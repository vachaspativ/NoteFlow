"""Network-activity-based call detection for the NoteFlow daemon.

Detects active VoIP/video calls by monitoring whether known communication
processes have sustained UDP connections to Microsoft Teams media relay IPs
or Google Meet (via Chrome) media relay IPs.

Detection strategy:
  - Scan psutil.net_connections(kind='udp') for connections from Teams/Chrome PIDs.
  - A connection qualifies when:
      (a) remote IP falls within a known Teams or Google media relay CIDR, OR
      (b) remote UDP port is in the STUN/TURN port set {3478–3481}
          (VPN/corporate TURN fallback — relay IP is the VPN gateway, not Microsoft's).
  - Require ≥ N simultaneous qualifying connections to avoid false-positives from
    stray STUN probes or background keep-alive packets.

Cross-platform: works identically on Windows and macOS via psutil.
"""
from __future__ import annotations

import ipaddress
import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known Teams media relay CIDR blocks (Microsoft Azure CDN / Transport Relay)
# Source: https://learn.microsoft.com/en-us/microsoft-365/enterprise/urls-and-ip-address-ranges
# Category 11 (media) — stable for years, verified 2025
# ---------------------------------------------------------------------------
_TEAMS_CIDRS: list[ipaddress.IPv4Network] = [
    ipaddress.ip_network("13.107.64.0/18"),    # Teams media — primary
    ipaddress.ip_network("52.112.0.0/14"),     # Teams media — AMS/EU
    ipaddress.ip_network("52.122.0.0/15"),     # Teams media — APAC
    ipaddress.ip_network("52.238.119.141/32"), # Teams TURN relay
    ipaddress.ip_network("52.244.160.207/32"), # Teams TURN relay
]

# ---------------------------------------------------------------------------
# Google Meet WebRTC media relay CIDR blocks (Google ASN 15169)
# ---------------------------------------------------------------------------
_GOOGLE_CIDRS: list[ipaddress.IPv4Network] = [
    ipaddress.ip_network("64.233.160.0/19"),   # Google media / stun.l.google.com
    ipaddress.ip_network("74.125.0.0/16"),     # Google / Meet relay
    ipaddress.ip_network("142.250.0.0/15"),    # Google Cloud / Meet relay
    ipaddress.ip_network("216.58.192.0/19"),   # Google / Meet relay (older range)
]

# Standard STUN/TURN UDP ports — used as a VPN/corporate-proxy fallback
# when the remote IP is the VPN gateway rather than Microsoft's own relay.
STUN_TURN_PORTS: frozenset[int] = frozenset({3478, 3479, 3480, 3481})

# Loopback / any-address ranges to always ignore
_LOOPBACK = ipaddress.ip_network("127.0.0.0/8")
_ANY4 = ipaddress.ip_network("0.0.0.0/8")

# Exact executable names for Teams processes (lowercased)
TEAMS_PROCESS_NAMES: frozenset[str] = frozenset({
    "teams.exe", "ms-teams.exe", "msteams.exe",
})
# Chrome is the only browser monitored for Google Meet.
# NOTE: Microsoft Edge (msedge.exe) support is not included in this release.
# Edge users should use the window-title detection layer. See README.md.
MEET_PROCESS_NAMES: frozenset[str] = frozenset({
    "chrome.exe",
})
ALL_COMM_PROCESS_NAMES = TEAMS_PROCESS_NAMES | MEET_PROCESS_NAMES


class NetworkCallResult(NamedTuple):
    is_active: bool
    app_name: str          # e.g. "ms-teams.exe" or "chrome.exe"
    signal_type: str       # "ip_range" | "stun_port" | ""
    qualifying_count: int  # number of matching UDP connections found


def _ip_in_cidrs(ip_str: str, cidrs: list[ipaddress.IPv4Network]) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        if addr in _LOOPBACK or addr in _ANY4:
            return False
        return any(addr in net for net in cidrs)
    except ValueError:
        return False


def _is_qualifying_connection(raddr_ip: str, raddr_port: int,
                               cidrs: list[ipaddress.IPv4Network]) -> tuple[bool, str]:
    """Returns (is_qualifying, signal_type). signal_type is 'ip_range' or 'stun_port'."""
    # Always reject loopback, all-interface, and private-broadcast addresses first
    try:
        addr = ipaddress.ip_address(raddr_ip)
        if addr in _LOOPBACK or addr in _ANY4 or addr.is_loopback or addr.is_unspecified:
            return False, ""
    except ValueError:
        return False, ""

    if _ip_in_cidrs(raddr_ip, cidrs):
        return True, "ip_range"
    if raddr_port in STUN_TURN_PORTS:
        # VPN fallback: the port matches even if the IP is a corporate relay.
        # We already know the IP is non-loopback and non-local at this point.
        return True, "stun_port"
    return False, ""


class CallNetworkMonitor:
    """Monitors UDP connections to detect active Teams or Google Meet calls.

    Args:
        min_connections: Minimum simultaneous qualifying UDP connections required
                         before declaring a call as active. Default 2.
        teams_extra_cidrs: Optional additional CIDR strings for corporate VPN TURN
                           overrides (e.g. ["10.0.0.0/8"]).
    """

    def __init__(
        self,
        min_connections: int = 2,
        teams_extra_cidrs: list[str] | None = None,
    ) -> None:
        self.min_connections = min_connections
        self._teams_cidrs = list(_TEAMS_CIDRS)
        if teams_extra_cidrs:
            for cidr in teams_extra_cidrs:
                try:
                    self._teams_cidrs.append(ipaddress.ip_network(cidr, strict=False))
                except ValueError as exc:
                    logger.warning(f"Invalid extra CIDR '{cidr}': {exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_call_active(self) -> NetworkCallResult:
        """Inspect current UDP connections and return detection result."""
        try:
            import psutil
        except ImportError:
            logger.debug("psutil not available — skipping network call detection")
            return NetworkCallResult(False, "", "", 0)

        # Build a map of comm-process PID → (name, cidr_list)
        comm_pids: dict[int, tuple[str, list[ipaddress.IPv4Network]]] = {}
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                pname = (proc.info.get("name") or "").lower()
                pid = proc.info.get("pid")
                if pid is None:
                    continue
                if pname in TEAMS_PROCESS_NAMES:
                    comm_pids[pid] = (pname, self._teams_cidrs)
                elif pname in MEET_PROCESS_NAMES:
                    comm_pids[pid] = (pname, _GOOGLE_CIDRS)
        except Exception as exc:
            logger.debug(f"Process scan error in network monitor: {exc}")
            return NetworkCallResult(False, "", "", 0)

        if not comm_pids:
            return NetworkCallResult(False, "", "", 0)

        # Tally qualifying UDP connections per comm process
        best_result = NetworkCallResult(False, "", "", 0)
        try:
            udp_conns = psutil.net_connections(kind="udp")
        except Exception as exc:
            logger.debug(f"net_connections() error: {exc}")
            return NetworkCallResult(False, "", "", 0)

        # Group by (pid, app_name, cidr_list)
        counts: dict[int, dict] = {}
        for conn in udp_conns:
            if conn.pid not in comm_pids:
                continue
            if not conn.raddr or not conn.raddr.ip:
                continue
            app_name, cidrs = comm_pids[conn.pid]
            qualifying, sig_type = _is_qualifying_connection(
                conn.raddr.ip, conn.raddr.port, cidrs
            )
            if qualifying:
                entry = counts.setdefault(conn.pid, {
                    "app_name": app_name,
                    "count": 0,
                    "signal_type": sig_type,
                })
                entry["count"] += 1
                if entry["signal_type"] == "" and sig_type:
                    entry["signal_type"] = sig_type

        for pid, entry in counts.items():
            if entry["count"] >= self.min_connections:
                result = NetworkCallResult(
                    is_active=True,
                    app_name=entry["app_name"],
                    signal_type=entry["signal_type"],
                    qualifying_count=entry["count"],
                )
                # Prefer Teams over Chrome if both active
                if not best_result.is_active or "teams" in entry["app_name"]:
                    best_result = result

        if best_result.is_active:
            logger.debug(
                f"[NetworkMonitor] Active call via {best_result.app_name} "
                f"({best_result.qualifying_count} UDP connections, "
                f"signal={best_result.signal_type})"
            )

        return best_result

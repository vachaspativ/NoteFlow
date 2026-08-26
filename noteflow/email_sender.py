from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime
import string


class EmailSender:
    """Sends notes via email."""

    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool,
        username: str,
        password: str,
        email_from: str,
        email_to: str,
        subject_prefix: str = "[NoteFlow]",
    ):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.username = username
        self.password = password
        self.email_from = email_from
        self.email_to = email_to
        self.subject_prefix = subject_prefix

        # Load HTML template
        template_path = Path(__file__).parent / "templates" / "email_template.html"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                self.html_template = f.read()
        except FileNotFoundError:
            self.html_template = "" # Fallback or tests

    def send(
        self,
        notes: dict,
        title: str,
        duration: str,
        start_time: str,
        end_time: str,
        transcript: str,
    ) -> None:
        """Send the formatted notes and transcript via email."""
        msg = MIMEMultipart("alternative")
        date_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"{self.subject_prefix} {title} - {date_str}"
        msg["Subject"] = subject
        msg["From"] = self.email_from
        msg["To"] = self.email_to

        plain_text = self.build_plain_text(
            notes, title, duration, start_time, end_time, transcript, date_str
        )
        html_text = self.build_html(
            notes, title, duration, start_time, end_time, transcript, date_str
        )

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_text, "html"))

        if self.port == 465:
            server = smtplib.SMTP_SSL(self.host, self.port)
        else:
            server = smtplib.SMTP(self.host, self.port)
            if self.use_tls:
                server.starttls()
        
        try:
            if self.username and self.password:
                server.login(self.username, self.password)
            server.sendmail(self.email_from, [self.email_to], msg.as_string())
        finally:
            server.quit()

    def build_html(
        self,
        notes: dict,
        title: str,
        duration: str,
        start_time: str,
        end_time: str,
        transcript: str,
        date_str: str,
    ) -> str:
        """Build HTML email content."""
        summary = notes.get("summary", "")
        
        # Action Items
        action_items = notes.get("action_items", [])
        action_items_html = ""
        if not action_items:
            action_items_html = "<tr><td colspan='3' style='padding: 12px; text-align: center; border: 1px solid #ddd;'>No action items.</td></tr>"
        else:
            for item in action_items:
                owner = item.get("owner", "Unassigned")
                action = item.get("action", "")
                deadline = item.get("deadline", "-")
                action_items_html += f"<tr><td style='padding: 12px; border: 1px solid #ddd;'>{owner}</td><td style='padding: 12px; border: 1px solid #ddd;'>{action}</td><td style='padding: 12px; border: 1px solid #ddd;'>{deadline}</td></tr>"

        # Highlights
        highlights = notes.get("highlights", [])
        highlights_html = ""
        if not highlights:
            highlights_html = "<li>No highlights available.</li>"
        else:
            for hl in highlights:
                highlights_html += f"<li>{hl}</li>"

        # Decisions
        decisions = notes.get("decisions", [])
        decisions_html = ""
        if not decisions:
            decisions_html = "<li>No decisions recorded.</li>"
        else:
            for dec in decisions:
                decisions_html += f"<li>{dec}</li>"

        # Stakeholders
        stakeholders = notes.get("stakeholders", [])
        stakeholders_html = ""
        if not stakeholders:
            stakeholders_html = "<tr><td colspan='3' style='padding: 12px; text-align: center; border: 1px solid #ddd;'>No stakeholders mapped.</td></tr>"
        else:
            for sh in stakeholders:
                name = sh.get("name", "Unknown")
                role = sh.get("role", "Participant")
                sentiment = sh.get("sentiment", "Neutral")
                stakeholders_html += f"<tr><td style='padding: 12px; border: 1px solid #ddd;'>{name}</td><td style='padding: 12px; border: 1px solid #ddd;'>{role}</td><td style='padding: 12px; border: 1px solid #ddd;'>{sentiment}</td></tr>"

        # Risks
        risks = notes.get("risks", [])
        risks_html = ""
        if not risks:
            risks_html = "<li>No risks identified.</li>"
        else:
            for r in risks:
                risks_html += f"<li>{r}</li>"

        # Dependencies
        dependencies = notes.get("dependencies", [])
        dependencies_html = ""
        if not dependencies:
            dependencies_html = "<li>No dependencies identified.</li>"
        else:
            for d in dependencies:
                dependencies_html += f"<li>{d}</li>"

        # Recommendations
        recommendations = notes.get("recommendations", [])
        recommendations_html = ""
        if not recommendations:
            recommendations_html = "<li>No recommendations recorded.</li>"
        else:
            for rec in recommendations:
                recommendations_html += f"<li>{rec}</li>"

        if not self.html_template:
            # simple fallback
            return f"<h1>{title}</h1><p>{summary}</p>"

        # format template
        # Using string replacement to avoid KeyError with .format() for unexpected braces
        html = self.html_template
        html = html.replace("{title}", title)
        html = html.replace("{date}", date_str)
        html = html.replace("{duration}", duration)
        html = html.replace("{start_time}", start_time)
        html = html.replace("{end_time}", end_time)
        html = html.replace("{summary}", summary)
        html = html.replace("{action_items_html}", action_items_html)
        html = html.replace("{highlights_html}", highlights_html)
        html = html.replace("{decisions_html}", decisions_html)
        html = html.replace("{stakeholders_html}", stakeholders_html)
        html = html.replace("{risks_html}", risks_html)
        html = html.replace("{dependencies_html}", dependencies_html)
        html = html.replace("{recommendations_html}", recommendations_html)
        html = html.replace("{transcript}", transcript)
        
        return html

    def build_plain_text(
        self,
        notes: dict,
        title: str,
        duration: str,
        start_time: str,
        end_time: str,
        transcript: str,
        date_str: str,
    ) -> str:
        """Build plain text email content."""
        lines = []
        lines.append(f"Meeting: {title}")
        lines.append(f"Date: {date_str} | Duration: {duration} ({start_time} - {end_time})")
        lines.append("=" * 60)
        lines.append("\nSUMMARY")
        lines.append("-" * 60)
        lines.append(notes.get("summary", ""))
        
        lines.append("\nSTAKEHOLDER MAPPING")
        lines.append("-" * 60)
        stakeholders = notes.get("stakeholders", [])
        if stakeholders:
            for sh in stakeholders:
                lines.append(f"- {sh.get('name', 'Unknown')} ({sh.get('role', 'Participant')}) - Sentiment: {sh.get('sentiment', 'Neutral')}")
        else:
            lines.append("No stakeholders mapped.")

        lines.append("\nACTION ITEMS")
        lines.append("-" * 60)
        action_items = notes.get("action_items", [])
        if action_items:
            for item in action_items:
                owner = item.get("owner", "Unassigned")
                action = item.get("action", "")
                deadline = item.get("deadline", "-")
                lines.append(f"- [{owner}] {action} (Due: {deadline})")
        else:
            lines.append("No action items.")

        lines.append("\nDECISIONS")
        lines.append("-" * 60)
        decisions = notes.get("decisions", [])
        if decisions:
            for dec in decisions:
                lines.append(f"- {dec}")
        else:
            lines.append("No decisions recorded.")

        lines.append("\nRISKS")
        lines.append("-" * 60)
        risks = notes.get("risks", [])
        if risks:
            for r in risks:
                lines.append(f"- {r}")
        else:
            lines.append("No risks identified.")

        lines.append("\nDEPENDENCIES")
        lines.append("-" * 60)
        dependencies = notes.get("dependencies", [])
        if dependencies:
            for d in dependencies:
                lines.append(f"- {d}")
        else:
            lines.append("No dependencies identified.")

        lines.append("\nSTRATEGIC RECOMMENDATIONS")
        lines.append("-" * 60)
        recommendations = notes.get("recommendations", [])
        if recommendations:
            for rec in recommendations:
                lines.append(f"- {rec}")
        else:
            lines.append("No recommendations recorded.")

        # Legacy Highlights block
        highlights = notes.get("highlights", [])
        if highlights:
            lines.append("\nHIGHLIGHTS")
            lines.append("-" * 60)
            for hl in highlights:
                lines.append(f"- {hl}")

        lines.append("\n" + "=" * 60)
        lines.append("RAW TRANSCRIPT")
        lines.append("=" * 60)
        lines.append(transcript)
        
        lines.append("\n\nGenerated by NoteFlow (Offline AI) — All data processed locally")
        
        return "\n".join(lines)

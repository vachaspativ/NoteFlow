/* ==========================================================================
   NoteFlow Web UI Application Logic
   ========================================================================== */

(function () {
  'use strict';

  // State
  const state = {
    theme: 'dark',
    mode: 'live',
    isRecording: false,
    timerInterval: null,
    durationSeconds: 0,
    currentSessionId: null,
    currentNotes: null,
    ws: null,
    devices: [],
    settings: {},
    audioWaveAnimId: null,
    isRegenerating: false,
  };

  // DOM Elements
  const els = {
    html: document.documentElement,
    themeToggle: document.getElementById('btn-theme-toggle'),
    views: {
      setup: document.getElementById('view-setup'),
      recording: document.getElementById('view-recording'),
      processing: document.getElementById('view-processing'),
      results: document.getElementById('view-results'),
    },
    statusPills: {
      whisper: document.getElementById('pill-whisper'),
      ollama: document.getElementById('pill-ollama'),
      mic: document.getElementById('pill-mic'),
    },
    setup: {
      titleInput: document.getElementById('input-meeting-title'),
      cardLive: document.getElementById('card-mode-live'),
      cardBatch: document.getElementById('card-mode-batch'),
      micSelect: document.getElementById('select-mic'),
      whisperPreview: document.getElementById('preview-whisper-model'),
      ollamaPreview: document.getElementById('preview-ollama-model'),
      autoCallBadge: document.getElementById('badge-autocall-status'),
      autoCallLabel: document.getElementById('label-autocall'),
      startBtn: document.getElementById('btn-start-session'),
    },
    recording: {
      hudTitle: document.getElementById('hud-title'),
      hudModePill: document.getElementById('hud-mode-pill'),
      hudTimer: document.getElementById('hud-timer'),
      canvas: document.getElementById('waveform-canvas'),
      feedLive: document.getElementById('feed-live-container'),
      feedBatch: document.getElementById('feed-batch-container'),
      stream: document.getElementById('transcript-stream'),
      placeholder: document.getElementById('transcript-placeholder'),
      segmentCounter: document.getElementById('hud-segment-counter'),
      autoScroll: document.getElementById('check-auto-scroll'),
      batchChunks: document.getElementById('batch-stat-chunks'),
      batchSize: document.getElementById('batch-stat-size'),
      stopBtn: document.getElementById('btn-stop-session'),
    },
    processing: {
      subtitle: document.getElementById('processing-subtitle'),
      barFill: document.getElementById('processing-bar-fill'),
      log: document.getElementById('processing-log'),
      steps: [
        document.getElementById('step-1'),
        document.getElementById('step-2'),
        document.getElementById('step-3'),
        document.getElementById('step-4'),
      ],
    },
    results: {
      date: document.getElementById('res-date'),
      title: document.getElementById('res-title'),
      duration: document.getElementById('res-duration'),
      mode: document.getElementById('res-mode'),
      emailTag: document.getElementById('res-email-tag'),
      summary: document.getElementById('res-summary'),
      actionsCount: document.getElementById('res-actions-count'),
      actionsList: document.getElementById('res-actions-list'),
      highlightsList: document.getElementById('res-highlights-list'),
      decisionsList: document.getElementById('res-decisions-list'),
      transcriptBody: document.getElementById('res-transcript-body'),
      transcriptText: document.getElementById('res-transcript-text'),
      toggleTranscriptBtn: document.getElementById('btn-toggle-transcript'),
      copyTranscriptBtn: document.getElementById('btn-copy-raw-transcript'),
      copyNotesBtn: document.getElementById('btn-copy-notes'),
      regenerateNotesBtn: document.getElementById('btn-regenerate-notes'),
      downloadMdBtn: document.getElementById('btn-download-md'),
      downloadTranscriptBtn: document.getElementById('btn-download-transcript'),
      resendEmailBtn: document.getElementById('btn-resend-email'),
      newMeetingBtn: document.getElementById('btn-new-meeting'),
    },
    history: {
      drawer: document.getElementById('history-drawer'),
      overlay: document.getElementById('drawer-overlay'),
      list: document.getElementById('history-sessions-list'),
      openBtn: document.getElementById('btn-history'),
      closeBtn: document.getElementById('btn-close-drawer'),
    },
    settingsModal: {
      modal: document.getElementById('modal-settings'),
      openBtn: document.getElementById('btn-settings'),
      closeBtn: document.getElementById('btn-close-settings'),
      cancelBtn: document.getElementById('btn-cancel-settings'),
      form: document.getElementById('form-settings'),
      whisperModel: document.getElementById('cfg-whisper-model'),
      whisperDevice: document.getElementById('cfg-whisper-device'),
      allowOnlineModelDownload: document.getElementById('cfg-allow-online-model-download'),
      enableLoopback: document.getElementById('cfg-enable-loopback'),
      autoCallDetection: document.getElementById('cfg-auto-call-detection'),
      titlePrefix: document.getElementById('cfg-title-prefix'),
      ollamaHost: document.getElementById('cfg-ollama-host'),
      ollamaPort: document.getElementById('cfg-ollama-port'),
      ollamaModel: document.getElementById('cfg-ollama-model'),
      ollamaTimeout: document.getElementById('cfg-ollama-timeout'),
      ollamaRetries: document.getElementById('cfg-ollama-retries'),
      smtpHost: document.getElementById('cfg-smtp-host'),
      smtpPort: document.getElementById('cfg-smtp-port'),
      smtpUser: document.getElementById('cfg-smtp-user'),
      emailTo: document.getElementById('cfg-email-to'),
      enableEmail: document.getElementById('cfg-enable-email'),
    },
    toastContainer: document.getElementById('toast-container'),
  };

  // --- Initialize App ---
  async function init() {
    setupEventListeners();
    initWaveformCanvas();
    await loadSettings();
    await checkStatus();
    await loadDevices();
    connectWebSocket();
    suggestMeetingTitle();
  }

  // --- Views Switcher ---
  function showView(viewName) {
    Object.keys(els.views).forEach((key) => {
      els.views[key].classList.toggle('active', key === viewName);
    });
  }

  function suggestMeetingTitle() {
    const now = new Date();
    const formattedDate = now.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const formattedTime = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    els.setup.titleInput.value = `Meeting — ${formattedDate} (${formattedTime})`;
  }

  // --- Event Listeners ---
  function setupEventListeners() {
    // Theme Switch
    els.themeToggle.addEventListener('click', toggleTheme);

    // Mode Selector Cards
    els.setup.cardLive.addEventListener('click', () => setMode('live'));
    els.setup.cardBatch.addEventListener('click', () => setMode('batch'));

    // Start Session
    els.setup.startBtn.addEventListener('click', handleStartSession);

    // Stop Session
    els.recording.stopBtn.addEventListener('click', handleStopSession);

    // Results Actions
    els.results.toggleTranscriptBtn.addEventListener('click', () => {
      els.results.transcriptBody.classList.toggle('hidden');
    });

    els.results.copyTranscriptBtn.addEventListener('click', () => {
      copyToClipboard(els.results.transcriptText.innerText, 'Transcript copied to clipboard!');
    });

    els.results.copyNotesBtn.addEventListener('click', () => {
      if (state.currentNotes) {
        copyToClipboard(formatNotesMarkdown(state.currentNotes), 'Formatted notes copied to clipboard!');
      }
    });

    els.results.downloadMdBtn.addEventListener('click', handleDownloadMarkdown);
    if (els.results.regenerateNotesBtn) els.results.regenerateNotesBtn.addEventListener('click', handleRegenerateNotes);
    if (els.results.downloadTranscriptBtn) els.results.downloadTranscriptBtn.addEventListener('click', handleDownloadTranscript);
    els.results.resendEmailBtn.addEventListener('click', handleResendEmail);
    els.results.newMeetingBtn.addEventListener('click', () => {
      suggestMeetingTitle();
      showView('setup');
    });

    // History Drawer
    els.history.openBtn.addEventListener('click', openHistoryDrawer);
    els.history.closeBtn.addEventListener('click', closeHistoryDrawer);
    els.history.overlay.addEventListener('click', closeHistoryDrawer);

    // Settings Modal
    els.settingsModal.openBtn.addEventListener('click', openSettingsModal);
    els.settingsModal.closeBtn.addEventListener('click', closeSettingsModal);
    els.settingsModal.cancelBtn.addEventListener('click', closeSettingsModal);
    els.settingsModal.form.addEventListener('submit', handleSaveSettings);
  }

  // --- Mode Handling ---
  function setMode(mode) {
    state.mode = mode;
    els.setup.cardLive.classList.toggle('active', mode === 'live');
    els.setup.cardBatch.classList.toggle('active', mode === 'batch');
    const radio = document.querySelector(`input[name="transcription_mode"][value="${mode}"]`);
    if (radio) radio.checked = true;
  }

  // --- Theme Handling ---
  function toggleTheme() {
    const newTheme = state.theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    saveThemePreference(newTheme);
  }

  function setTheme(theme) {
    state.theme = theme;
    els.html.setAttribute('data-theme', theme);
  }

  async function saveThemePreference(theme) {
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme }),
      });
    } catch (e) {
      console.warn('Could not persist theme to server:', e);
    }
  }

  function updateAutoCallBadge(enabled, running) {
    if (!els.setup.autoCallBadge || !els.setup.autoCallLabel) return;
    if (enabled) {
      els.setup.autoCallBadge.classList.remove('inactive');
      els.setup.autoCallBadge.classList.add('active');
      els.setup.autoCallLabel.innerText = running ? '🤖 Auto Call Listener: ACTIVE' : '🤖 Auto Call Listener: ON';
    } else {
      els.setup.autoCallBadge.classList.remove('active');
      els.setup.autoCallBadge.classList.add('inactive');
      els.setup.autoCallLabel.innerText = 'Auto Call Listener: OFF';
    }
  }

  // --- API & Status ---
  async function loadSettings() {
    try {
      const res = await fetch('/api/settings');
      if (res.ok) {
        state.settings = await res.json();
        setTheme(state.settings.theme || 'dark');
        setMode(state.settings.transcription_mode || 'live');
        els.setup.whisperPreview.innerText = `Whisper: ${state.settings.whisper_model}`;
        els.setup.ollamaPreview.innerText = `Ollama: ${state.settings.ollama_model}`;

        updateAutoCallBadge(state.settings.auto_call_detection, true);

        // Populate settings modal
        els.settingsModal.whisperModel.value = state.settings.whisper_model;
        els.settingsModal.whisperDevice.value = state.settings.whisper_device;
        if (els.settingsModal.allowOnlineModelDownload) els.settingsModal.allowOnlineModelDownload.checked = state.settings.allow_online_model_download ?? false;
        if (els.settingsModal.enableLoopback) els.settingsModal.enableLoopback.checked = state.settings.enable_loopback ?? true;
        if (els.settingsModal.autoCallDetection) els.settingsModal.autoCallDetection.checked = state.settings.auto_call_detection ?? false;
        if (els.settingsModal.titlePrefix) els.settingsModal.titlePrefix.value = state.settings.default_meeting_title_prefix || '[NoteFlow] Meeting';
        els.settingsModal.ollamaHost.value = state.settings.ollama_host;
        els.settingsModal.ollamaPort.value = state.settings.ollama_port;
        els.settingsModal.ollamaModel.value = state.settings.ollama_model;
        if (els.settingsModal.ollamaTimeout) els.settingsModal.ollamaTimeout.value = state.settings.ollama_timeout || 300;
        if (els.settingsModal.ollamaRetries) els.settingsModal.ollamaRetries.value = state.settings.ollama_max_retries ?? 1;
        els.settingsModal.smtpHost.value = state.settings.smtp_host;
        els.settingsModal.smtpPort.value = state.settings.smtp_port;
        els.settingsModal.smtpUser.value = state.settings.smtp_username;
        els.settingsModal.emailTo.value = state.settings.email_to;
        if (els.settingsModal.enableEmail) els.settingsModal.enableEmail.checked = state.settings.enable_email ?? true;
      }
    } catch (e) {
      console.error('Error loading settings:', e);
    }
  }

  async function checkStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        updateStatusPill(els.statusPills.whisper, data.components.whisper);
        updateStatusPill(els.statusPills.ollama, data.components.ollama);
        updateStatusPill(els.statusPills.mic, data.components.microphone);

        updateAutoCallBadge(data.auto_call_detection, data.daemon_running);

        if (data.is_recording && data.active_session) {
          resumeActiveSession(data.active_session);
        }
      }
    } catch (e) {
      console.error('Error checking status:', e);
    }
  }

  function updateStatusPill(pill, isOnline) {
    pill.classList.toggle('online', !!isOnline);
    pill.classList.toggle('offline', !isOnline);
  }

  async function loadDevices() {
    try {
      const res = await fetch('/api/devices');
      if (res.ok) {
        state.devices = await res.json();
        els.setup.micSelect.innerHTML = '';
        if (state.devices.length === 0) {
          els.setup.micSelect.innerHTML = '<option value="">Default System Microphone</option>';
        } else {
          state.devices.forEach((d, idx) => {
            const opt = document.createElement('option');
            opt.value = idx;
            opt.innerText = `${d.name || 'Microphone ' + idx} (${d.max_input_channels || 1} ch)`;
            els.setup.micSelect.appendChild(opt);
          });
        }
      }
    } catch (e) {
      console.error('Error loading audio devices:', e);
    }
  }

  // --- WebSocket Connection ---
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    state.ws = new WebSocket(wsUrl);

    state.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleWebSocketMessage(msg);
      } catch (e) {
        console.error('Error parsing WS message:', e);
      }
    };

    state.ws.onclose = () => {
      setTimeout(connectWebSocket, 3000);
    };
  }

  function handleWebSocketMessage(msg) {
    if (msg.type === 'segment') {
      appendTranscriptSegment(msg.data);
    } else if (msg.type === 'status') {
      updateProcessingProgress(msg.data);
    }
  }

  function appendTranscriptSegment(segment) {
    if (els.recording.placeholder) {
      els.recording.placeholder.style.display = 'none';
    }

    const bubble = document.createElement('div');
    bubble.className = 'speech-bubble';
    bubble.innerHTML = `
      <span class="speech-time">${segment.timestamp_display}</span>
      <span class="speech-text">${escapeHtml(segment.text)}</span>
    `;
    els.recording.stream.appendChild(bubble);

    const count = els.recording.stream.querySelectorAll('.speech-bubble').length;
    els.recording.segmentCounter.innerText = `${count} segments`;

    if (els.recording.autoScroll.checked) {
      els.recording.stream.scrollTop = els.recording.stream.scrollHeight;
    }
  }

  // --- Session Control ---
  async function handleStartSession() {
    const title = els.setup.titleInput.value.trim() || 'Untitled Meeting';
    const deviceId = els.setup.micSelect.value ? parseInt(els.setup.micSelect.value, 10) : null;

    try {
      els.setup.startBtn.disabled = true;
      const res = await fetch('/api/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          mode: state.mode,
          theme: state.theme,
          device_id: deviceId,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to start session');
      }

      const data = await res.json();
      state.currentSessionId = data.session_id;
      state.isRecording = true;
      state.durationSeconds = 0;

      // Setup Recording HUD
      els.recording.hudTitle.innerText = title;
      els.recording.hudModePill.innerText = state.mode.toUpperCase() + ' MODE';
      els.recording.stream.innerHTML = '';
      if (els.recording.placeholder) els.recording.placeholder.style.display = 'flex';
      els.recording.segmentCounter.innerText = '0 segments';

      els.recording.feedLive.classList.toggle('hidden', state.mode !== 'live');
      els.recording.feedBatch.classList.toggle('hidden', state.mode !== 'batch');

      startTimer();
      startWaveformAnimation();
      showView('recording');
      showToast('Recording session started!');
    } catch (e) {
      showToast(`Error: ${e.message}`, 'error');
    } finally {
      els.setup.startBtn.disabled = false;
    }
  }

  async function handleStopSession() {
    stopTimer();
    stopWaveformAnimation();
    state.isRecording = false;

    showView('processing');
    resetProcessingStepper();

    try {
      const res = await fetch('/api/session/stop', { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Processing failed');
      }

      const data = await res.json();
      state.currentNotes = data.notes;
      renderResults(data.notes);
      showView('results');
      showToast('Meeting notes ready!');
    } catch (e) {
      els.processing.subtitle.innerText = `Error: ${e.message}`;
      showToast(`Processing error: ${e.message}`, 'error');
      if (!state.currentNotes) {
        state.currentNotes = {
          title: els.recording.hudTitle.innerText || 'Meeting Notes',
          summary: `(Processing error: ${e.message})`,
          error: e.message,
          action_items: [],
          highlights: [],
          decisions: [],
          transcript: '',
        };
      }
      setTimeout(() => {
        renderResults(state.currentNotes);
        showView('results');
      }, 1000);
    }
  }

  function startTimer() {
    clearInterval(state.timerInterval);
    state.timerInterval = setInterval(() => {
      state.durationSeconds += 1;
      const h = Math.floor(state.durationSeconds / 3600);
      const m = Math.floor((state.durationSeconds % 3600) / 60);
      const s = state.durationSeconds % 60;
      els.recording.hudTimer.innerText = `${pad(h)}:${pad(m)}:${pad(s)}`;

      // Update batch estimated stats if in batch mode
      if (state.mode === 'batch') {
        const chunks = Math.floor(state.durationSeconds / 3);
        const mb = (chunks * 0.1).toFixed(1);
        els.recording.batchChunks.innerText = chunks;
        els.recording.batchSize.innerText = `~${mb} MB`;
      }
    }, 1000);
  }

  function stopTimer() {
    clearInterval(state.timerInterval);
  }

  function pad(num) {
    return num.toString().padStart(2, '0');
  }

  // --- Processing Progress ---
  function resetProcessingStepper() {
    els.processing.barFill.style.width = '10%';
    els.processing.subtitle.innerText = 'Initializing local models...';
    els.processing.log.innerHTML = '<div class="log-line">Initializing pipeline...</div>';
    
    // Update Step 4 labels if dry run is active
    const step4Title = document.querySelector('#step-4 .step-title');
    const step4Desc = document.querySelector('#step-4 .step-desc');
    if (state.settings && state.settings.dry_run) {
      if (step4Title) step4Title.innerText = 'Local Archival (Dry Run)';
      if (step4Desc) step4Desc.innerText = 'Write JSON/MD archives (SMTP email skipped)';
    } else {
      if (step4Title) step4Title.innerText = 'Email & Archival';
      if (step4Desc) step4Desc.innerText = 'Dispatch SMTP report and write JSON/MD';
    }

    els.processing.steps.forEach((s, i) => {
      s.classList.toggle('active', i === 0);
      s.classList.remove('completed');
    });
  }

  function updateProcessingProgress(status) {
    const pct = Math.round(status.progress * 100);
    els.processing.barFill.style.width = `${pct}%`;
    els.processing.subtitle.innerText = status.message;

    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerText = `[${new Date().toLocaleTimeString()}] ${status.message}`;
    els.processing.log.appendChild(line);
    els.processing.log.scrollTop = els.processing.log.scrollHeight;

    if (status.progress >= 1.0) {
      els.processing.steps.forEach((s) => {
        s.classList.remove('active');
        s.classList.add('completed');
      });
      if (state.currentNotes) {
        renderResults(state.currentNotes);
        showView('results');
      }
    } else {
      const stepIndex = status.progress < 0.25 ? 0 : status.progress < 0.5 ? 1 : status.progress < 0.8 ? 2 : 3;
      els.processing.steps.forEach((s, idx) => {
        s.classList.toggle('completed', idx < stepIndex);
        s.classList.toggle('active', idx === stepIndex);
      });
    }
  }

  // --- Render Results ---
  function renderResults(notes) {
    els.results.title.innerText = notes.title || 'Untitled Meeting';
    els.results.duration.innerText = notes.duration || `${state.durationSeconds}s`;
    els.results.mode.innerText = state.mode === 'live' ? 'Live Stream' : 'Silent Batch';
    els.results.date.innerText = new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });

    els.results.emailTag.style.display = notes.email_sent ? 'inline-block' : 'none';

    // Summary
    const hasError = notes.error || (notes.summary && (notes.summary.includes('failed') || notes.summary.includes('skipped') || notes.summary.includes('timed out')));
    if (hasError) {
      const errMsg = notes.error || notes.summary;
      els.results.summary.innerHTML = `
        <div class="action-error-box">
          <div class="error-header">
            <span>⚠️ Note Generation Timed Out / Failed</span>
          </div>
          <div class="error-detail">${escapeHtml(errMsg)}</div>
          <div class="error-hint">💡 <em>Tip: You can increase <strong>Ollama Timeout</strong> in Settings, select a lighter model like <code>phi3</code>, or click Retry below.</em></div>
          <button class="btn btn-primary btn-small" id="btn-retry-inline-notes">
            🔄 Retry Notes Generation
          </button>
        </div>
      `;
      const retryBtn = document.getElementById('btn-retry-inline-notes');
      if (retryBtn) {
        retryBtn.addEventListener('click', handleRegenerateNotes);
      }
    } else {
      els.results.summary.innerText = notes.summary || 'No summary available.';
    }

    // Action Items
    els.results.actionsList.innerHTML = '';
    const actions = notes.action_items || [];
    els.results.actionsCount.innerText = actions.length;
    if (actions.length === 0) {
      els.results.actionsList.innerHTML = '<p class="empty-state-text">No action items identified.</p>';
    } else {
      actions.forEach((item) => {
        const row = document.createElement('div');
        row.className = 'action-item-row';
        const owner = typeof item === 'object' ? item.owner || 'Unassigned' : 'Unassigned';
        const text = typeof item === 'object' ? item.action || item : item;
        const deadline = typeof item === 'object' && item.deadline ? item.deadline : 'Not specified';
        row.innerHTML = `
          <input type="checkbox" class="action-checkbox">
          <div class="action-body">
            <div class="action-text">${escapeHtml(text)}</div>
            <div class="action-meta">
              <span class="action-owner">👤 ${escapeHtml(owner)}</span>
              <span class="action-deadline">📅 ${escapeHtml(deadline)}</span>
            </div>
          </div>
        `;
        els.results.actionsList.appendChild(row);
      });
    }

    // Highlights
    els.results.highlightsList.innerHTML = '';
    const highlights = notes.highlights || [];
    if (highlights.length === 0) {
      els.results.highlightsList.innerHTML = '<li class="empty-state-text">No key highlights recorded.</li>';
    } else {
      highlights.forEach((h) => {
        const li = document.createElement('li');
        li.innerText = h;
        els.results.highlightsList.appendChild(li);
      });
    }

    // Decisions
    els.results.decisionsList.innerHTML = '';
    const decisions = notes.decisions || [];
    if (decisions.length === 0) {
      els.results.decisionsList.innerHTML = '<li class="empty-state-text">No decisions recorded.</li>';
    } else {
      decisions.forEach((d) => {
        const li = document.createElement('li');
        li.innerText = d;
        els.results.decisionsList.appendChild(li);
      });
    }

    // Transcript
    const transcript = notes.timestamped_transcript || notes.transcript || 'No transcript generated.';
    els.results.transcriptText.innerText = transcript;
  }

  // --- Waveform Canvas Animation ---
  function initWaveformCanvas() {
    const ctx = els.recording.canvas.getContext('2d');
    ctx.clearRect(0, 0, els.recording.canvas.width, els.recording.canvas.height);
  }

  function startWaveformAnimation() {
    const canvas = els.recording.canvas;
    const ctx = canvas.getContext('2d');
    let phase = 0;

    function draw() {
      if (!state.isRecording) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const isDark = state.theme === 'dark';
      ctx.strokeStyle = isDark ? '#58a6ff' : '#0969da';
      ctx.lineWidth = 2;
      ctx.beginPath();

      const centerY = canvas.height / 2;
      const numBars = 50;
      const spacing = canvas.width / numBars;

      for (let i = 0; i < numBars; i++) {
        const x = i * spacing;
        const amp = Math.sin(phase + i * 0.2) * 15 + Math.cos(phase * 0.7 + i * 0.3) * 10;
        const h = Math.max(4, Math.abs(amp));
        ctx.moveTo(x, centerY - h / 2);
        ctx.lineTo(x, centerY + h / 2);
      }

      ctx.stroke();
      phase += 0.08;
      state.audioWaveAnimId = requestAnimationFrame(draw);
    }

    draw();
  }

  function stopWaveformAnimation() {
    if (state.audioWaveAnimId) {
      cancelAnimationFrame(state.audioWaveAnimId);
      initWaveformCanvas();
    }
  }

  // --- History Drawer ---
  async function openHistoryDrawer() {
    els.history.drawer.classList.remove('hidden');
    els.history.overlay.classList.remove('hidden');
    els.history.list.innerHTML = '<div class="empty-history">Loading sessions...</div>';

    try {
      const res = await fetch('/api/sessions');
      if (res.ok) {
        const sessions = await res.json();
        if (sessions.length === 0) {
          els.history.list.innerHTML = '<div class="empty-history">No past meetings recorded yet.</div>';
          return;
        }

        els.history.list.innerHTML = '';
        sessions.forEach((s) => {
          const card = document.createElement('div');
          card.className = 'history-card';
          card.innerHTML = `
            <div class="history-card-header">
              <span class="history-card-title">${escapeHtml(s.title)}</span>
              <span class="history-card-date">${s.start_time.split('T')[0] || ''}</span>
            </div>
            <div class="history-card-preview">${escapeHtml(s.summary_preview)}</div>
            <div class="results-meta-row" style="margin-top: 8px;">
              <span class="meta-tag">⏱️ ${s.duration_display}</span>
              <span class="meta-tag">✅ ${s.action_items_count} Actions</span>
            </div>
          `;
          card.addEventListener('click', () => loadPastSession(s.session_id));
          els.history.list.appendChild(card);
        });
      }
    } catch (e) {
      els.history.list.innerHTML = `<div class="empty-history">Failed to load history: ${e.message}</div>`;
    }
  }

  function closeHistoryDrawer() {
    els.history.drawer.classList.add('hidden');
    els.history.overlay.classList.add('hidden');
  }

  async function loadPastSession(sessionId) {
    try {
      closeHistoryDrawer();
      const res = await fetch(`/api/sessions/${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        state.currentSessionId = data.session_id;
        state.currentNotes = data.notes;
        renderResults(data.notes);
        showView('results');
        showToast(`Loaded "${data.title}"`);
      }
    } catch (e) {
      showToast(`Error loading session: ${e.message}`, 'error');
    }
  }

  // --- Settings Modal ---
  function openSettingsModal() {
    els.settingsModal.modal.classList.remove('hidden');
  }

  function closeSettingsModal() {
    els.settingsModal.modal.classList.add('hidden');
  }

  async function handleSaveSettings(e) {
    e.preventDefault();
    const payload = {
      whisper_model: els.settingsModal.whisperModel.value,
      whisper_device: els.settingsModal.whisperDevice.value,
      allow_online_model_download: els.settingsModal.allowOnlineModelDownload ? els.settingsModal.allowOnlineModelDownload.checked : false,
      enable_loopback: els.settingsModal.enableLoopback ? els.settingsModal.enableLoopback.checked : true,
      auto_call_detection: els.settingsModal.autoCallDetection ? els.settingsModal.autoCallDetection.checked : false,
      default_meeting_title_prefix: els.settingsModal.titlePrefix ? els.settingsModal.titlePrefix.value : '[NoteFlow] Meeting',
      ollama_host: els.settingsModal.ollamaHost.value,
      ollama_port: parseInt(els.settingsModal.ollamaPort.value, 10) || 11434,
      ollama_model: els.settingsModal.ollamaModel.value,
      ollama_timeout: parseInt(els.settingsModal.ollamaTimeout.value, 10) || 300,
      ollama_max_retries: parseInt(els.settingsModal.ollamaRetries ? els.settingsModal.ollamaRetries.value : '1', 10) ?? 1,
      smtp_host: els.settingsModal.smtpHost.value,
      smtp_port: parseInt(els.settingsModal.smtpPort.value, 10) || 587,
      smtp_username: els.settingsModal.smtpUser.value,
      email_to: els.settingsModal.emailTo.value,
      enable_email: els.settingsModal.enableEmail ? els.settingsModal.enableEmail.checked : true,
    };

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        closeSettingsModal();
        await loadSettings();
        await checkStatus();
        showToast('Settings saved successfully!');
      } else {
        showToast('Failed to save settings', 'error');
      }
    } catch (err) {
      showToast(`Error saving settings: ${err.message}`, 'error');
    }
  }

  // --- Export & Sharing ---
  function handleDownloadMarkdown() {
    if (!state.currentNotes) return;
    const md = formatNotesMarkdown(state.currentNotes);
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(state.currentNotes.title || 'Meeting_Notes').replace(/[^a-zA-Z0-9_-]/g, '_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Markdown document exported!');
  }

  function setActionButtonsDisabled(disabled) {
    const actionBtns = [
      els.results.regenerateNotesBtn,
      els.results.copyNotesBtn,
      els.results.downloadMdBtn,
      els.results.resendEmailBtn,
      els.results.newMeetingBtn,
      els.results.downloadTranscriptBtn,
      els.results.copyTranscriptBtn,
    ];
    actionBtns.forEach((btn) => {
      if (btn) btn.disabled = !!disabled;
    });
  }

  async function handleRegenerateNotes() {
    if (state.isRegenerating) return;
    state.isRegenerating = true;

    const btn = els.results.regenerateNotesBtn;
    const originalBtnHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.innerHTML = '<span class="btn-spinner"></span><span>Regenerating...</span>';
    }
    setActionButtonsDisabled(true);

    showToast('Re-triggering Ollama notes generation...', 'info');
    showView('processing');
    resetProcessingStepper();
    
    // Set processing view to Step 3 (LLM synthesis)
    els.processing.barFill.style.width = '60%';
    els.processing.subtitle.innerText = 'Re-running local Ollama LLM synthesis...';
    els.processing.steps.forEach((s, idx) => {
      s.classList.toggle('completed', idx < 2);
      s.classList.toggle('active', idx === 2);
    });

    const logLine = document.createElement('div');
    logLine.className = 'log-line';
    logLine.innerText = `[${new Date().toLocaleTimeString()}] Re-generating structured notes with model: ${state.settings.ollama_model || 'llama3'} (Timeout: ${state.settings.ollama_timeout || 300}s)`;
    els.processing.log.appendChild(logLine);

    try {
      const endpoint = state.currentSessionId
        ? `/api/sessions/${state.currentSessionId}/regenerate`
        : '/api/session/regenerate';

      const res = await fetch(endpoint, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Regeneration failed');
      }

      const data = await res.json();
      state.currentNotes = data.notes;

      // Complete processing stepper
      els.processing.barFill.style.width = '100%';
      els.processing.subtitle.innerText = 'Notes generation completed!';
      els.processing.steps.forEach((s) => {
        s.classList.remove('active');
        s.classList.add('completed');
      });

      setTimeout(() => {
        renderResults(data.notes);
        showView('results');
        showToast('Meeting notes regenerated successfully!');
      }, 800);
    } catch (e) {
      showToast(`Regeneration error: ${e.message}`, 'error');
      if (!state.currentNotes) {
        state.currentNotes = {
          title: 'Meeting Notes',
          summary: `(Note generation failed after retries: ${e.message})`,
          error: e.message,
          action_items: [],
          highlights: [],
          decisions: [],
          transcript: els.results.transcriptText ? els.results.transcriptText.innerText : '',
        };
      } else {
        state.currentNotes.error = e.message;
        state.currentNotes.action_items = [];
        state.currentNotes.highlights = [];
        state.currentNotes.decisions = [];
      }
      renderResults(state.currentNotes);
      showView('results');
    } finally {
      state.isRegenerating = false;
      if (btn) btn.innerHTML = originalBtnHtml;
      setActionButtonsDisabled(false);
    }
  }

  function handleDownloadTranscript() {
    const text = els.results.transcriptText ? els.results.transcriptText.innerText : '';
    if (!text || text === 'No transcript available.') {
      showToast('No transcript content available to export', 'error');
      return;
    }

    const title = (state.currentNotes && state.currentNotes.title) ? state.currentNotes.title : 'Meeting_Transcript';
    const filename = `${title.replace(/[^a-zA-Z0-9_-]/g, '_')}_Transcript.txt`;

    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Transcript text file exported!');
  }

  async function handleResendEmail() {
    if (!state.currentSessionId) return;
    try {
      const res = await fetch(`/api/sessions/${state.currentSessionId}/resend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      if (res.ok) {
        showToast('Meeting notes email sent successfully!');
      } else {
        const err = await res.json();
        showToast(`Email failed: ${err.detail}`, 'error');
      }
    } catch (e) {
      showToast(`Error: ${e.message}`, 'error');
    }
  }

  function formatNotesMarkdown(notes) {
    let md = `# 📝 ${notes.title || 'Meeting Notes'}\n\n`;
    md += `**Duration:** ${notes.duration || 'Unknown'} | **Date:** ${new Date().toLocaleDateString()}\n\n---\n\n`;
    md += `## 📋 Executive Summary\n${notes.summary || ''}\n\n`;

    if (notes.action_items && notes.action_items.length) {
      md += `## ✅ Action Items\n`;
      notes.action_items.forEach((item) => {
        if (typeof item === 'object') {
          md += `- [ ] **${item.owner || 'Unassigned'}**: ${item.action || ''} *(Due: ${item.deadline || 'N/A'})*\n`;
        } else {
          md += `- [ ] ${item}\n`;
        }
      });
      md += '\n';
    }

    if (notes.highlights && notes.highlights.length) {
      md += `## 💡 Key Highlights\n`;
      notes.highlights.forEach((h) => (md += `- ${h}\n`));
      md += '\n';
    }

    if (notes.decisions && notes.decisions.length) {
      md += `## 🎯 Decisions Made\n`;
      notes.decisions.forEach((d) => (md += `- ${d}\n`));
      md += '\n';
    }

    const t = notes.timestamped_transcript || notes.transcript || '';
    if (t) {
      md += `## 🎙️ Transcript\n\n${t}\n`;
    }
    return md;
  }

  function copyToClipboard(text, successMsg) {
    navigator.clipboard.writeText(text).then(
      () => showToast(successMsg),
      () => showToast('Failed to copy', 'error')
    );
  }

  // --- Toasts & Helpers ---
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerText = message;
    els.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 250);
    }, 3000);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Start initialization
  document.addEventListener('DOMContentLoaded', init);
})();

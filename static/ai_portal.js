/**
 * AI Chat Portal — MedGemma
 * Handles patient selection, manual entry, image upload, canvas annotation, and chat.
 */

// ── State ─────────────────────────────────────────────────────────────────────

const portalState = {
    mode: 'patient',            // 'patient' | 'manual'
    selectedPatient: null,      // full patient summary object
    patientId: null,

    // Image
    imageDataUrl: null,         // base64 data URL of loaded image
    imageFile: null,            // File object
    imageModality: 'xray',
    imageName: '',

    // Annotations
    annotations: [],            // [{id, x, y, w, h, label}]  — normalised 0-1
    annotationCounter: 0,

    // Canvas drawing state
    drawTool: 'view',           // 'view' | 'annotate'
    isDrawing: false,
    drawStart: null,

    // Chat
    chatHistory: [],            // [{role, content, imageDataUrl?, annotations?}]
    isGenerating: false,

    // Chat-attached image (separate from center-panel image)
    chatAttachedImage: null,    // {dataUrl, name, modality, annotations}

    // Audio
    audioContext: null,
    mediaRecorder: null,
    audioChunks: [],
    manualRecording: false,
    chatRecording: false,
    activeRecordTarget: null,   // 'manual' | 'chat'
};

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    loadPatients();
    setupImageDragDrop();
    setupCanvas();
});

// ── Mode switch ───────────────────────────────────────────────────────────────

function setMode(mode) {
    portalState.mode = mode;

    document.getElementById('modePatientBtn').classList.toggle('active', mode === 'patient');
    document.getElementById('modeManualBtn').classList.toggle('active', mode === 'manual');
    document.getElementById('patientMode').classList.toggle('hidden', mode !== 'patient');
    document.getElementById('manualMode').classList.toggle('hidden', mode !== 'manual');

    updateContextBadge();
}

function updateContextBadge() {
    const badge = document.getElementById('contextBadge');
    badge.classList.remove('hidden');
    if (portalState.mode === 'patient' && portalState.selectedPatient) {
        const p = portalState.selectedPatient.patient || {};
        badge.textContent = p.name || 'Patient selected';
        badge.className = 'context-badge';
    } else if (portalState.mode === 'manual') {
        badge.textContent = 'Manual entry';
        badge.className = 'context-badge manual';
    } else {
        badge.textContent = 'No patient';
        badge.className = 'context-badge';
    }
}

// ── Patient loading ───────────────────────────────────────────────────────────

async function loadPatients() {
    try {
        const res = await fetch('/api/patients');
        const data = await res.json();
        renderPatientSelector(data.patients);
    } catch (e) {
        document.getElementById('patientSelector').innerHTML =
            '<p style="color:var(--text-secondary); font-size:0.85rem;">Failed to load patients.</p>';
    }
}

function renderPatientSelector(patients) {
    const el = document.getElementById('patientSelector');
    if (!patients || patients.length === 0) {
        el.innerHTML = '<p style="color:var(--text-secondary); font-size:0.85rem;">No patients found.</p>';
        return;
    }
    el.innerHTML = patients.map(p => {
        const age = calcAge(p.birthDate);
        return `<div class="patient-option" onclick="selectPatient('${p.id}')" data-id="${p.id}">
            <div class="patient-opt-name">${p.name}</div>
            <div class="patient-opt-details">${age} yr • ${p.gender}</div>
        </div>`;
    }).join('');
}

function calcAge(birthDate) {
    if (!birthDate) return '?';
    const birth = new Date(birthDate);
    const now = new Date();
    let age = now.getFullYear() - birth.getFullYear();
    if (now.getMonth() < birth.getMonth() ||
        (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())) age--;
    return age;
}

async function selectPatient(patientId) {
    // Highlight selection
    document.querySelectorAll('.patient-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.id === patientId);
    });

    try {
        const res = await fetch(`/api/patients/${patientId}`);
        if (!res.ok) throw new Error('Patient not found');
        const data = await res.json();

        portalState.selectedPatient = data;
        portalState.patientId = patientId;

        // Hide selector, show details
        document.getElementById('patientSelector').classList.add('hidden');
        document.getElementById('patientDetails').classList.remove('hidden');

        renderPatientDetails(data);
        updateContextBadge();
        showToast('Patient loaded');
    } catch (e) {
        showToast('Failed to load patient', 'error');
    }
}

function renderPatientDetails(data) {
    const p = data.patient || {};
    let html = `
        <div style="font-weight:700; font-size:1rem; margin-bottom:0.35rem;">${p.name || 'Unknown'}</div>
        <div style="font-size:0.82rem; color:var(--text-secondary); margin-bottom:1rem;">
            ${p.age || '?'} yr • ${p.gender || ''} • ${p.location || ''}
        </div>`;

    if (data.conditions && data.conditions.length > 0) {
        html += `<div class="summary-label">Conditions</div><div class="summary-chips">
            ${data.conditions.map(c => `<span class="chip-sm">${c.name}</span>`).join('')}
        </div>`;
    }
    if (data.medications && data.medications.length > 0) {
        html += `<div class="summary-label">Medications</div><div class="summary-chips">
            ${data.medications.map(m => `<span class="chip-sm">${m.name}</span>`).join('')}
        </div>`;
    }
    if (data.allergies && data.allergies.length > 0) {
        html += `<div class="summary-label">Allergies</div><div class="summary-chips">
            ${data.allergies.map(a => `<span class="chip-sm allergy">${a.substance}</span>`).join('')}
        </div>`;
    }

    // Images stored in patient record
    if (data.images && data.images.length > 0) {
        html += `<div class="summary-label">Existing Images</div><div style="display:flex; flex-direction:column; gap:0.4rem;">`;
        data.images.forEach(img => {
            const date = new Date(img.timestamp).toLocaleDateString();
            html += `<button class="tool-btn" style="text-align:left; font-size:0.78rem;"
                onclick="loadPatientImage('${img.url}', '${img.modality || 'xray'}', '${img.analysis || ''}')">
                🖼 ${(img.modality || 'imaging').toUpperCase()} — ${date}
            </button>`;
        });
        html += `</div>`;
    }

    document.getElementById('patientSummaryContent').innerHTML = html;
}

function clearPatient() {
    portalState.selectedPatient = null;
    portalState.patientId = null;
    document.getElementById('patientSelector').classList.remove('hidden');
    document.querySelectorAll('.patient-option').forEach(el => el.classList.remove('selected'));
    document.getElementById('patientDetails').classList.add('hidden');
    updateContextBadge();
}

async function loadPatientImage(url, modality, preExistingAnalysis) {
    try {
        const res = await fetch(url);
        const blob = await res.blob();
        const file = new File([blob], url.split('/').pop() || 'image.jpg', { type: blob.type });
        await displayImageFile(file, modality);
        if (preExistingAnalysis) {
            showToast('Image loaded with existing analysis');
        } else {
            showToast('Image loaded');
        }
    } catch (e) {
        showToast('Failed to load patient image', 'error');
    }
}

// ── Image handling ────────────────────────────────────────────────────────────

function setupImageDragDrop() {
    const zone = document.getElementById('imageDropZone');
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor = 'var(--primary)'; });
    zone.addEventListener('dragleave', () => { zone.style.borderColor = ''; });
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.style.borderColor = '';
        if (e.dataTransfer.files.length > 0 && !portalState.imageDataUrl) {
            handleImageFile({ files: e.dataTransfer.files });
        }
    });
}

function onDropZoneClick() {
    if (portalState.drawTool === 'annotate' && portalState.imageDataUrl) return;
    if (!portalState.imageDataUrl) {
        document.getElementById('imageFileInput').click();
    }
}

function handleImageFile(input) {
    const file = input.files ? input.files[0] : null;
    if (!file) return;
    if (!file.type.startsWith('image/')) {
        showToast('Please select an image file', 'error');
        return;
    }
    displayImageFile(file, document.getElementById('imagingModality').value);
}

async function displayImageFile(file, modality) {
    return new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = e => {
            portalState.imageDataUrl = e.target.result;
            portalState.imageFile = file;
            portalState.imageName = file.name;
            portalState.imageModality = modality || document.getElementById('imagingModality').value;
            portalState.annotations = [];

            const img = document.getElementById('baseImage');
            img.src = e.target.result;
            img.onload = () => {
                fitCanvasToImage();
                resolve();
            };

            document.getElementById('dropPlaceholder').classList.add('hidden');
            document.getElementById('canvasWrapper').classList.add('visible');
            document.getElementById('imageToolbar').style.display = '';
            document.getElementById('clearImageBtn').style.display = '';
            document.getElementById('attachImageBtn').style.display = '';
            showToast('Image loaded — use Annotate tool to mark regions');
        };
        reader.readAsDataURL(file);
    });
}

function clearImage() {
    portalState.imageDataUrl = null;
    portalState.imageFile = null;
    portalState.annotations = [];

    document.getElementById('baseImage').src = '';
    document.getElementById('canvasWrapper').classList.remove('visible');
    document.getElementById('dropPlaceholder').classList.remove('hidden');
    document.getElementById('imageToolbar').style.display = 'none';
    document.getElementById('clearImageBtn').style.display = 'none';
    document.getElementById('attachImageBtn').style.display = 'none';

    const canvas = document.getElementById('annotationCanvas');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    setTool('view');
    renderAnnotationList();
}

// ── Canvas annotation ─────────────────────────────────────────────────────────

function setupCanvas() {
    const canvas = document.getElementById('annotationCanvas');
    canvas.addEventListener('mousedown', onCanvasMouseDown);
    canvas.addEventListener('mousemove', onCanvasMouseMove);
    canvas.addEventListener('mouseup', onCanvasMouseUp);
    canvas.addEventListener('mouseleave', onCanvasMouseUp);
}

function fitCanvasToImage() {
    const img = document.getElementById('baseImage');
    const canvas = document.getElementById('annotationCanvas');
    // Match canvas pixel dims to the rendered image size
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.style.width = img.offsetWidth + 'px';
    canvas.style.height = img.offsetHeight + 'px';
    canvas.style.top = img.offsetTop + 'px';
    canvas.style.left = img.offsetLeft + 'px';
    redrawAnnotations();
}

window.addEventListener('resize', () => {
    if (portalState.imageDataUrl) fitCanvasToImage();
});

function setTool(tool) {
    portalState.drawTool = tool;
    document.getElementById('toolView').classList.toggle('active', tool === 'view');
    document.getElementById('toolAnnotate').classList.toggle('active', tool === 'annotate');

    const canvas = document.getElementById('annotationCanvas');
    const hint = document.getElementById('annotationHint');
    if (tool === 'annotate') {
        canvas.style.pointerEvents = 'auto';
        hint.classList.remove('hidden');
    } else {
        canvas.style.pointerEvents = 'none';
        hint.classList.add('hidden');
    }
}

function onCanvasMouseDown(e) {
    if (portalState.drawTool !== 'annotate') return;
    portalState.isDrawing = true;
    const pos = canvasPos(e);
    portalState.drawStart = pos;
}

function onCanvasMouseMove(e) {
    if (!portalState.isDrawing) return;
    const pos = canvasPos(e);
    const canvas = document.getElementById('annotationCanvas');
    const ctx = canvas.getContext('2d');
    redrawAnnotations(ctx);

    const { x: sx, y: sy } = portalState.drawStart;
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = Math.max(2, canvas.width / 300);
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(sx, sy, pos.x - sx, pos.y - sy);
    ctx.setLineDash([]);
}

function onCanvasMouseUp(e) {
    if (!portalState.isDrawing) return;
    portalState.isDrawing = false;
    const pos = canvasPos(e);
    const { x: sx, y: sy } = portalState.drawStart;

    const w = pos.x - sx;
    const h = pos.y - sy;
    if (Math.abs(w) < 10 || Math.abs(h) < 10) {
        redrawAnnotations();
        return; // too small — ignore
    }

    const canvas = document.getElementById('annotationCanvas');
    // Normalise to 0-1 relative to canvas
    const annotation = {
        id: ++portalState.annotationCounter,
        x: Math.min(sx, pos.x) / canvas.width,
        y: Math.min(sy, pos.y) / canvas.height,
        w: Math.abs(w) / canvas.width,
        h: Math.abs(h) / canvas.height,
        label: `Region ${portalState.annotationCounter}`,
    };
    portalState.annotations.push(annotation);
    redrawAnnotations();
    renderAnnotationList();
    showToast(`Annotation ${annotation.id} added`);
}

function canvasPos(e) {
    const canvas = document.getElementById('annotationCanvas');
    const rect = canvas.getBoundingClientRect();
    // Scale mouse coords to canvas natural resolution
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY,
    };
}

function redrawAnnotations(ctx) {
    const canvas = document.getElementById('annotationCanvas');
    if (!ctx) ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    portalState.annotations.forEach(ann => {
        const x = ann.x * canvas.width;
        const y = ann.y * canvas.height;
        const w = ann.w * canvas.width;
        const h = ann.h * canvas.height;
        const lw = Math.max(2, canvas.width / 300);

        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = lw + 1;
        ctx.strokeStyle = 'rgba(0,0,0,0.5)';
        ctx.strokeRect(x, y, w, h);
        ctx.lineWidth = lw;
        ctx.strokeStyle = '#f59e0b';
        ctx.strokeRect(x, y, w, h);

        // Label
        ctx.font = `${Math.max(12, canvas.width / 60)}px Inter, sans-serif`;
        ctx.fillStyle = '#f59e0b';
        const labelY = y > 20 ? y - 4 : y + h + 16;
        ctx.fillText(ann.label, x + 2, labelY);
    });
}

function clearAnnotations() {
    portalState.annotations = [];
    redrawAnnotations();
    renderAnnotationList();
}

function removeAnnotation(id) {
    portalState.annotations = portalState.annotations.filter(a => a.id !== id);
    redrawAnnotations();
    renderAnnotationList();
}

function renderAnnotationList() {
    const el = document.getElementById('annotationList');
    if (portalState.annotations.length === 0) {
        el.innerHTML = '<span style="color:var(--text-secondary);">No annotations</span>';
        return;
    }
    el.innerHTML = portalState.annotations.map(a =>
        `<span class="annotation-tag">
            📐 ${a.label}
            <button onclick="removeAnnotation(${a.id})" title="Remove">✕</button>
        </span>`
    ).join('');
}

// ── Attach image to chat ──────────────────────────────────────────────────────

function attachImageToChat() {
    if (!portalState.imageDataUrl) {
        showToast('No image loaded', 'error');
        return;
    }
    portalState.chatAttachedImage = {
        dataUrl: portalState.imageDataUrl,
        name: portalState.imageName,
        modality: document.getElementById('imagingModality').value,
        annotations: [...portalState.annotations],
    };
    renderAttachedItems();
    showToast('Image attached to next message');
}

function triggerImageAttach() {
    if (!portalState.imageDataUrl) {
        // Open file picker directly
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.onchange = async (e) => {
            if (e.target.files.length > 0) {
                await displayImageFile(e.target.files[0]);
                attachImageToChat();
            }
        };
        input.click();
    } else {
        attachImageToChat();
    }
}

function removeAttachedImage() {
    portalState.chatAttachedImage = null;
    renderAttachedItems();
}

function renderAttachedItems() {
    const container = document.getElementById('attachedItems');
    if (!portalState.chatAttachedImage) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }
    const annText = portalState.chatAttachedImage.annotations.length > 0
        ? ` + ${portalState.chatAttachedImage.annotations.length} annotation(s)` : '';
    container.style.display = 'flex';
    container.innerHTML = `<span class="attach-tag">
        🩻 ${portalState.chatAttachedImage.modality.toUpperCase()} — ${portalState.chatAttachedImage.name}${annText}
        <button onclick="removeAttachedImage()" title="Remove">✕</button>
    </span>`;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

function onChatKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text && !portalState.chatAttachedImage) return;
    if (portalState.isGenerating) return;

    const msg = {
        role: 'user',
        content: text || '(Image attached — please analyze)',
        imageDataUrl: portalState.chatAttachedImage ? portalState.chatAttachedImage.dataUrl : null,
        imageName: portalState.chatAttachedImage ? portalState.chatAttachedImage.name : null,
        imageModality: portalState.chatAttachedImage ? portalState.chatAttachedImage.modality : null,
        annotations: portalState.chatAttachedImage ? portalState.chatAttachedImage.annotations : [],
    };

    portalState.chatHistory.push(msg);
    renderMessage(msg);

    // Clear input + attachment
    input.value = '';
    input.style.height = 'auto';
    portalState.chatAttachedImage = null;
    renderAttachedItems();

    // Show typing indicator
    showTyping();
    portalState.isGenerating = true;
    document.getElementById('sendBtn').disabled = true;

    try {
        const requestBody = buildRequestBody(msg);
        const res = await fetch('/api/ai-portal/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }

        const data = await res.json();
        hideTyping();

        const assistantMsg = {
            role: 'assistant',
            content: data.response || '(No response)'
        };
        portalState.chatHistory.push(assistantMsg);
        renderMessage(assistantMsg);

    } catch (e) {
        hideTyping();
        const errMsg = {
            role: 'assistant',
            content: `Error: ${e.message}`
        };
        portalState.chatHistory.push(errMsg);
        renderMessage(errMsg);
    } finally {
        portalState.isGenerating = false;
        document.getElementById('sendBtn').disabled = false;
        scrollChatToBottom();
    }
}

function buildRequestBody(userMsg) {
    // Patient context
    let patientContext = null;
    if (portalState.mode === 'patient' && portalState.selectedPatient) {
        patientContext = portalState.selectedPatient;
    } else if (portalState.mode === 'manual') {
        const manual = document.getElementById('manualContext').value.trim();
        if (manual) patientContext = { freeText: manual };
    }

    // Chat history (text only — no repeated images)
    const history = portalState.chatHistory.slice(0, -1).map(m => ({
        role: m.role,
        content: m.content,
    }));

    const body = {
        message: userMsg.content,
        history,
        patient_context: patientContext,
    };

    if (userMsg.imageDataUrl) {
        body.image_data = userMsg.imageDataUrl;
        body.image_modality = userMsg.imageModality || 'xray';
        body.image_name = userMsg.imageName || 'image.jpg';
    }

    if (userMsg.annotations && userMsg.annotations.length > 0) {
        body.annotations = userMsg.annotations;
    }

    return body;
}

// ── Chat rendering ────────────────────────────────────────────────────────────

function renderMessage(msg) {
    const container = document.getElementById('chatMessages');

    // Remove empty state
    const empty = document.getElementById('chatEmpty');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = `chat-msg ${msg.role}`;

    const roleLabel = msg.role === 'user' ? 'You' : 'MedGemma';

    let bubbleContent = '';
    let bubbleClass = 'msg-bubble';

    if (msg.role === 'assistant' && typeof marked !== 'undefined') {
        // Render markdown for assistant messages
        bubbleClass += ' markdown';
        bubbleContent = marked.parse(msg.content, { breaks: true });
    } else {
        bubbleContent = escapeHtml(msg.content);
    }

    let extra = '';
    if (msg.imageDataUrl) {
        extra += `<img src="${msg.imageDataUrl}" class="msg-image-thumb" alt="attached image">`;
    }
    if (msg.annotations && msg.annotations.length > 0) {
        extra += `<span class="msg-annotation-badge">📐 ${msg.annotations.length} region(s) annotated</span>`;
    }

    div.innerHTML = `
        <span class="msg-role">${roleLabel}</span>
        <div class="${bubbleClass}">${bubbleContent}</div>
        ${extra}
    `;

    container.appendChild(div);
    scrollChatToBottom();
}

function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
}

let typingEl = null;

function showTyping() {
    const container = document.getElementById('chatMessages');
    const empty = document.getElementById('chatEmpty');
    if (empty) empty.remove();

    typingEl = document.createElement('div');
    typingEl.className = 'chat-msg assistant';
    typingEl.innerHTML = `
        <span class="msg-role">MedGemma</span>
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>`;
    container.appendChild(typingEl);
    scrollChatToBottom();
}

function hideTyping() {
    if (typingEl) {
        typingEl.remove();
        typingEl = null;
    }
}

function scrollChatToBottom() {
    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

function clearChat() {
    portalState.chatHistory = [];
    const container = document.getElementById('chatMessages');
    container.innerHTML = `<div class="chat-empty" id="chatEmpty">
        <div class="icon">💬</div>
        <p>Ask MedGemma anything about this patient.<br>Attach an image and annotate regions of interest for focused analysis.</p>
    </div>`;
}

// ── Audio recording (manual entry + chat) ─────────────────────────────────────

async function toggleManualRecording() {
    if (portalState.manualRecording) {
        stopRecording('manual');
    } else {
        await startRecording('manual');
    }
}

async function toggleChatRecording() {
    if (portalState.chatRecording) {
        stopRecording('chat');
    } else {
        await startRecording('chat');
    }
}

async function startRecording(target) {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        portalState.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        portalState.mediaRecorder = new MediaRecorder(stream);
        portalState.audioChunks = [];
        portalState.activeRecordTarget = target;

        portalState.mediaRecorder.ondataavailable = e => portalState.audioChunks.push(e.data);
        portalState.mediaRecorder.onstop = () => handleRecordingStop(target, stream);
        portalState.mediaRecorder.start();

        if (target === 'manual') {
            portalState.manualRecording = true;
            document.getElementById('manualRecordBtn').classList.add('recording');
            document.getElementById('manualRecIndicator').classList.remove('hidden');
        } else {
            portalState.chatRecording = true;
            document.getElementById('chatRecordBtn').classList.add('recording');
            document.getElementById('chatRecIndicator').classList.remove('hidden');
        }
    } catch (e) {
        showToast('Microphone access denied', 'error');
    }
}

function stopRecording(target) {
    if (portalState.mediaRecorder && portalState.mediaRecorder.state !== 'inactive') {
        portalState.mediaRecorder.stop();
    }
    if (target === 'manual') {
        portalState.manualRecording = false;
        document.getElementById('manualRecordBtn').classList.remove('recording');
        document.getElementById('manualRecIndicator').classList.add('hidden');
    } else {
        portalState.chatRecording = false;
        document.getElementById('chatRecordBtn').classList.remove('recording');
        document.getElementById('chatRecIndicator').classList.add('hidden');
    }
}

async function handleRecordingStop(target, stream) {
    stream.getTracks().forEach(t => t.stop());

    const blob = new Blob(portalState.audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');

    showToast('Transcribing…');

    try {
        const res = await fetch('/api/ai-portal/transcribe', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        const text = data.text || '';

        if (target === 'manual') {
            const ta = document.getElementById('manualContext');
            ta.value = (ta.value + ' ' + text).trim();
        } else {
            const chatIn = document.getElementById('chatInput');
            chatIn.value = (chatIn.value + ' ' + text).trim();
            autoResize(chatIn);
        }
        showToast('Transcribed');
    } catch (e) {
        showToast('Transcription failed', 'error');
    }
}

async function handleManualAudioUpload(input) {
    const file = input.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('audio', file);
    showToast('Transcribing audio file…');

    try {
        const res = await fetch('/api/ai-portal/transcribe', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        const ta = document.getElementById('manualContext');
        ta.value = (ta.value + ' ' + (data.text || '')).trim();
        showToast('Audio transcribed');
    } catch (e) {
        showToast('Transcription failed', 'error');
    } finally {
        input.value = '';
    }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

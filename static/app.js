/**
 * MedGemma Clinical Assistant - Frontend Application
 * Handles patient selection, audio recording, image upload, and SOAP workflow
 */

// Application State
const state = {
    sessionId: null,
    patientId: null,
    patient: null,
    isRecording: false,
    transcription: '',
    audioContext: null,
    mediaRecorder: null,
    audioSocket: null,
    soapGenerated: false,
    modelStatusInterval: null   // polling timer for model sleep/wake status
};

// DOM Elements
const elements = {
    patientSelection: document.getElementById('patientSelection'),
    patientList: document.getElementById('patientList'),
    clinicalEncounter: document.getElementById('clinicalEncounter'),
    patientInfo: document.getElementById('patientInfo'),
    imageUploadArea: document.getElementById('imageUploadArea'),
    uploadPlaceholder: document.getElementById('uploadPlaceholder'),
    previewImage: document.getElementById('previewImage'),
    imageInput: document.getElementById('imageInput'),
    modalitySelect: document.getElementById('modalitySelect'),
    imageAnalysis: document.getElementById('imageAnalysis'),
    analysisContent: document.getElementById('analysisContent'),
    recordBtn: document.getElementById('recordBtn'),
    recordingIndicator: document.getElementById('recordingIndicator'),
    transcriptionArea: document.getElementById('transcriptionArea'),
    soapContent: document.getElementById('soapContent'),
    soapStatus: document.getElementById('soapStatus'),
    soapActions: document.getElementById('soapActions'),
    alertsCard: document.getElementById('alertsCard'),
    alertsContent: document.getElementById('alertsContent'),
    statusIndicator: document.getElementById('statusIndicator'),
    toastContainer: document.getElementById('toastContainer'),
    confirmModal: document.getElementById('confirmModal'),
    dbImageSelect: document.getElementById('dbImageSelect'),
    // Model status bar
    modelStatusBar: document.getElementById('modelStatusBar'),
    modelStatusHint: document.getElementById('modelStatusHint'),
};

// Initialize application
document.addEventListener('DOMContentLoaded', init);

async function init() {
    await loadPatients();
    setupImageUpload();
    setupDragAndDrop();
}

// ===== Patient Management =====

async function loadPatients() {
    try {
        const response = await fetch('/api/patients');
        const data = await response.json();
        renderPatientList(data.patients);
    } catch (error) {
        showToast('Failed to load patients', 'error');
        console.error('Error loading patients:', error);
    }
}

function renderPatientList(patients) {
    elements.patientList.innerHTML = patients.map(patient => {
        const initials = patient.name.split(' ').map(n => n[0]).join('');
        const age = calculateAge(patient.birthDate);
        return `
            <div class="patient-item" onclick="selectPatient('${patient.id}')">
                <div class="patient-avatar">${initials}</div>
                <div class="patient-item-info">
                    <div class="patient-item-name">${patient.name}</div>
                    <div class="patient-item-details">${age} years • ${patient.gender}</div>
                </div>
                <span>→</span>
            </div>
        `;
    }).join('');
}

function calculateAge(birthDate) {
    const birth = new Date(birthDate);
    const today = new Date();
    let age = today.getFullYear() - birth.getFullYear();
    const monthDiff = today.getMonth() - birth.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
        age--;
    }
    return age;
}

async function selectPatient(patientId) {
    try {
        // Start encounter
        const formData = new FormData();
        formData.append('patient_id', patientId);

        const response = await fetch('/api/encounters/start', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        state.sessionId = data.session_id;
        state.patientId = patientId;
        state.patient = data.patient;

        // Update UI
        renderPatientInfo(data);

        // Switch to encounter view
        elements.patientSelection.classList.add('hidden');
        elements.clinicalEncounter.classList.remove('hidden');

        // Show model status bar and start polling
        elements.modelStatusBar.classList.remove('hidden');
        startModelStatusPolling();

        updateStatus('Encounter Active');
        showToast('Encounter started');

    } catch (error) {
        showToast('Failed to start encounter', 'error');
        console.error('Error starting encounter:', error);
    }
}

function renderPatientInfo(data) {
    const p = data.patient;
    elements.patientInfo.innerHTML = `
        <div class="patient-name">${p.name}</div>
        <div class="patient-demographics">${p.age} years • ${p.gender} • ${p.location}</div>
        
        ${data.conditions && data.conditions.length > 0 ? `
            <div class="patient-section">
                <div class="patient-section-title">Conditions</div>
                <div class="patient-section-content">
                    ${data.conditions.map(c => `<span class="tag">${c.name}</span>`).join('')}
                </div>
            </div>
        ` : ''}
        
        ${data.medications && data.medications.length > 0 ? `
            <div class="patient-section">
                <div class="patient-section-title">Medications</div>
                <div class="patient-section-content">
                    ${data.medications.map(m => `<span class="tag">${m.name}</span>`).join('')}
                </div>
            </div>
        ` : ''}
        
        ${data.allergies && data.allergies.length > 0 ? `
            <div class="patient-section">
                <div class="patient-section-title">Allergies</div>
                <div class="patient-section-content">
                    ${data.allergies.map(a => `<span class="tag allergy">${a.substance}</span>`).join('')}
                </div>
            </div>
        ` : ''}
        
        ${data.recent_observations && data.recent_observations.length > 0 ? `
            <div class="patient-section">
                <div class="patient-section-title">Recent Observations</div>
                <div class="patient-section-content">
                    ${data.recent_observations.slice(0, 4).map(o =>
        `<div style="font-size: 0.8rem; margin-bottom: 4px;">${o.type}: <strong>${o.value}</strong></div>`
    ).join('')}
                </div>
            </div>
        ` : ''}
    `;

    // Populate image dropdown if images exist
    elements.dbImageSelect.innerHTML = '<option value="">-- Select an image --</option>';
    if (data.images && data.images.length > 0) {
        data.images.forEach(img => {
            const opt = document.createElement('option');
            opt.value = img.url;
            opt.textContent = `${img.modality.toUpperCase()} - ${new Date(img.timestamp).toLocaleDateString()}`;
            opt.dataset.analysis = img.analysis || '';
            opt.dataset.modality = img.modality || 'xray';
            elements.dbImageSelect.appendChild(opt);
        });
    } else {
        elements.dbImageSelect.innerHTML = '<option value="">-- No existing images --</option>';
    }
}

function endEncounter() {
    // Reset state
    state.sessionId = null;
    state.patientId = null;
    state.patient = null;
    state.transcription = '';
    state.soapGenerated = false;

    // Stop recording if active
    if (state.isRecording) {
        toggleRecording();
    }

    // Stop model status polling and hide bar
    stopModelStatusPolling();
    elements.modelStatusBar.classList.add('hidden');

    // Reset UI
    elements.clinicalEncounter.classList.add('hidden');
    elements.patientSelection.classList.remove('hidden');
    elements.transcriptionArea.value = '';
    elements.soapContent.innerHTML = `
        <div class="soap-placeholder">
            <span class="placeholder-icon">📋</span>
            <p>SOAP note will appear here after generation</p>
        </div>
    `;
    elements.soapActions.classList.add('hidden');
    elements.alertsCard.classList.add('hidden');
    elements.imageAnalysis.classList.add('hidden');
    elements.previewImage.classList.add('hidden');
    elements.uploadPlaceholder.classList.remove('hidden');
    elements.previewImage.src = '';

    updateStatus('Ready');
}

// ===== Image Upload =====

function setupImageUpload() {
    elements.imageUploadArea.addEventListener('click', () => {
        elements.imageInput.click();
    });

    elements.imageInput.addEventListener('change', handleImageSelect);
}

function setupDragAndDrop() {
    elements.imageUploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.imageUploadArea.classList.add('drag-over');
    });

    elements.imageUploadArea.addEventListener('dragleave', () => {
        elements.imageUploadArea.classList.remove('drag-over');
    });

    elements.imageUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.imageUploadArea.classList.remove('drag-over');

        if (e.dataTransfer.files.length > 0) {
            handleImageFile(e.dataTransfer.files[0]);
        }
    });
}

function handleImageSelect(e) {
    if (e.target.files.length > 0) {
        handleImageFile(e.target.files[0]);
    }
}

async function handleImageFile(file) {
    if (!file.type.startsWith('image/')) {
        showToast('Please select an image file', 'error');
        return;
    }

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        elements.previewImage.src = e.target.result;
        elements.previewImage.classList.remove('hidden');
        elements.uploadPlaceholder.classList.add('hidden');
    };
    reader.readAsDataURL(file);

    // Upload to server
    try {
        const formData = new FormData();
        formData.append('image', file);
        formData.append('modality', elements.modalitySelect.value);

        showToast('Analyzing image...');

        const response = await fetch(`/api/encounters/${state.sessionId}/image`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.analysis) {
            elements.imageAnalysis.classList.remove('hidden');
            elements.analysisContent.textContent = data.analysis;
            showToast('Image analyzed', 'success');
        } else {
            showToast('Image uploaded (analysis pending model load)');
        }

    } catch (error) {
        showToast('Failed to upload image', 'error');
        console.error('Error uploading image:', error);
    }
}

async function loadDatabaseImage(imageUrl) {
    if (!imageUrl) {
        elements.previewImage.classList.add('hidden');
        elements.uploadPlaceholder.classList.remove('hidden');
        elements.imageAnalysis.classList.add('hidden');
        return;
    }

    const selectedOption = elements.dbImageSelect.options[elements.dbImageSelect.selectedIndex];

    // Show preview
    elements.previewImage.src = imageUrl;
    elements.previewImage.classList.remove('hidden');
    elements.uploadPlaceholder.classList.add('hidden');
    elements.modalitySelect.value = selectedOption.dataset.modality || "xray";

    // Show existing analysis if available
    const analysis = selectedOption.dataset.analysis;
    if (analysis) {
        elements.imageAnalysis.classList.remove('hidden');
        elements.analysisContent.textContent = analysis;
    } else {
        elements.imageAnalysis.classList.add('hidden');
    }
}

// ===== Audio Recording =====

async function toggleRecording() {
    if (state.isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    try {
        // Request microphone access
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true
            }
        });

        // Create audio context
        state.audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000
        });

        // Connect to WebSocket for streaming
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        state.audioSocket = new WebSocket(`${wsProtocol}//${window.location.host}/ws/audio/${state.sessionId}`);

        state.audioSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'transcription' && data.text) {
                state.transcription = data.text;
                updateTranscriptionDisplay();
            }
        };

        state.audioSocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            showToast('Audio connection error', 'error');
        };

        // Set up audio processing
        const source = state.audioContext.createMediaStreamSource(stream);
        const processor = state.audioContext.createScriptProcessor(4096, 1, 1);

        processor.onaudioprocess = (e) => {
            if (state.isRecording && state.audioSocket?.readyState === WebSocket.OPEN) {
                const inputData = e.inputBuffer.getChannelData(0);
                const pcmData = new Int16Array(inputData.length);

                // Convert float32 to int16
                for (let i = 0; i < inputData.length; i++) {
                    pcmData[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
                }

                state.audioSocket.send(pcmData.buffer);
            }
        };

        source.connect(processor);
        processor.connect(state.audioContext.destination);

        state.mediaStream = stream;
        state.isRecording = true;

        // Update UI
        elements.recordBtn.classList.add('recording');
        elements.recordBtn.querySelector('.record-text').textContent = 'Stop Recording';
        elements.recordingIndicator.classList.remove('hidden');

        updateStatus('Recording');
        showToast('Recording started');

    } catch (error) {
        showToast('Microphone access denied', 'error');
        console.error('Error starting recording:', error);
    }
}

function stopRecording() {
    state.isRecording = false;

    // Stop audio stream
    if (state.mediaStream) {
        state.mediaStream.getTracks().forEach(track => track.stop());
        state.mediaStream = null;
    }

    // Close WebSocket
    if (state.audioSocket) {
        state.audioSocket.close();
        state.audioSocket = null;
    }

    // Close audio context
    if (state.audioContext) {
        state.audioContext.close();
        state.audioContext = null;
    }

    // Update UI
    elements.recordBtn.classList.remove('recording');
    elements.recordBtn.querySelector('.record-text').textContent = 'Start Recording';
    elements.recordingIndicator.classList.add('hidden');

    updateStatus('Encounter Active');
    showToast('Recording stopped');
}

function updateTranscriptionDisplay() {
    if (state.transcription) {
        elements.transcriptionArea.value = state.transcription;
    }
}

function updateTranscriptionState(value) {
    state.transcription = value;
}

function clearTranscription() {
    state.transcription = '';
    elements.transcriptionArea.value = '';
}

// ===== SOAP Note Generation =====

async function generateSOAP() {
    if (!state.sessionId) {
        showToast('No active encounter', 'error');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('chief_complaint', state.transcription.split('.')[0] || 'General consultation');

        elements.soapStatus.innerHTML = '<span class="status-badge">Generating...</span>';
        showToast('Generating SOAP note...');

        const response = await fetch(`/api/encounters/${state.sessionId}/generate-soap`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.status === 'generated') {
            elements.soapContent.innerHTML = data.soap_html;
            elements.soapStatus.innerHTML = '<span class="status-badge generated">Generated</span>';
            elements.soapActions.classList.remove('hidden');
            state.soapGenerated = true;

            // Show alerts if any
            if (data.alerts && data.alerts.length > 0) {
                elements.alertsCard.classList.remove('hidden');
                elements.alertsContent.innerHTML = data.alerts
                    .map(a => `<div class="alert-item">⚠️ ${a.message}</div>`)
                    .join('');
            }

            if (data.simulated) {
                showToast('SOAP note generated (simulated mode)');
            } else {
                showToast('SOAP note generated', 'success');
            }

            // Start polling for PubMed background analysis
            if (data.pubmed_insights_status === 'running') {
                startPubmedPolling(state.sessionId);
            }
        }

    } catch (error) {
        showToast('Failed to generate SOAP note', 'error');
        console.error('Error generating SOAP:', error);
    }
}

function regenerateSOAP() {
    generateSOAP();
}

function approveSOAP() {
    elements.confirmModal.classList.remove('hidden');
}

function closeModal() {
    elements.confirmModal.classList.add('hidden');
}

async function confirmApproval() {
    closeModal();

    try {
        const response = await fetch(`/api/encounters/${state.sessionId}/approve`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.status === 'approved') {
            elements.soapStatus.innerHTML = '<span class="status-badge approved">Approved & Saved</span>';
            elements.soapActions.innerHTML = '<button class="btn btn-secondary" onclick="endEncounter()">End Encounter</button>';
            showToast('SOAP note saved to EHR!', 'success');
        }

    } catch (error) {
        showToast('Failed to save to EHR', 'error');
        console.error('Error approving SOAP:', error);
    }
}

// ===== Utilities =====

function updateStatus(text) {
    elements.statusIndicator.querySelector('.status-text').textContent = text;

    const dot = elements.statusIndicator.querySelector('.status-dot');
    if (text === 'Recording') {
        dot.style.background = '#ef4444';
    } else {
        dot.style.background = '#10b981';
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// ===== Model Status Polling =====

function startModelStatusPolling() {
    pollModelStatus(); // immediate first call
    state.modelStatusInterval = setInterval(pollModelStatus, 3000);
}

function stopModelStatusPolling() {
    if (state.modelStatusInterval) {
        clearInterval(state.modelStatusInterval);
        state.modelStatusInterval = null;
    }
}

async function pollModelStatus() {
    try {
        const response = await fetch('/api/model-status');
        if (!response.ok) return;
        const data = await response.json();
        updateModelStatusDisplay(data);
    } catch (_) {
        // Silently ignore — server may be busy
    }
}

function updateModelStatusDisplay(data) {
    const models = data.models || {};
    const active = data.active;

    // Update each chip
    ['medgemma', 'functiongemma', 'medasr'].forEach(name => {
        const chip = document.getElementById(`chip-${name}`);
        if (!chip) return;
        const status = (models[name] || {}).status || 'unloaded';
        chip.className = `model-chip ${status === 'awake' ? 'awake' : 'asleep'}`;
    });

    // Update hint text
    if (active) {
        const labels = { medgemma: 'MedGemma', functiongemma: 'FunctionGemma', medasr: 'MedASR' };
        elements.modelStatusHint.textContent = `${labels[active] || active} active`;
    } else {
        elements.modelStatusHint.textContent = 'All sleeping';
    }
}

// ===== Audio File Upload =====

async function handleAudioFileUpload(input) {
    const file = input.files[0];
    if (!file) return;

    if (!state.sessionId) {
        showToast('No active encounter', 'error');
        input.value = '';
        return;
    }

    const formData = new FormData();
    formData.append('audio', file);

    showToast('Transcribing audio file…');

    try {
        const response = await fetch(
            `/api/encounters/${state.sessionId}/transcribe-audio`,
            { method: 'POST', body: formData }
        );

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            showToast(`Transcription failed: ${err.detail}`, 'error');
            input.value = '';
            return;
        }

        const data = await response.json();
        if (data.status === 'transcribed') {
            state.transcription = data.full_transcription;
            elements.transcriptionArea.value = data.full_transcription;
            showToast('Audio transcribed', 'success');
        }
    } catch (error) {
        showToast('Audio transcription error', 'error');
        console.error('Audio file upload error:', error);
    } finally {
        input.value = '';  // Reset so same file can be re-uploaded
    }
}

// ===== PubMed Insights Polling =====

let pubmedPollInterval = null;
let pubmedExpanded = true;

function startPubmedPolling(sessionId) {
    stopPubmedPolling();  // clear any previous

    const card = document.getElementById('pubmedCard');
    const badge = document.getElementById('pubmedStatusBadge');
    const body  = document.getElementById('pubmedBody');

    card.classList.remove('hidden');
    badge.textContent = 'Searching PubMed…';
    badge.style.background = '#fef9c3';
    badge.style.color = '#92400e';
    body.innerHTML = '<p style="color:var(--text-secondary); padding-top:0.5rem;">Scanning literature in background…</p>';

    pubmedPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/encounters/${sessionId}/pubmed-insights`);
            if (!res.ok) return;
            const data = await res.json();

            if (data.status === 'completed') {
                stopPubmedPolling();
                badge.textContent = 'Done';
                badge.style.background = '#d1fae5';
                badge.style.color = '#065f46';
                renderPubmedInsights(data.results || {});
            } else if (data.status === 'error') {
                stopPubmedPolling();
                badge.textContent = 'Error';
                badge.style.background = '#fee2e2';
                badge.style.color = '#991b1b';
                body.innerHTML = `<p style="color:#dc2626;padding-top:0.5rem;">PubMed analysis error: ${data.error || 'Unknown'}</p>`;
            }
            // Keep polling while status === 'running'
        } catch (_) {}
    }, 3500);
}

function stopPubmedPolling() {
    if (pubmedPollInterval) {
        clearInterval(pubmedPollInterval);
        pubmedPollInterval = null;
    }
}

function togglePubmedPanel() {
    const body = document.getElementById('pubmedBody');
    pubmedExpanded = !pubmedExpanded;
    body.style.display = pubmedExpanded ? '' : 'none';
}

function renderPubmedInsights(results) {
    const body = document.getElementById('pubmedBody');
    const sections = [];

    const modeLabels = {
        case_matcher:  { icon: '🦓', title: 'Zebra Hunt — Rare Diagnoses' },
        ebm_validator: { icon: '📊', title: 'Evidence-Based Validation' },
        ddi_monitor:   { icon: '💊', title: 'Drug Interaction Signals' },
    };

    for (const [mode, result] of Object.entries(results)) {
        if (result.error) continue;
        const meta = modeLabels[mode] || { icon: '📚', title: mode };

        let html = `<div style="margin-top:1rem; padding:0.75rem; background:var(--bg-primary); border-radius:8px; border:1px solid var(--border);">`;
        html += `<div style="font-weight:600; margin-bottom:0.5rem;">${meta.icon} ${meta.title}</div>`;

        if (result.summary) {
            html += `<p style="color:var(--text-secondary); margin-bottom:0.5rem; line-height:1.5;">${result.summary}</p>`;
        }

        // Mode-specific lists
        if (mode === 'case_matcher' && result.rare_diagnoses && result.rare_diagnoses.length > 0) {
            html += `<div style="font-weight:500; margin-bottom:0.25rem;">Rare Diagnoses to Consider:</div><ul style="margin:0 0 0.5rem 1.2rem; padding:0;">`;
            result.rare_diagnoses.slice(0, 5).forEach(d => {
                html += `<li style="margin:0.15rem 0;">${d}</li>`;
            });
            html += `</ul>`;
        }

        if (mode === 'ebm_validator' && result.divergences && result.divergences.length > 0) {
            html += `<div style="font-weight:500; color:#b45309; margin-bottom:0.25rem;">Plan Divergences from Evidence:</div><ul style="margin:0 0 0.5rem 1.2rem; padding:0; color:#92400e;">`;
            result.divergences.slice(0, 4).forEach(d => {
                html += `<li style="margin:0.15rem 0; font-size:0.82rem;">${d}</li>`;
            });
            html += `</ul>`;
        }

        if (mode === 'ddi_monitor' && result.ddi_alerts && result.ddi_alerts.length > 0) {
            html += `<div style="font-weight:500; color:#b91c1c; margin-bottom:0.25rem;">Interaction Signals:</div><ul style="margin:0 0 0.5rem 1.2rem; padding:0; color:#7f1d1d;">`;
            result.ddi_alerts.slice(0, 4).forEach(a => {
                html += `<li style="margin:0.15rem 0; font-size:0.82rem;">${a}</li>`;
            });
            html += `</ul>`;
        }

        // Key findings
        if (result.key_findings && result.key_findings.length > 0) {
            html += `<details style="margin-top:0.35rem;"><summary style="cursor:pointer; font-size:0.8rem; color:var(--text-secondary);">Key findings (${result.key_findings.length})</summary><ul style="margin:0.25rem 0 0 1.2rem; padding:0;">`;
            result.key_findings.forEach(f => {
                html += `<li style="margin:0.2rem 0; font-size:0.78rem; color:var(--text-secondary);">${f}</li>`;
            });
            html += `</ul></details>`;
        }

        // Citations
        if (result.citation_list && result.citation_list.length > 0) {
            html += `<details style="margin-top:0.25rem;"><summary style="cursor:pointer; font-size:0.8rem; color:var(--text-secondary);">Citations (${result.citation_list.length})</summary><ol style="margin:0.25rem 0 0 1.2rem; padding:0;">`;
            result.citation_list.forEach(c => {
                html += `<li style="margin:0.2rem 0; font-size:0.75rem; color:var(--text-secondary);">${c}</li>`;
            });
            html += `</ol></details>`;
        }

        html += `</div>`;
        sections.push(html);
    }

    body.innerHTML = sections.length > 0
        ? sections.join('')
        : '<p style="color:var(--text-secondary); padding-top:0.5rem;">No relevant PubMed literature found for this encounter.</p>';
}

// ═══════════════════════════════════════════════════════════
//  Resume Bot v2.0 — Main Dashboard JS
//  Tabs, API calls, job rendering, chatbot, settings, about
// ═══════════════════════════════════════════════════════════

// Global job data cache (used for resume preview by index)
let cachedJobs = [];

document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    fetchJobs();
    loadSettings();
    loadAbout();

    // Auto-refresh stats every 5 seconds
    setInterval(fetchStats, 5000);
    // Auto-refresh jobs every 15 seconds
    setInterval(fetchJobs, 15000);

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
        });
    });

    // Button bindings
    document.getElementById('btn-toggle-scheduler').addEventListener('click', toggleScheduler);
    document.getElementById('btn-force-scan').addEventListener('click', triggerScan);

    // Chatbot input: Enter to send
    document.getElementById('chatbot-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });
});

// ─── HTML escape helper ─────────────────────────────────────
function esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ═══════════════════════════════════════════════════════════
//  API: Stats & Dashboard
// ═══════════════════════════════════════════════════════════
async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();

        // Dashboard stat cards
        document.getElementById('metric-total').innerText = data.total_jobs || 0;
        document.getElementById('metric-today').innerText = data.new_today || 0;
        document.getElementById('metric-pending').innerText = data.pending || 0;
        document.getElementById('metric-approved').innerText = data.approved || 0;
        document.getElementById('metric-rejected').innerText = data.rejected || 0;
        document.getElementById('metric-ats').innerText = `${data.avg_ats || 0}%`;

        // Pending/Approved count labels
        const pendingLabel = document.getElementById('pending-count-label');
        if (pendingLabel) pendingLabel.innerText = `${data.pending || 0} jobs pending`;
        const approvedLabel = document.getElementById('approved-count-label');
        if (approvedLabel) approvedLabel.innerText = `${data.approved || 0} approved jobs`;

        // Status pill
        const pill = document.getElementById('status-pill');
        const statusText = document.getElementById('status-text');
        const btn = document.getElementById('btn-toggle-scheduler');

        pill.className = 'status-pill';
        if (data.scheduler_running) {
            pill.classList.add('active');
            statusText.innerText = 'Auto-Scanning';
            btn.innerText = '🛑 Stop Auto-Scanner';
            btn.className = 'btn btn-danger btn-full';
        } else {
            statusText.innerText = 'Idle';
            btn.innerText = '🚀 Start Auto-Scanner';
            btn.className = 'btn btn-primary btn-full';
        }

        // Sync status indicators
        const driveDot = document.getElementById('sync-drive-dot');
        const driveCount = document.getElementById('sync-drive-count');
        if (data.drive_uploads > 0) {
            driveDot.className = 'sync-dot sync-dot-active';
            driveCount.innerText = `${data.drive_uploads} uploaded`;
        } else {
            driveDot.className = 'sync-dot';
            driveCount.innerText = '0 uploads';
        }

        const scannerDot = document.getElementById('sync-scanner-dot');
        const scannerStatus = document.getElementById('sync-scanner-status');
        if (data.scheduler_running) {
            scannerDot.className = 'sync-dot sync-dot-active';
            scannerStatus.innerText = 'Running';
        } else {
            scannerDot.className = 'sync-dot';
            scannerStatus.innerText = 'Off';
        }

        const sheetsDot = document.getElementById('sync-sheets-dot');
        if (data.approved > 0 || data.drive_uploads > 0) {
            sheetsDot.className = 'sync-dot sync-dot-active';
        } else {
            sheetsDot.className = 'sync-dot sync-dot-warning';
        }

        const resumesCount = document.getElementById('sync-resumes-count');
        resumesCount.innerText = data.resumes_generated || 0;

        // Logs
        const logsEl = document.getElementById('logs-container');
        if (data.logs && data.logs.length > 0) {
            logsEl.innerText = data.logs.join('\n');
        } else {
            logsEl.innerText = 'No activity yet.';
        }
    } catch (e) {
        console.error('Stats fetch error:', e);
    }
}

// ═══════════════════════════════════════════════════════════
//  API: Jobs
// ═══════════════════════════════════════════════════════════
async function fetchJobs() {
    try {
        const res = await fetch('/api/jobs');
        const jobs = await res.json();
        cachedJobs = jobs;

        const pendingJobs = jobs.filter(j => j.status === 'pending');
        // Support both old "applied" and new "approved"
        const approvedJobs = jobs.filter(j => j.status === 'applied' || j.status === 'approved');

        renderPending(pendingJobs);
        renderApproved(approvedJobs);
        renderRecentJobs(jobs);
    } catch (e) {
        console.error('Jobs fetch error:', e);
    }
}

// ─── Render Pending Jobs ────────────────────────────────────
function renderPending(jobs) {
    const el = document.getElementById('pending-list');
    if (jobs.length === 0) {
        el.innerHTML = '<div class="empty-state">No pending jobs. Click <strong>Find Jobs Now</strong> on the Dashboard to discover opportunities.</div>';
        return;
    }

    el.innerHTML = jobs.map((job, idx) => {
        const score = job.ats_score || 0;
        const isTailored = score > 0 && job.tailored_resume_text;
        const cls = score >= 80 ? 'ats-high' : (score >= 70 ? 'ats-mid' : 'ats-low');
        const badgeHtml = isTailored
            ? `<span class="ats-badge ${cls}">ATS ${score}/100</span>`
            : `<span class="ats-badge ats-low">Not scored</span>`;

        // Find global index for resume preview
        const globalIdx = cachedJobs.findIndex(j => j.apply_url === job.apply_url);

        const metaHtml = isTailored
            ? `<div class="job-meta">
                    <strong>Role:</strong> ${esc(job.job_role || job.title)}<br>
                    <strong>Tech:</strong> ${esc(job.tech_stack || 'N/A')}<br>
                    <strong>Looking for:</strong> ${esc(job.summary_looking_for || 'N/A')}
               </div>`
            : `<div class="job-meta">
                    <strong>Role:</strong> ${esc(job.job_role || job.title)}<br>
                    <strong>Platform:</strong> ${esc(job.platform || 'N/A')}<br>
                    <em style="color: var(--text-muted);">Click "Tailor Resume" to score and optimize your resume for this job.</em>
               </div>`;

        return `
            <div class="job-card" id="job-card-${globalIdx}">
                <div class="job-card-header">
                    <div>
                        <div class="job-title">${esc(job.title)}</div>
                        <div class="job-company">${esc(job.company)} · ${esc(job.platform || '')}</div>
                    </div>
                    ${badgeHtml}
                </div>
                ${metaHtml}
                <div class="job-actions">
                    ${!isTailored ? `<button onclick="tailorJob('${encodeURIComponent(job.apply_url)}')" class="btn btn-sm btn-primary">✦ Tailor Resume</button>` : ''}
                    ${isTailored ? `<button onclick="previewResume(${globalIdx})" class="btn btn-sm btn-outline">📄 Tailored Resume</button>` : ''}
                    ${job.drive_link && !job.drive_link.startsWith('Saved Locally') && !job.drive_link.startsWith('Error') ? `<a href="${esc(job.drive_link)}" target="_blank" class="btn btn-sm btn-outline">📂 Drive Resume</a>` : ''}
                    <a href="${esc(job.apply_url)}" target="_blank" class="btn btn-sm btn-outline">🔗 Job Link</a>
                    <button onclick="askAboutJob('${esc(job.title).replace(/'/g, "\\'")}', '${esc(job.company).replace(/'/g, "\\'")}')" class="btn btn-sm btn-outline">💬 Ask AI</button>
                    <button onclick="approveJob('${encodeURIComponent(job.apply_url)}')" class="btn btn-sm btn-success">✓ Approve & Log to Sheet</button>
                    <button onclick="rejectJob('${encodeURIComponent(job.apply_url)}')" class="btn btn-sm btn-danger">✕ Reject</button>
                </div>
            </div>`;
    }).join('');
}

// ─── Render Approved Jobs ───────────────────────────────────
function renderApproved(jobs) {
    const el = document.getElementById('approved-list');
    if (jobs.length === 0) {
        el.innerHTML = '<div class="empty-state">No approved jobs yet. Review pending jobs and click <strong>Approve & Log</strong>.</div>';
        return;
    }

    el.innerHTML = jobs.map((job, idx) => {
        const globalIdx = cachedJobs.findIndex(j => j.apply_url === job.apply_url);
        const hasDriveLink = job.drive_link && !job.drive_link.startsWith('Saved Locally') && !job.drive_link.startsWith('Error');

        return `
        <div class="job-card approved">
            <div class="job-card-header">
                <div>
                    <div class="job-title">${esc(job.title)}</div>
                    <div class="job-company">${esc(job.company)} · ATS ${job.ats_score || 0}/100</div>
                </div>
                <span class="ats-badge ats-high">Approved ✓</span>
            </div>
            <div class="job-meta">
                <strong>Role:</strong> ${esc(job.job_role || job.title)}<br>
                <strong>Tech:</strong> ${esc(job.tech_stack || 'N/A')}<br>
                ${hasDriveLink ? `<strong>Resume:</strong> <a href="${esc(job.drive_link)}" target="_blank" style="color: var(--accent);">Open in Google Drive ↗</a>` : ''}
            </div>
            <div class="job-actions">
                ${hasDriveLink ? `<a href="${esc(job.drive_link)}" target="_blank" class="btn btn-sm btn-primary">📂 Open Resume in Drive</a>` : ''}
                <a href="${esc(job.apply_url)}" target="_blank" class="btn btn-sm btn-outline">🔗 Apply from Job Portal</a>
                ${job.tailored_resume_text ? `<button onclick="previewResume(${globalIdx})" class="btn btn-sm btn-outline">📄 View Resume</button>` : ''}
                <a href="/api/download/pdf?apply_url=${encodeURIComponent(job.apply_url)}" class="btn btn-sm btn-outline">📥 Download PDF</a>
            </div>
        </div>`;
    }).join('');
}

// ─── Render Recent Jobs (Dashboard) ─────────────────────────
function renderRecentJobs(jobs) {
    const el = document.getElementById('recent-jobs-list');
    if (!el) return;
    
    // Show last 8 jobs, sorted by most recent first
    const recent = [...jobs].reverse().slice(0, 8);
    if (recent.length === 0) {
        el.innerHTML = '<div class="empty-state-sm">No jobs discovered yet. Run a scan to get started.</div>';
        return;
    }

    el.innerHTML = recent.map(job => {
        const status = (job.status === 'applied' || job.status === 'approved') ? 'approved' : job.status;
        const ats = job.ats_score > 0 ? `ATS ${job.ats_score}` : '';
        return `
            <div class="recent-job-item">
                <div class="recent-job-dot ${status}"></div>
                <div class="recent-job-info">
                    <div class="recent-job-title">${esc(job.title)}</div>
                    <div class="recent-job-company">${esc(job.company)} · ${esc(job.platform || '')}</div>
                </div>
                ${ats ? `<div class="recent-job-ats">${ats}</div>` : ''}
            </div>`;
    }).join('');
}

// ═══════════════════════════════════════════════════════════
//  ACTIONS: Scan, Toggle, Tailor, Approve, Reject
// ═══════════════════════════════════════════════════════════

async function triggerScan() {
    const btn = document.getElementById('btn-force-scan');
    btn.innerText = '⏳ Finding jobs...';
    btn.disabled = true;

    const pill = document.getElementById('status-pill');
    const statusText = document.getElementById('status-text');
    pill.className = 'status-pill scanning';
    statusText.innerText = 'Scanning...';

    try {
        const res = await fetch('/api/scan', { method: 'POST' });
        const data = await res.json();
        if (data.status !== 'success') {
            showToast(data.message || 'Scan could not start.', 'error');
        } else {
            showToast('Job scan started! New jobs will appear shortly.', 'success');
        }
        // Refresh after a delay to allow background processing
        setTimeout(() => {
            fetchStats();
            fetchJobs();
            btn.innerText = '🔍 Find Jobs Now';
            btn.disabled = false;
        }, 5000);
    } catch (e) {
        console.error('Scan error:', e);
        btn.innerText = '🔍 Find Jobs Now';
        btn.disabled = false;
    }
}

async function toggleScheduler() {
    try {
        await fetch('/api/scheduler/toggle', { method: 'POST' });
        fetchStats();
    } catch (e) {
        console.error('Toggle error:', e);
    }
}

async function tailorJob(encodedUrl) {
    const apply_url = decodeURIComponent(encodedUrl);
    showToast('Tailoring resume... this may take 15-30 seconds.', 'info');
    try {
        const res = await fetch('/api/tailor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ apply_url })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Resume tailored! ATS Score: ${data.ats_score || 'N/A'}/100`, 'success');
            fetchStats();
            fetchJobs();
        } else {
            showToast(`Tailoring failed: ${data.message}`, 'error');
        }
    } catch (e) {
        console.error('Tailor error:', e);
        showToast('Tailoring failed. Check console for details.', 'error');
    }
}

async function approveJob(encodedUrl) {
    const apply_url = decodeURIComponent(encodedUrl);
    showToast('Approving & saving to Google Sheet...', 'info');
    try {
        const res = await fetch('/api/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ apply_url })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Approved! Job saved to Google Sheet with resume link.', 'success');
            fetchStats();
            fetchJobs();
        } else {
            showToast(`Approval failed: ${data.message}`, 'error');
        }
    } catch (e) {
        console.error('Approve error:', e);
        showToast('Approval failed. Check console for details.', 'error');
    }
}

async function rejectJob(encodedUrl) {
    const apply_url = decodeURIComponent(encodedUrl);
    try {
        await fetch('/api/reject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ apply_url })
        });
        showToast('Job rejected and removed from pending.', 'info');
        fetchStats();
        fetchJobs();
    } catch (e) {
        console.error('Reject error:', e);
    }
}

async function bulkApprove() {
    showToast('Approving all pending jobs... this may take a while.', 'info');
    const jobs = cachedJobs.filter(j => j.status === 'pending');
    for (const job of jobs) {
        await approveJob(encodeURIComponent(job.apply_url));
    }
    showToast('All pending jobs approved!', 'success');
}

async function bulkRejectLow() {
    const jobs = cachedJobs.filter(j => j.status === 'pending');
    let count = 0;
    for (const job of jobs) {
        if ((job.ats_score || 0) < 70) {
            await rejectJob(encodeURIComponent(job.apply_url));
            count++;
        }
    }
    showToast(`Rejected ${count} jobs with ATS score below 70.`, 'info');
}

// ═══════════════════════════════════════════════════════════
//  RESUME PREVIEW MODAL
//  Fixed: uses index into cachedJobs instead of encoding
//  the entire resume text into an onclick attribute
// ═══════════════════════════════════════════════════════════

function previewResume(jobIndex) {
    const job = cachedJobs[jobIndex];
    if (!job || !job.tailored_resume_text) {
        showToast('No tailored resume available for this job.', 'error');
        return;
    }
    document.getElementById('modal-title').innerText = `Resume — ${job.job_role || job.title} at ${job.company}`;
    document.getElementById('modal-text').value = job.tailored_resume_text;
    document.getElementById('preview-modal').style.display = 'block';
}

function closeModal() {
    document.getElementById('preview-modal').style.display = 'none';
    document.getElementById('preview-modal-box').classList.remove('modal-maximized');
}

function toggleMaximize() {
    document.getElementById('preview-modal-box').classList.toggle('modal-maximized');
}

window.addEventListener('click', e => {
    if (e.target.id === 'preview-modal') closeModal();
});

// ═══════════════════════════════════════════════════════════
//  FLOATING AI CHATBOT
// ═══════════════════════════════════════════════════════════

function toggleChatbot() {
    const window_ = document.getElementById('chatbot-window');
    const fab = document.getElementById('chatbot-fab');

    if (window_.classList.contains('open')) {
        window_.classList.remove('open');
        fab.classList.remove('hidden');
    } else {
        window_.classList.add('open');
        fab.classList.add('hidden');
        document.getElementById('chatbot-input').focus();
    }
}

async function sendChatMessage() {
    const input = document.getElementById('chatbot-input');
    const question = input.value.trim();
    if (!question) return;

    const messagesEl = document.getElementById('chatbot-messages');

    // Add user message
    messagesEl.innerHTML += `<div class="chat-bubble user">${esc(question)}</div>`;
    input.value = '';
    messagesEl.scrollTop = messagesEl.scrollHeight;

    // Add typing indicator
    const typingId = 'typing-' + Date.now();
    messagesEl.innerHTML += `<div class="chat-bubble typing" id="${typingId}">Thinking...</div>`;
    messagesEl.scrollTop = messagesEl.scrollHeight;

    const sendBtn = document.getElementById('chatbot-send');
    sendBtn.disabled = true;

    try {
        const res = await fetch('/api/chatbot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });
        const data = await res.json();

        // Remove typing indicator
        const typingEl = document.getElementById(typingId);
        if (typingEl) typingEl.remove();

        const answer = data.answer || 'I could not generate an answer right now.';
        messagesEl.innerHTML += `<div class="chat-bubble assistant">${formatChatAnswer(answer)}</div>`;
        messagesEl.scrollTop = messagesEl.scrollHeight;
    } catch (e) {
        const typingEl = document.getElementById(typingId);
        if (typingEl) typingEl.remove();
        messagesEl.innerHTML += '<div class="chat-bubble assistant">Sorry, I\'m unable to connect right now. Please check the API keys in Settings.</div>';
    } finally {
        sendBtn.disabled = false;
    }
}

function askAboutJob(title, company) {
    // Open chatbot and pre-fill with job-specific question
    const window_ = document.getElementById('chatbot-window');
    const fab = document.getElementById('chatbot-fab');

    if (!window_.classList.contains('open')) {
        window_.classList.add('open');
        fab.classList.add('hidden');
    }

    const input = document.getElementById('chatbot-input');
    input.value = `What should I emphasize in my resume for "${title}" at ${company}? Also suggest interview questions.`;
    input.focus();

    // Auto-send
    setTimeout(() => sendChatMessage(), 300);
}

function formatChatAnswer(text) {
    // Basic markdown-like formatting for chat
    return esc(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^- /gm, '• ')
        .replace(/\n/g, '<br>');
}

// ═══════════════════════════════════════════════════════════
//  SETTINGS
// ═══════════════════════════════════════════════════════════

async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        const data = await res.json();
        document.getElementById('llm_provider').value = data.llm_provider;
        document.getElementById('groq_key').value = data.groq_key;
        document.getElementById('openrouter_key').value = data.openrouter_key;
        document.getElementById('gemini_key').value = data.gemini_key;
        document.getElementById('sheet_title').value = data.sheet_title;
        document.getElementById('sheet_id').value = data.sheet_id;
        document.getElementById('sheet_tab').value = data.sheet_tab;
        document.getElementById('keywords').value = data.keywords;
    } catch (e) {
        console.error('Load settings error:', e);
    }
}

async function saveSettings() {
    const payload = {
        llm_provider: document.getElementById('llm_provider').value,
        groq_key: document.getElementById('groq_key').value,
        openrouter_key: document.getElementById('openrouter_key').value,
        gemini_key: document.getElementById('gemini_key').value,
        sheet_title: document.getElementById('sheet_title').value,
        sheet_id: document.getElementById('sheet_id').value,
        sheet_tab: document.getElementById('sheet_tab').value,
        keywords: document.getElementById('keywords').value
    };
    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Settings saved successfully!', 'success');
            fetchStats();
        }
    } catch (e) {
        console.error('Save settings error:', e);
        showToast('Failed to save settings.', 'error');
    }
}

// ═══════════════════════════════════════════════════════════
//  ABOUT / SYSTEM ARCHITECTURE
// ═══════════════════════════════════════════════════════════

async function loadAbout() {
    try {
        const res = await fetch('/api/system-info');
        const info = await res.json();
        renderAbout(info);
    } catch (e) {
        console.error('System info error:', e);
        document.getElementById('about-content').innerHTML = '<div class="about-loading">Failed to load system information.</div>';
    }
}

function renderAbout(info) {
    const el = document.getElementById('about-content');
    const arch = info.architecture || {};

    // Build architecture cards
    const archCards = Object.values(arch).map(section => {
        const techTags = (section.tech || []).map(t => `<span class="arch-tech-tag">${esc(t)}</span>`).join('');

        let listHtml = '';
        // Show capabilities, sources, endpoints, or features
        const items = section.capabilities || section.features || [];
        if (items.length > 0) {
            listHtml = `<ul class="arch-list">${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>`;
        }

        // Special handling for sources
        if (section.sources) {
            listHtml = `<ul class="arch-list">${section.sources.map(s => `<li><strong>${esc(s.name)}</strong> (${esc(s.type)}) — ${esc(s.desc)}</li>`).join('')}</ul>`;
        }

        // Special handling for endpoints
        if (section.endpoints) {
            listHtml = `<ul class="arch-list">${section.endpoints.map(ep => `<li><strong>${esc(ep.method)}</strong> ${esc(ep.path)} — ${esc(ep.desc)}</li>`).join('')}</ul>`;
        }

        return `
            <div class="arch-card">
                <h3>${esc(section.title)}</h3>
                <div class="arch-tech-tags">${techTags}</div>
                <p>${esc(section.description)}</p>
                ${listHtml}
            </div>`;
    }).join('');

    // Build workflow steps
    const workflowHtml = (info.workflow || []).map((step, i) => {
        const arrow = i < info.workflow.length - 1 ? '<span class="workflow-arrow">→</span>' : '';
        return `<div class="workflow-step"><span class="step-num">${i + 1}</span>${esc(step)}</div>${arrow}`;
    }).join('');

    el.innerHTML = `
        <div class="about-hero">
            <h2>${esc(info.project_name)}</h2>
            <p>${esc(info.description)}</p>
            <span class="about-version">Version ${esc(info.version)}</span>
        </div>

        <div class="workflow-card">
            <h3>📋 End-to-End Workflow</h3>
            <div class="workflow-steps">${workflowHtml}</div>
        </div>

        <div class="arch-grid">${archCards}</div>
    `;
}

// ═══════════════════════════════════════════════════════════
//  TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════

function showToast(message, type = 'info') {
    // Remove existing toast
    const existing = document.querySelector('.toast-notification');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.innerText = message;

    // Style it inline (no CSS class needed)
    Object.assign(toast.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '12px 20px',
        borderRadius: '10px',
        fontSize: '0.84rem',
        fontWeight: '600',
        fontFamily: 'Inter, sans-serif',
        color: '#fff',
        zIndex: '5000',
        maxWidth: '400px',
        boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
        animation: 'fadeIn 0.3s ease',
        cursor: 'pointer'
    });

    const colors = {
        success: 'linear-gradient(135deg, #4A9A64, #3D8A55)',
        error: 'linear-gradient(135deg, #C0615A, #A8524C)',
        info: 'linear-gradient(135deg, #5B8DB5, #4A7DA5)',
        warning: 'linear-gradient(135deg, #E6A641, #D49635)'
    };
    toast.style.background = colors[type] || colors.info;

    toast.onclick = () => toast.remove();
    document.body.appendChild(toast);

    // Auto-remove after 4 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-10px)';
            toast.style.transition = '0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}

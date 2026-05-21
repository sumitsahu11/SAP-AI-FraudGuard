/* ============================================================
   SAP AI FraudGuard — main.js
   All frontend logic for the dashboard
   ============================================================ */

'use strict';

/* ============================================================
   GLOBAL STATE
   ============================================================ */
const APP = {
  currentSection: 'upload',
  uploadSummary: null,
  riskyInvoices: [],
  vendorRisk: [],
  apControl: null,
  docFiles: [],
  chatHistory: [],
  ragChatHistory: [],
};

/* ============================================================
   UTILITY
   ============================================================ */

function fmt(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

function fmtCurrency(n) {
  if (n === null || n === undefined) return '—';
  return '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtScore(n) {
  if (n === null || n === undefined) return '—';
  return (Number(n) * 100).toFixed(1) + '%';
}

function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = String(str ?? '');
  return d.innerHTML;
}

function riskBadge(level) {
  const l = String(level).toUpperCase();
  return `<span class="risk-badge ${l}">${l}</span>`;
}

function tierBadge(tier) {
  return `<span class="tier-badge ${tier}">${tier}</span>`;
}

/* ============================================================
   TOAST
   ============================================================ */
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span> ${escHtml(message)}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideIn 0.3s reverse forwards';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/* ============================================================
   LOADING OVERLAY
   ============================================================ */
function showLoading(message = 'Processing...', sub = '') {
  const el = document.getElementById('loading-overlay');
  if (!el) return;
  el.querySelector('.loading-title').textContent = message;
  el.querySelector('.loading-sub').textContent = sub;
  el.classList.add('active');
}
function hideLoading() {
  const el = document.getElementById('loading-overlay');
  if (el) el.classList.remove('active');
}

/* ============================================================
   NAVIGATION
   ============================================================ */
function navigate(section) {
  // Update nav items
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.section === section);
  });

  // Update page sections
  document.querySelectorAll('.page-section').forEach(el => {
    el.classList.toggle('active', el.id === 'section-' + section);
  });

  // Update topbar title
  const titles = {
    upload:       { title: 'Invoice Analysis',      breadcrumb: 'Upload & Process' },
    invoices:     { title: 'Risky Invoices',        breadcrumb: 'Invoice Intelligence' },
    vendor:       { title: 'Vendor Risk 360°',      breadcrumb: 'Vendor Analysis' },
    ap:           { title: 'AP Control Dashboard',  breadcrumb: 'AP Operations' },
    rag:          { title: 'AI Query Engine',       breadcrumb: 'RAG Intelligence' },
    docfinder:    { title: 'DocFinder',             breadcrumb: 'Document Intelligence' },
    docsummarizer:{ title: 'Doc Summarizer',        breadcrumb: 'Document Intelligence' }, // NEW
    simulator:    { title: 'What-If Simulator',     breadcrumb: 'Policy Simulation' },
    playbook:     { title: 'Fraud Playbook',        breadcrumb: 'Recommendations' },
  };

  const info = titles[section] || { title: section, breadcrumb: '' };
  const el = document.getElementById('topbar-title');
  const el2 = document.getElementById('topbar-breadcrumb');
  if (el) el.textContent = info.title;
  if (el2) el2.textContent = info.breadcrumb;

  APP.currentSection = section;

  // Lazy-load section data
  if (section === 'vendor' && APP.uploadSummary) loadVendorRisk();
  if (section === 'ap' && APP.uploadSummary) { loadAPControl(); loadAPControlCharts(); }
  if (section === 'playbook' && APP.uploadSummary) loadPlaybook();
}

/* ============================================================
   SECTION: UPLOAD & PROCESS
   ============================================================ */
function initUploadZone() {
  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('file-input');
  const label = document.getElementById('upload-file-label');

  if (!zone || !input) return;

  ['dragover', 'dragenter'].forEach(evt => {
    zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.add('dragover'); });
  });
  ['dragleave', 'drop'].forEach(evt => {
    zone.addEventListener(evt, () => zone.classList.remove('dragover'));
  });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length) {
      input.files = files;
      if (label) label.textContent = files[0].name;
    }
  });
  input.addEventListener('change', () => {
    if (input.files.length && label) label.textContent = input.files[0].name;
  });
}

async function processInvoices() {
  const input = document.getElementById('file-input');
  if (!input || !input.files.length) {
    showToast('Please select a file first.', 'warning');
    return;
  }

  const formData = new FormData();
  formData.append('file', input.files[0]);

  showLoading('Running AI Analysis…', 'Applying ML models, rule checks, and risk scoring');

  try {
    const res = await fetch('/api/process_invoices', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.error || 'Processing failed.', 'error');
      hideLoading();
      return;
    }

    APP.uploadSummary = data.summary;
    APP.riskyInvoices = data.risky_invoices_sample || [];

    hideLoading();
    renderUploadSummary(data.summary);
    renderRiskyInvoicesTable(APP.riskyInvoices);
    showToast(`Processed ${fmt(data.summary.total_invoices)} invoices successfully.`, 'success');

  } catch (err) {
    hideLoading();
    showToast('Network error. Please try again.', 'error');
    console.error(err);
  }
}

function renderUploadSummary(s) {
  const el = document.getElementById('upload-results');
  if (!el) return;
  el.innerHTML = `
    <div class="kpi-row" style="margin-bottom:0">
      <div class="kpi-card blue">
        <div class="kpi-badge">📄</div>
        <div class="kpi-label">Total Invoices</div>
        <div class="kpi-value"><span>${fmt(s.total_invoices)}</span></div>
        <div class="kpi-sub">Processed successfully</div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-badge">🚨</div>
        <div class="kpi-label">High Risk</div>
        <div class="kpi-value"><span>${fmt(s.high_risk_invoices)}</span></div>
        <div class="kpi-sub">${fmtCurrency(s.high_risk_amount)} exposure</div>
      </div>
      <div class="kpi-card amber">
        <div class="kpi-badge">⚠️</div>
        <div class="kpi-label">Risky Total</div>
        <div class="kpi-value"><span>${fmt(s.risky_invoices)}</span></div>
        <div class="kpi-sub">${fmtCurrency(s.total_risk_amount)} at risk</div>
      </div>
      <div class="kpi-card green">
        <div class="kpi-badge">✅</div>
        <div class="kpi-label">Clean Invoices</div>
        <div class="kpi-value"><span>${fmt(s.total_invoices - s.risky_invoices)}</span></div>
        <div class="kpi-sub">No anomalies detected</div>
      </div>
    </div>
    <div class="alert info mt-16" style="margin-bottom:0">
      <span class="alert-icon">ℹ️</span>
      <div>AI analysis complete. Navigate to <strong>Risky Invoices</strong>, <strong>Vendor Risk 360°</strong>, or <strong>AP Dashboard</strong> to explore results.</div>
    </div>
  `;
}

function renderRiskyInvoicesTable(invoices) {
  const el = document.getElementById('risky-invoices-body');
  if (!el) return;

  if (!invoices.length) {
    el.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:32px;color:var(--ink-light)">No risky invoices found.</td></tr>`;
    return;
  }

  el.innerHTML = invoices.map(inv => `
    <tr class="row-link" onclick="openInvoiceModal('${escHtml(inv.InvoiceID)}')">
      <td class="mono">${escHtml(inv.InvoiceID)}</td>
      <td>${escHtml(inv.Vendor)}</td>
      <td class="mono">${escHtml(inv.InvoiceNumber)}</td>
      <td>${escHtml(inv.InvoiceDate)}</td>
      <td class="mono" style="font-weight:600">${fmtCurrency(inv.Amount)}</td>
      <td>${riskBadge(inv.RiskLevel)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="progress-bar" style="width:60px">
            <div class="progress-fill ${inv.RiskLevel === 'HIGH' ? 'red' : 'amber'}" style="width:${Math.round(Number(inv.RiskScore)*100)}%"></div>
          </div>
          <span class="mono text-xs">${fmtScore(inv.RiskScore)}</span>
        </div>
      </td>
      <td class="text-sm text-muted">${escHtml(inv.RiskReason || '—')}</td>
    </tr>
  `).join('');
}

/* ============================================================
   INVOICE MODAL
   ============================================================ */
async function openInvoiceModal(invoiceId) {
  const modal = document.getElementById('invoice-modal');
  if (!modal) return;

  modal.classList.add('active');

  const body = document.getElementById('invoice-modal-body');
  body.innerHTML = `<div style="text-align:center;padding:32px"><div class="loading-spinner-lg"></div><p class="text-muted mt-12">Loading invoice…</p></div>`;

  try {
    const res = await fetch(`/api/invoice/${encodeURIComponent(invoiceId)}`);
    const data = await res.json();

    if (!res.ok) {
      body.innerHTML = `<div class="alert error"><span>❌</span>${escHtml(data.error)}</div>`;
      return;
    }

    const inv = data.invoice;
    const history = data.history;

    const cells = Object.entries(inv).map(([k, v]) => `
      <div class="detail-cell">
        <div class="detail-cell-label">${escHtml(k)}</div>
        <div class="detail-cell-value">${k === 'RiskLevel' ? riskBadge(v) : k === 'RiskScore' ? fmtScore(v) : k === 'Amount' ? fmtCurrency(v) : escHtml(v)}</div>
      </div>
    `).join('');

    const histRows = (history.rows || []).map(row => {
      const isCurrent = row[history.columns.indexOf('InvoiceID')] === String(invoiceId);
      return `<tr${isCurrent ? ' class="highlighted"' : ''}>
        ${row.map((v, i) => {
          const col = history.columns[i];
          let cell = escHtml(v);
          if (col === 'RiskLevel') cell = riskBadge(v);
          if (col === 'Amount') cell = fmtCurrency(v);
          if (col === 'RiskScore') cell = fmtScore(v);
          return `<td>${cell}</td>`;
        }).join('')}
      </tr>`;
    }).join('');

    body.innerHTML = `
      <div class="detail-grid">${cells}</div>

      <div class="mt-20">
        <div class="card-title mb-16">
          <div class="card-title-icon">📋</div>
          Vendor Invoice History
        </div>
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>${(history.columns || []).map(c => `<th>${escHtml(c)}</th>`).join('')}</tr>
            </thead>
            <tbody>${histRows}</tbody>
          </table>
        </div>
      </div>

      <div class="mt-20">
        <div class="card-title mb-16">
          <div class="card-title-icon">🤖</div>
          AI Explanation
        </div>
        <div id="inv-explanation">
          <button class="btn btn-primary btn-sm" onclick="loadExplanation('${escHtml(invoiceId)}')">Generate AI Explanation</button>
        </div>
      </div>
    `;

  } catch (err) {
    body.innerHTML = `<div class="alert error"><span>❌</span>Failed to load invoice.</div>`;
  }
}

async function loadExplanation(invoiceId) {
  const el = document.getElementById('inv-explanation');
  if (!el) return;
  el.innerHTML = `<div class="flex-center gap-8"><div class="spinner"></div> <span class="text-muted">Generating AI explanation…</span></div>`;

  try {
    const res = await fetch('/api/rag/explain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invoice_id: invoiceId }),
    });
    const data = await res.json();

    if (!res.ok) {
      el.innerHTML = `<div class="alert error"><span>❌</span>${escHtml(data.error)}</div>`;
      return;
    }

    const explanation = data.explanation || data.answer || JSON.stringify(data, null, 2);
    el.innerHTML = `
      <div class="alert info" style="align-items:flex-start">
        <span class="alert-icon">🤖</span>
        <div style="white-space:pre-wrap;line-height:1.7">${escHtml(explanation)}</div>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<div class="alert error"><span>❌</span>Failed to get explanation.</div>`;
  }
}

function closeInvoiceModal() {
  const m = document.getElementById('invoice-modal');
  if (m) m.classList.remove('active');
}

/* ============================================================
   SECTION: VENDOR RISK
   ============================================================ */
async function loadVendorRisk() {
  if (APP.vendorRisk.length) { renderVendorTable(APP.vendorRisk); return; }

  const el = document.getElementById('vendor-table-body');
  if (el) el.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px"><div class="spinner"></div></td></tr>`;

  try {
    const res = await fetch('/api/vendor_risk_overview');
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Failed to load vendor data.', 'error'); return; }
    APP.vendorRisk = data.vendors || [];
    renderVendorTable(APP.vendorRisk);
  } catch (err) {
    showToast('Network error loading vendor data.', 'error');
  }
}

function renderVendorTable(vendors) {
  const el = document.getElementById('vendor-table-body');
  if (!el) return;

  if (!vendors.length) {
    el.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:32px;color:var(--ink-light)">No vendor data available.</td></tr>`;
    return;
  }

  el.innerHTML = vendors.map(v => `
    <tr>
      <td style="font-weight:600">${escHtml(v.vendor)}</td>
      <td class="mono">${fmt(v.total_invoices)}</td>
      <td class="mono">${fmtCurrency(v.total_amount)}</td>
      <td class="mono">${fmt(v.risky_invoices)}</td>
      <td class="mono">${fmt(v.high_risk_invoices)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="progress-bar" style="width:70px">
            <div class="progress-fill ${v.risk_tier === 'HIGH' ? 'red' : v.risk_tier === 'MEDIUM' ? 'amber' : 'green'}" style="width:${Math.min(100, v.risky_percentage).toFixed(0)}%"></div>
          </div>
          <span class="mono text-xs">${v.risky_percentage.toFixed(1)}%</span>
        </div>
      </td>
      <td class="mono">${v.avg_score.toFixed(2)}</td>
      <td>${tierBadge(v.risk_tier)}</td>
    </tr>
  `).join('');
}

/* ============================================================
   SECTION: AP CONTROL
   ============================================================ */
async function loadAPControl() {
  if (APP.apControl) { renderAPControl(APP.apControl); return; }

  try {
    const res = await fetch('/api/ap_control_overview');
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Failed to load AP data.', 'error'); return; }
    APP.apControl = data;
    renderAPControl(data);
  } catch (err) {
    showToast('Network error loading AP data.', 'error');
  }
}

function renderAPControl(data) {
  const s = data.summary;
  const dist = data.risk_distribution || {};
  const trend = data.monthly_trend || [];
  const topVendors = data.top_risky_vendors || [];

  // KPIs
  const kpiEl = document.getElementById('ap-kpis');
  if (kpiEl) {
    kpiEl.innerHTML = `
      <div class="kpi-card blue">
        <div class="kpi-badge">📋</div>
        <div class="kpi-label">Total Invoices</div>
        <div class="kpi-value"><span>${fmt(s.total_invoices)}</span></div>
        <div class="kpi-sub">${fmtCurrency(s.total_amount)} total</div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-badge">🔴</div>
        <div class="kpi-label">High Risk</div>
        <div class="kpi-value"><span>${fmt(s.high_risk_invoices)}</span></div>
        <div class="kpi-sub">${fmtCurrency(s.high_risk_amount)}</div>
      </div>
      <div class="kpi-card amber">
        <div class="kpi-badge">🟠</div>
        <div class="kpi-label">Total Risky</div>
        <div class="kpi-value"><span>${fmt(s.risky_invoices)}</span></div>
        <div class="kpi-sub">${fmtCurrency(s.total_risk_amount)}</div>
      </div>
      <div class="kpi-card green">
        <div class="kpi-badge">🟢</div>
        <div class="kpi-label">Clean</div>
        <div class="kpi-value"><span>${fmt(s.total_invoices - s.risky_invoices)}</span></div>
        <div class="kpi-sub">No risk flags</div>
      </div>
    `;
  }

  // Donut / distribution
  const distEl = document.getElementById('ap-distribution');
  if (distEl) {
    const total = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
    const colors = { HIGH: '#CC2A2A', MEDIUM: '#B85C00', LOW: '#1A7A4A', UNKNOWN: '#9AAABB' };
    let offset = 0;
    const r = 52, cx = 64, cy = 64, circum = 2 * Math.PI * r;
    const segments = Object.entries(dist).map(([k, v]) => {
      const pct = v / total;
      const dash = pct * circum;
      const gap = circum - dash;
      const seg = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${colors[k]}" stroke-width="18" stroke-dasharray="${dash} ${gap}" stroke-dashoffset="${-offset * circum}" />`;
      offset += pct;
      return { key: k, value: v, color: colors[k], seg };
    });

    distEl.innerHTML = `
      <div class="donut-wrap">
        <div class="donut-chart" style="width:128px;height:128px">
          <svg width="128" height="128" viewBox="0 0 128 128" style="transform:rotate(-90deg)">
            <circle cx="64" cy="64" r="52" fill="none" stroke="var(--border)" stroke-width="18"></circle>
            ${segments.map(s => s.seg).join('')}
          </svg>
          <div class="donut-center">
            <div class="donut-center-value">${fmt(total)}</div>
            <div class="donut-center-label">Total</div>
          </div>
        </div>
        <div class="donut-legend">
          ${segments.map(s => `
            <div class="donut-legend-item">
              <div class="donut-legend-dot" style="background:${s.color}"></div>
              <span class="donut-legend-label">${s.key}</span>
              <span class="donut-legend-value">${fmt(s.value)}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // Monthly trend table
  const trendEl = document.getElementById('ap-trend-body');
  if (trendEl) {
    trendEl.innerHTML = trend.map(t => `
      <tr>
        <td class="mono">${escHtml(t.month)}</td>
        <td class="mono">${fmt(t.invoices)}</td>
        <td class="mono">${fmtCurrency(t.total_amount)}</td>
        <td class="mono">${fmt(t.risky_invoices)}</td>
        <td class="mono">${fmt(t.high_risk_invoices)}</td>
      </tr>
    `).join('');
  }

  // Top risky vendors
  const topVendEl = document.getElementById('ap-top-vendors');
  if (topVendEl) {
    topVendEl.innerHTML = topVendors.map((v, i) => `
      <div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-light)">
        <div style="width:22px;height:22px;border-radius:50%;background:var(--sap-blue-light);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:var(--sap-blue);flex-shrink:0">${i+1}</div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:12.5px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(v.vendor)}</div>
          <div style="font-size:11px;color:var(--ink-light)">${fmt(v.risky_count)} risky invoices</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:13px;font-weight:600;color:var(--high)">${fmtCurrency(v.risky_amount)}</div>
          <div style="font-size:10px;color:var(--ink-light)">Max: ${v.max_score.toFixed(2)}</div>
        </div>
      </div>
    `).join('');
  }
}

/* ============================================================
   SECTION: RAG QUERY
   ============================================================ */
async function sendRagQuery() {
  const input = document.getElementById('rag-question');
  const question = input?.value?.trim();
  if (!question) return;

  appendChat('rag-chat', question, 'user');
  input.value = '';

  const thinkingId = 'thinking-' + Date.now();
  appendChat('rag-chat', '<div class="flex-center gap-8"><div class="spinner sm"></div> <em>Searching invoices…</em></div>', 'system', thinkingId);

  try {
    const res = await fetch('/api/rag/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();

    removeChat('rag-chat', thinkingId);

    if (!res.ok) {
      appendChat('rag-chat', `❌ ${data.error}`, 'system');
      return;
    }

    let msg = data.answer || '—';
    if (data.similar_invoices && data.similar_invoices.length) {
      msg += `\n\n**Similar invoices found:** ${data.similar_invoices.slice(0, 3).map(s => s.invoice_id || s.id || '').filter(Boolean).join(', ')}`;
    }
    appendChat('rag-chat', msg, 'assistant');
  } catch (err) {
    removeChat('rag-chat', thinkingId);
    appendChat('rag-chat', '❌ Network error. Please try again.', 'system');
  }
}

function appendChat(containerId, text, role, id) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  if (id) div.id = id;
  div.innerHTML = String(text).replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function removeChat(containerId, id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function handleRagKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendRagQuery();
  }
}

/* ============================================================
   SECTION: DOCFINDER
   ============================================================ */
async function uploadDocs() {
  const input = document.getElementById('doc-file-input');
  if (!input || !input.files.length) {
    showToast('Please select document files.', 'warning');
    return;
  }

  const formData = new FormData();
  Array.from(input.files).forEach(f => formData.append('files', f));

  showLoading('Indexing Documents…', 'Building semantic knowledge base');

  try {
    const res = await fetch('/api/docfinder/process', { method: 'POST', body: formData });
    const data = await res.json();
    hideLoading();

    if (!res.ok) { showToast(data.error || 'Failed to process files.', 'error'); return; }

    APP.docFiles = data.files || [];
    showToast(`Indexed ${data.summary.total_files} files (${data.summary.total_chunks} chunks).`, 'success');

    const filesEl = document.getElementById('doc-indexed-files');
    if (filesEl) {
      filesEl.innerHTML = `
        <div class="alert success"><span>✅</span> ${escHtml(data.message || 'Documents indexed successfully.')}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px">
          ${APP.docFiles.map(f => `<span style="background:var(--sap-blue-light);color:var(--sap-blue-dark);padding:4px 10px;border-radius:5px;font-size:11.5px;font-weight:500">📄 ${escHtml(f)}</span>`).join('')}
        </div>
      `;
    }
  } catch (err) {
    hideLoading();
    showToast('Network error.', 'error');
  }
}

async function sendDocQuery() {
  const input = document.getElementById('doc-question');
  const question = input?.value?.trim();
  if (!question) return;

  appendChat('doc-chat', question, 'user');
  input.value = '';

  const thinkingId = 'thinking-' + Date.now();
  appendChat('doc-chat', '<div class="flex-center gap-8"><div class="spinner sm"></div> <em>Searching documents…</em></div>', 'system', thinkingId);

  try {
    const res = await fetch('/api/docfinder/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    removeChat('doc-chat', thinkingId);

    if (!res.ok) { appendChat('doc-chat', `❌ ${data.error}`, 'system'); return; }

    const answer = data.answer || data.response || JSON.stringify(data);
    appendChat('doc-chat', answer, 'assistant');
  } catch (err) {
    removeChat('doc-chat', thinkingId);
    appendChat('doc-chat', '❌ Network error.', 'system');
  }
}

function handleDocKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendDocQuery();
  }
}

/* ============================================================
   SECTION: WHAT-IF SIMULATOR
   ============================================================ */
async function runSimulator() {
  const getVal = id => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };

  const payload = {
    min_amount_dual_approval: parseFloat(getVal('sim-dual-amount')) || 0,
    block_new_vendor_days: parseInt(getVal('sim-vendor-days')) || 0,
    block_no_po_min_amount: parseFloat(getVal('sim-no-po-amount')) || 0,
  };

  const resultEl = document.getElementById('sim-result');
  if (resultEl) resultEl.innerHTML = `<div class="flex-center gap-8"><div class="spinner"></div> Running simulation…</div>`;

  try {
    const res = await fetch('/api/what_if_simulator', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) { showToast(data.error || 'Simulation failed.', 'error'); return; }

    const b = data.base;
    const imp = data.impact;
    const pct = b.risky_invoices > 0 ? (imp.blocked_risky_invoices / b.risky_invoices * 100).toFixed(1) : '0.0';

    if (resultEl) {
      resultEl.innerHTML = `
        <div class="sim-result-box">
          <div class="flex-between">
            <div>
              <div style="font-size:14px;font-weight:600;color:var(--ink)">Simulation Results</div>
              <div style="font-size:12px;color:var(--ink-light);margin-top:2px">Impact of your policy configuration</div>
            </div>
            <div style="font-size:28px;font-weight:700;color:var(--low)">${pct}%</div>
          </div>
          <div class="sim-result-grid">
            <div class="sim-result-item">
              <div class="sim-result-label">Blocked Risky</div>
              <div class="sim-result-value good">${fmt(imp.blocked_risky_invoices)}</div>
            </div>
            <div class="sim-result-item">
              <div class="sim-result-label">Blocked Amount</div>
              <div class="sim-result-value good">${fmtCurrency(imp.blocked_risk_amount)}</div>
            </div>
            <div class="sim-result-item">
              <div class="sim-result-label">Remaining Risky</div>
              <div class="sim-result-value bad">${fmt(imp.new_risky_invoices)}</div>
            </div>
            <div class="sim-result-item">
              <div class="sim-result-label">Dual Approval Hits</div>
              <div class="sim-result-value">${fmt(imp.dual_approval_hits)}</div>
            </div>
            <div class="sim-result-item">
              <div class="sim-result-label">New Vendor Hits</div>
              <div class="sim-result-value">${fmt(imp.new_vendor_hits)}</div>
            </div>
            <div class="sim-result-item">
              <div class="sim-result-label">No-PO Hits</div>
              <div class="sim-result-value">${fmt(imp.no_po_hits)}</div>
            </div>
          </div>
        </div>
      `;
    }
  } catch (err) {
    showToast('Network error running simulation.', 'error');
  }
}

/* ============================================================
   SECTION: PLAYBOOK
   ============================================================ */
async function loadPlaybook() {
  const el = document.getElementById('playbook-content');
  if (!el) return;
  el.innerHTML = `<div class="flex-center gap-8" style="padding:32px"><div class="spinner"></div> Loading recommendations…</div>`;

  try {
    const res = await fetch('/api/fraud_playbook');
    const data = await res.json();

    if (!res.ok) { el.innerHTML = `<div class="alert error"><span>❌</span>${escHtml(data.error)}</div>`; return; }

    const h = data.headline_risk;
    const recs = data.top_recommendations || [];
    const qw = data.quick_wins || [];
    const wl = data.watchlist_vendors || [];

    el.innerHTML = `
      <div class="alert info mb-24">
        <span class="alert-icon">📋</span>
        <div>${escHtml(data.executive_summary)}</div>
      </div>

      <div class="kpi-row mb-24">
        <div class="kpi-card red"><div class="kpi-badge">🔴</div><div class="kpi-label">High Risk Invoices</div><div class="kpi-value"><span>${fmt(h.high_risk_invoices)}</span></div><div class="kpi-sub">${fmtCurrency(h.high_risk_amount)}</div></div>
        <div class="kpi-card amber"><div class="kpi-badge">🏦</div><div class="kpi-label">Bank Change Flags</div><div class="kpi-value"><span>${fmt(h.bank_change_count)}</span></div></div>
        <div class="kpi-card amber"><div class="kpi-badge">🆕</div><div class="kpi-label">New Vendors (≤30d)</div><div class="kpi-value"><span>${fmt(h.new_vendor_count)}</span></div></div>
        <div class="kpi-card blue"><div class="kpi-badge">📝</div><div class="kpi-label">No-PO Invoices</div><div class="kpi-value"><span>${fmt(h.no_po_count)}</span></div></div>
      </div>

      <div class="grid-2 mb-24">
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title"><div class="card-title-icon">🎯</div>Top Recommendations</div>
            </div>
          </div>
          <div class="card-body" style="padding-top:12px">
            ${recs.map(r => `
              <div class="playbook-rec">
                <div class="playbook-priority ${r.priority}"></div>
                <div style="flex:1">
                  <div class="playbook-rec-title">${escHtml(r.title)}</div>
                  <div class="playbook-rec-reason">${escHtml(r.reason)}</div>
                  <div class="playbook-rec-action">→ ${escHtml(r.action)}</div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <div style="display:flex;flex-direction:column;gap:18px">
          <div class="card">
            <div class="card-header">
              <div class="card-title"><div class="card-title-icon">⚡</div>Quick Wins</div>
            </div>
            <div class="card-body" style="padding-top:12px">
              ${qw.map((q, i) => `
                <div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border-light)">
                  <div style="width:20px;height:20px;border-radius:50%;background:var(--low-bg);color:var(--low);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0">${i+1}</div>
                  <span style="font-size:12.5px;color:var(--ink-mid)">${escHtml(q)}</span>
                </div>
              `).join('')}
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <div class="card-title"><div class="card-title-icon">👁</div>Watchlist Vendors</div>
            </div>
            <div class="card-body" style="padding-top:8px">
              ${wl.map((v, i) => `
                <div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-light)">
                  <div style="width:24px;height:24px;border-radius:50%;background:var(--high-bg);color:var(--high);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">${i+1}</div>
                  <div style="flex:1">
                    <div style="font-weight:600;font-size:12.5px">${escHtml(v.vendor)}</div>
                    <div style="font-size:11px;color:var(--ink-light)">${fmt(v.risky_invoices)} risky</div>
                  </div>
                  <div style="font-weight:600;color:var(--high);font-size:12.5px">${fmtCurrency(v.risky_amount)}</div>
                </div>
              `).join('')}
            </div>
          </div>
        </div>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<div class="alert error"><span>❌</span>Failed to load playbook.</div>`;
  }
}

/* ============================================================
   LOGOUT
   ============================================================ */
function logout() {
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/logout';
  document.body.appendChild(form);
  form.submit();
}

/* ============================================================
   INIT
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  initUploadZone();

  // Nav items
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => navigate(el.dataset.section));
  });

  // Default section
  navigate('upload');
});
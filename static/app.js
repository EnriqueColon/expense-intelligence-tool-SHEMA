// --- Auth ---
const token    = localStorage.getItem('shema_token');
const username = localStorage.getItem('shema_user');

if (!token) { window.location.replace('/login'); }

document.getElementById('user-display').textContent = username || '';

function logout() {
  localStorage.removeItem('shema_token');
  localStorage.removeItem('shema_user');
  window.location.replace('/login');
}

// --- Tab navigation ---
const TAB_TITLES = { upload: 'Upload', dashboard: 'Dashboard', history: 'Transaction History', categories: 'Manage Categories' };
function switchTab(tab) {
  ['upload', 'dashboard', 'history', 'categories'].forEach(t => {
    document.getElementById('view-' + t).classList.toggle('hidden', tab !== t);
    document.getElementById('tab-' + t).classList.toggle('active', tab === t);
  });
  const titleEl = document.getElementById('topbar-title');
  if (titleEl) titleEl.textContent = TAB_TITLES[tab] || '';
  if (tab === 'history')    loadHistory();
  if (tab === 'dashboard')  loadDashboard();
  if (tab === 'categories') renderCategories();
}

// --- State ---
let transactions        = [];
let currentFile         = '';
let currentStmtPeriod   = null;   // 'YYYY-MM' extracted from the last uploaded PDF
let donutChart    = null;
let barChart      = null;
let activeBatchId = null;
let batchTxns     = [];
let lineChart     = null;
let analyticsData = [];
let dashDonutChart  = null;
let dashBarChart    = null;
let dashVendorChart = null;

const CATEGORIES = [
  'Advertising & Marketing', 'Bank Charges & Fees', 'Computer & Internet',
  'Dues & Subscriptions', 'Equipment & Supplies', 'Insurance',
  'Meals & Entertainment', 'Office Supplies', 'Other Expense',
  'Payment', 'Postage & Shipping', 'Professional Fees',
  'Rent', 'Repairs & Maintenance', 'Software', 'Telephone/Internet/Web',
  'Travel', 'Utilities', 'Vehicle', 'Unclassified'
];

const CHART_COLORS = [
  '#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6',
  '#06b6d4','#f97316','#84cc16','#ec4899','#64748b',
  '#0ea5e9','#a78bfa','#34d399','#fbbf24','#f87171',
  '#7dd3fc','#6ee7b7','#fcd34d','#fca5a5','#c4b5fd'
];

// --- Upload (supports multiple files) ---
const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const loadingEl = document.getElementById('loading');
const errorEl   = document.getElementById('error');
const resultsEl = document.getElementById('results');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
});
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => { if (e.target.files.length) handleFiles(e.target.files); });

async function handleFiles(fileList) {
  const files = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
  if (!files.length) { showError('Please upload PDF files.'); return; }

  hideError();
  dropZone.classList.add('hidden');
  loadingEl.classList.remove('hidden');
  resultsEl.classList.add('hidden');
  resetSaveStatus();

  const loadingText = document.getElementById('loading-text');
  const bulkProgress = document.getElementById('bulk-progress');
  const bulkBar = document.getElementById('bulk-bar');
  const multi = files.length > 1;

  if (multi) bulkProgress.classList.remove('hidden');

  const allTransactions = [];
  const fileNames = [];
  const errors = [];

  for (let idx = 0; idx < files.length; idx++) {
    const file = files[idx];
    loadingText.textContent = multi
      ? `Processing file ${idx + 1} of ${files.length}: ${file.name}`
      : 'Parsing and classifying transactions…';
    if (multi) bulkBar.style.width = Math.round((idx / files.length) * 100) + '%';

    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token },
        body: formData
      });
      if (res.status === 401) { logout(); return; }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        errors.push(file.name + ': ' + (err.detail || 'Server error'));
        continue;
      }
      const data = await res.json();
      allTransactions.push(...(data.transactions || []));
      fileNames.push(file.name);
      // Capture the statement period from the last successfully parsed file
      if (data.statement_period) currentStmtPeriod = data.statement_period;
    } catch (err) {
      errors.push(file.name + ': ' + err.message);
    }
  }

  if (multi) bulkBar.style.width = '100%';
  loadingEl.classList.add('hidden');
  bulkProgress.classList.add('hidden');
  bulkBar.style.width = '0%';
  fileInput.value = '';

  if (!allTransactions.length) {
    showError('No transactions found. ' + (errors.length ? errors.join(' | ') : ''));
    dropZone.classList.remove('hidden');
    return;
  }

  if (errors.length) showError('Some files had errors: ' + errors.join(' | '));

  currentFile = fileNames.join(', ');
  transactions = allTransactions;
  render();
  resultsEl.classList.remove('hidden');
}

function render() { renderStats(); renderCardholders(); renderCharts(); renderTable(); renderVendorAnalysis(); }

function renderStats() {
  let charges = 0, credits = 0;
  transactions.forEach(t => {
    const a = parseFloat(t.Amount) || 0;
    if (a < 0) credits += Math.abs(a); else charges += a;
  });
  const fmt = v => '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  document.getElementById('stats-grid').innerHTML =
    '<div class="stat-card"><div class="stat-label">Total Transactions</div><div class="stat-value">' + transactions.length + '</div></div>' +
    '<div class="stat-card amber"><div class="stat-label">Total Charges</div><div class="stat-value">' + fmt(charges) + '</div></div>' +
    '<div class="stat-card green"><div class="stat-label">Total Credits / Payments</div><div class="stat-value">' + fmt(credits) + '</div></div>' +
    '<div class="stat-card"><div class="stat-label">Uploaded By</div><div class="stat-value" style="font-size:1.1rem">' + (username || '-') + '</div></div>';
}

function renderCardholders() {
  const names = [...new Set(transactions.map(t => t.Cardholder || 'Primary'))].sort();
  const el = document.getElementById('cardholder-rename');
  el.innerHTML = names.map(name =>
    '<div class="ch-row">' +
      '<span class="ch-badge">' + esc(name) + '</span>' +
      '<span class="ch-arrow">&#8594;</span>' +
      '<input class="ch-input" type="text" placeholder="Rename to…" data-old="' + esc(name) + '" />' +
      '<button class="btn btn-sm btn-primary ch-apply" onclick="renameCardholder(this)">Apply</button>' +
    '</div>'
  ).join('');
}

function renameCardholder(btnEl) {
  const input  = btnEl.previousElementSibling;
  const oldName = input.dataset.old;
  const newName = input.value.trim();
  if (!newName || newName === oldName) return;
  transactions.forEach(t => { if ((t.Cardholder || 'Primary') === oldName) t.Cardholder = newName; });
  render();
}

function renderCharts() {
  const totals = {};
  transactions.forEach(t => {
    const a = parseFloat(t.Amount) || 0;
    if (a <= 0) return;
    const cat = t.Category || 'Unclassified';
    totals[cat] = (totals[cat] || 0) + a;
  });
  const sorted = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const labels = sorted.map(x => x[0]);
  const data   = sorted.map(x => +x[1].toFixed(2));

  if (donutChart) donutChart.destroy();
  donutChart = new Chart(document.getElementById('chart-donut'), {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: CHART_COLORS.slice(0, labels.length), borderWidth: 2 }] },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 10 } },
        tooltip: { callbacks: { label: ctx => ' $' + ctx.parsed.toLocaleString('en-US', { minimumFractionDigits: 2 }) } }
      }
    }
  });

  const top = sorted.slice(0, 10);
  if (barChart) barChart.destroy();
  barChart = new Chart(document.getElementById('chart-bar'), {
    type: 'bar',
    data: {
      labels: top.map(x => x[0]),
      datasets: [{ label: 'Total ($)', data: top.map(x => +x[1].toFixed(2)), backgroundColor: '#3b82f6', borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { callback: v => '$' + Number(v).toLocaleString() } } }
    }
  });
}

function renderTable() {
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';
  transactions.forEach(function(txn, i) {
    const amt = parseFloat(txn.Amount) || 0;
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + (txn['Sale Date'] || '') + '</td>' +
      '<td>' + (txn['Post Date'] || '') + '</td>' +
      '<td class="desc" title="' + esc(txn.Description || '') + '">' + esc(txn.Description || '') + '</td>' +
      '<td class="amount' + (amt < 0 ? ' negative' : '') + '">$' + Math.abs(amt).toFixed(2) + '</td>' +
      '<td><select class="category-select" onchange="updateCategory(' + i + ', this.value)">' + buildOptions(txn.Category) + '</select></td>' +
      '<td>' + esc(txn['Cardholder'] || 'Primary') + '</td>';
    tbody.appendChild(tr);
  });
}

function buildOptions(selected) {
  const all = CATEGORIES.indexOf(selected) >= 0 ? CATEGORIES : [selected].concat(CATEGORIES).filter(Boolean);
  const unique = all.filter((v, i, a) => a.indexOf(v) === i);
  return unique.map(c =>
    '<option value="' + esc(c) + '"' + (c === selected ? ' selected' : '') + '>' + esc(c) + '</option>'
  ).join('');
}

function updateCategory(i, val) {
  transactions[i].Category = val;
  renderCharts();
  renderStats();
}

function downloadCSV() {
  const headers = ['Sale Date', 'Post Date', 'Description', 'Amount', 'Category', 'Cardholder', 'Processed By'];
  const rows = transactions.map(t =>
    headers.map(h => '"' + String(t[h] || '').replace(/"/g, '""') + '"').join(',')
  );
  triggerCSVDownload([headers.join(',')].concat(rows).join('\n'), 'classified_expenses.csv');
}

async function retrainModel() {
  const btn = document.getElementById('retrain-btn');
  const resultEl = document.getElementById('retrain-result');
  btn.disabled = true;
  btn.textContent = 'Retraining...';
  resultEl.className = 'retrain-result retrain-loading';
  resultEl.textContent = 'Training model on current transactions...';
  resultEl.classList.remove('hidden');
  try {
    const res = await fetch('/api/retrain', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ transactions })
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Retrain failed');
    const persistMsg = data.persisted
      ? 'Model saved to Vercel Blob — will be used on all future requests.'
      : 'Model updated for this session only.';
    resultEl.className = 'retrain-result retrain-success';
    resultEl.innerHTML =
      '<strong>&#10003; Model retrained successfully</strong><br>' +
      'Trained on <strong>' + data.samples + '</strong> transactions &middot; ' +
      '<strong>' + data.categories.length + '</strong> categories learned<br>' +
      '<span class="retrain-note">' + persistMsg + '</span>';
  } catch (err) {
    resultEl.className = 'retrain-result retrain-error';
    resultEl.textContent = 'Retrain failed: ' + err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Retrain Model';
  }
}

// --- Save to Database ---
function resetSaveStatus() {
  const btn = document.getElementById('save-btn');
  const status = document.getElementById('save-status');
  btn.disabled = false;
  btn.textContent = '⇓ Save to Database';
  status.className = 'save-status hidden';
}

async function saveTransactions() {
  if (!transactions.length) return;
  const btn    = document.getElementById('save-btn');
  const status = document.getElementById('save-status');
  btn.disabled = true;
  btn.textContent = 'Saving…';
  status.className = 'save-status save-status-loading';
  status.textContent = 'Saving transactions…';
  status.classList.remove('hidden');
  try {
    const res = await fetch('/api/transactions/save', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: currentFile, transactions, statement_period: currentStmtPeriod })
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Save failed');
    btn.textContent = '✓ Saved';
    status.className = 'save-status save-status-ok';
    status.textContent = data.count + ' transactions saved.';
    loadDashboard();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = '⇓ Save to Database';
    status.className = 'save-status save-status-err';
    status.textContent = 'Save failed: ' + err.message;
  }
}

// --- Dashboard ---
async function loadDashboard() {
  const loadingEl = document.getElementById('dash-loading');
  const emptyEl   = document.getElementById('dash-empty');
  const contentEl = document.getElementById('dash-content');

  loadingEl.classList.remove('hidden');
  emptyEl.classList.add('hidden');
  contentEl.classList.add('hidden');

  const fromVal = document.getElementById('dash-date-from').value;
  const toVal   = document.getElementById('dash-date-to').value;
  const chVal   = document.getElementById('dash-cardholder-filter').value;
  const params  = new URLSearchParams();
  if (fromVal) params.append('start',      fromVal);
  if (toVal)   params.append('end',        toVal);
  if (chVal)   params.append('cardholder', chVal);
  const qs = params.toString() ? '?' + params.toString() : '';

  try {
    const res = await fetch('/api/dashboard' + qs, {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to load dashboard');

    const { stats, categories, vendors } = data;

    // Populate cardholder dropdown (preserves current selection)
    populateDashCardholderDropdown(data.cardholders || []);

    // Auto-init pickers to the full available range on first load
    if (!fromVal && stats.min_month) document.getElementById('dash-date-from').value = stats.min_month;
    if (!toVal   && stats.max_month) document.getElementById('dash-date-to').value   = stats.max_month;

    if (!stats.total_transactions) {
      emptyEl.classList.remove('hidden');
      return;
    }

    renderDashboardStats(stats);
    renderDashboardCharts(categories, vendors);
    renderDashboardRetrainStats(data.labeled_transactions || 0);
    contentEl.classList.remove('hidden');
  } catch (e) {
    emptyEl.innerHTML = '<div class="card card-body" style="text-align:center;color:#dc2626;padding:3rem">Could not load dashboard: ' + esc(e.message) + '</div>';
    emptyEl.classList.remove('hidden');
  } finally {
    loadingEl.classList.add('hidden');
  }
}

function resetDashboardFilter() {
  document.getElementById('dash-date-from').value        = '';
  document.getElementById('dash-date-to').value          = '';
  document.getElementById('dash-cardholder-filter').value = '';
  loadDashboard();
}

// --- Excel report download ---
const REPORT_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

function buildPeriodLabel(from, to) {
  const fmt = p => { const [y, m] = p.split('-'); return REPORT_MONTHS[+m - 1] + ' ' + y; };
  if (from && to) return from === to ? fmt(from) : fmt(from) + ' \u2013 ' + fmt(to);
  if (from)       return fmt(from) + ' \u2013 present';
  if (to)         return 'Through ' + fmt(to);
  return 'All periods';
}

async function downloadReport() {
  const btn   = document.getElementById('btn-download-report');
  const errEl = document.getElementById('report-error');

  // Mirror the dashboard's current filters so the report is a snapshot of what
  // is on screen.
  const fromVal = document.getElementById('dash-date-from').value;
  const toVal   = document.getElementById('dash-date-to').value;
  const chVal   = document.getElementById('dash-cardholder-filter').value;

  const params = new URLSearchParams();
  if (fromVal) params.append('start',      fromVal);
  if (toVal)   params.append('end',        toVal);
  if (chVal)   params.append('cardholder', chVal);
  params.append('period_label', buildPeriodLabel(fromVal, toVal));

  btn.disabled    = true;
  btn.textContent = 'Preparing\u2026';
  errEl.classList.add('hidden');

  try {
    const res = await fetch('/api/report?' + params.toString(), {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) {
      // Failures come back as JSON even though a success is binary.
      let msg = 'Could not generate the report.';
      try { const d = await res.json(); if (d.detail) msg = d.detail; } catch (_) {}
      throw new Error(msg);
    }

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = 'SHEMA_Expense_Report_' + new Date().toISOString().slice(0, 10) + '.xlsx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Download Report';
  }
}

function populateDashCardholderDropdown(cardholders) {
  const sel     = document.getElementById('dash-cardholder-filter');
  const current = sel.value;
  sel.innerHTML = '<option value="">All Cardholders</option>';
  cardholders.forEach(ch => {
    const opt = document.createElement('option');
    opt.value       = ch;
    opt.textContent = ch;
    if (ch === current) opt.selected = true;
    sel.appendChild(opt);
  });
}

function renderDashboardStats(stats) {
  const fmt = v => '$' + (v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  document.getElementById('dash-stats-grid').innerHTML =
    '<div class="stat-card"><div class="stat-label">Total Transactions</div><div class="stat-value">' + (stats.total_transactions || 0) + '</div></div>' +
    '<div class="stat-card"><div class="stat-label">Total Batches</div><div class="stat-value">' + (stats.total_batches || 0) + '</div></div>' +
    '<div class="stat-card amber"><div class="stat-label">Total Charges</div><div class="stat-value">' + fmt(stats.total_charges) + '</div></div>' +
    '<div class="stat-card green"><div class="stat-label">Total Credits / Payments</div><div class="stat-value">' + fmt(stats.total_credits) + '</div></div>';
}

function renderDashboardCharts(categories, vendorRows) {
  const fmt = v => '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const labels = categories.map(c => c.category);
  const data   = categories.map(c => +c.total.toFixed(2));

  if (dashDonutChart) dashDonutChart.destroy();
  dashDonutChart = new Chart(document.getElementById('dash-chart-donut'), {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: CHART_COLORS.slice(0, labels.length), borderWidth: 2 }] },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 10 } },
        tooltip: { callbacks: { label: ctx => ' $' + ctx.parsed.toLocaleString('en-US', { minimumFractionDigits: 2 }) } }
      }
    }
  });

  const top = categories.slice(0, 10);
  if (dashBarChart) dashBarChart.destroy();
  dashBarChart = new Chart(document.getElementById('dash-chart-bar'), {
    type: 'bar',
    data: {
      labels: top.map(c => c.category),
      datasets: [{ label: 'Total ($)', data: top.map(c => +c.total.toFixed(2)), backgroundColor: '#3b82f6', borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { callback: v => '$' + Number(v).toLocaleString() } } }
    }
  });

  // Normalize + re-aggregate vendors from raw DB descriptions
  const vendorMap = {};
  vendorRows.forEach(row => {
    const vendor = normalizeVendor(row.description);
    if (!vendorMap[vendor]) vendorMap[vendor] = { count: 0, total: 0 };
    vendorMap[vendor].count += row.count;
    vendorMap[vendor].total += row.total;
  });
  const sorted = Object.entries(vendorMap)
    .map(([vendor, v]) => ({ vendor, count: v.count, total: v.total, avg: v.total / v.count }))
    .sort((a, b) => b.total - a.total);

  const tbody = document.getElementById('dash-vendor-body');
  tbody.innerHTML = '';
  sorted.forEach(row => {
    const tr = document.createElement('tr');
    tr.dataset.vendor = row.vendor;
    tr.innerHTML =
      '<td class="desc">' + esc(row.vendor) + '</td>' +
      '<td style="text-align:center">' + row.count + '</td>' +
      '<td class="amount">' + fmt(row.total) + '</td>' +
      '<td class="amount">' + fmt(row.avg) + '</td>';
    tbody.appendChild(tr);
  });
  populateVendorDropdown('dash-vendor-filter-select', sorted);

  const topV = sorted.slice(0, 10);
  if (dashVendorChart) dashVendorChart.destroy();
  dashVendorChart = new Chart(document.getElementById('dash-chart-vendor'), {
    type: 'bar',
    data: {
      labels: topV.map(r => r.vendor.length > 30 ? r.vendor.slice(0, 28) + '…' : r.vendor),
      datasets: [{
        label: 'Total Spend ($)',
        data: topV.map(r => +r.total.toFixed(2)),
        backgroundColor: CHART_COLORS.slice(0, topV.length),
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: 'y', responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { callback: v => '$' + Number(v).toLocaleString() } } }
    }
  });
}

function renderDashboardRetrainStats(labeled) {
  const el = document.getElementById('db-retrain-stats');
  if (!el) return;
  el.innerHTML =
    '<span class="retrain-stat-pill">' + labeled.toLocaleString() +
    ' labeled transaction' + (labeled !== 1 ? 's' : '') + ' available for training</span>';
}

async function retrainFromDatabase() {
  const btn      = document.getElementById('db-retrain-btn');
  const resultEl = document.getElementById('db-retrain-result');
  btn.disabled = true;
  btn.textContent = 'Retraining…';
  resultEl.className = 'retrain-result retrain-loading';
  resultEl.textContent = 'Training model on all database transactions…';
  resultEl.classList.remove('hidden');
  try {
    const res = await fetch('/api/retrain/database', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Retrain failed');
    const persistMsg = data.persisted
      ? 'Model saved to Vercel Blob — all future uploads will use the updated model.'
      : 'Model updated for this session only.';
    resultEl.className = 'retrain-result retrain-success';
    resultEl.innerHTML =
      '<strong>&#10003; Model retrained successfully</strong><br>' +
      'Trained on <strong>' + data.samples + '</strong> transactions &middot; ' +
      '<strong>' + data.categories.length + '</strong> categories learned<br>' +
      '<span class="retrain-note">' + persistMsg + '</span>';
  } catch (err) {
    resultEl.className = 'retrain-result retrain-error';
    resultEl.textContent = 'Retrain failed: ' + err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '↺ Retrain from Database';
  }
}

// --- Analytics (monthly line chart) ---
async function loadAnalytics() {
  const emptyEl = document.getElementById('analytics-empty');
  try {
    const res = await fetch('/api/transactions/analytics', {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Analytics API error');
    analyticsData = data.data || [];

    // Populate category dropdown with all known categories plus any from data
    const sel = document.getElementById('category-filter');
    const dataCats = analyticsData.map(r => r.category);
    const allCats = [...new Set([...dataCats, ...CATEGORIES.filter(c => c !== 'Unclassified')])].sort();
    while (sel.options.length > 2) sel.remove(2);
    allCats.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = c;
      sel.appendChild(opt);
    });

    // Auto-initialize date range to cover all available data
    if (analyticsData.length) {
      const allMonths = [...new Set(analyticsData.map(r => r.month))].sort();
      const fromEl = document.getElementById('date-from');
      const toEl   = document.getElementById('date-to');
      if (!fromEl.value) fromEl.value = allMonths[0];
      if (!toEl.value)   toEl.value   = allMonths[allMonths.length - 1];
    }

    if (!analyticsData.length) {
      emptyEl.classList.remove('hidden');
      if (lineChart) { lineChart.destroy(); lineChart = null; }
    } else {
      emptyEl.classList.add('hidden');
      renderAnalyticsChart();
    }
  } catch (e) {
    emptyEl.textContent = 'Could not load analytics: ' + e.message;
    emptyEl.classList.remove('hidden');
  }
}

function updateAnalyticsChart() { renderAnalyticsChart(); }

function renderAnalyticsChart() {
  if (!analyticsData.length) return;

  const filter  = document.getElementById('category-filter').value;
  const fromVal = document.getElementById('date-from').value; // YYYY-MM or ''
  const toVal   = document.getElementById('date-to').value;   // YYYY-MM or ''

  const filtered = analyticsData.filter(r => {
    if (fromVal && r.month < fromVal) return false;
    if (toVal   && r.month > toVal)   return false;
    return true;
  });

  const months = [...new Set(filtered.map(r => r.month))].sort();
  const monthLabels = months.map(m => {
    const [y, mo] = m.split('-');
    return new Date(+y, +mo - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  });

  let datasets = [];

  if (filter === '__all__') {
    const catTotals = {};
    filtered.forEach(r => { catTotals[r.category] = (catTotals[r.category] || 0) + r.total; });
    const topCats = Object.entries(catTotals).sort((a, b) => b[1] - a[1]).slice(0, 6).map(e => e[0]);
    datasets = topCats.map((cat, idx) => {
      const byMonth = {};
      filtered.filter(r => r.category === cat).forEach(r => { byMonth[r.month] = r.total; });
      return {
        label: cat,
        data: months.map(m => +(byMonth[m] || 0).toFixed(2)),
        borderColor: CHART_COLORS[idx],
        backgroundColor: CHART_COLORS[idx] + '22',
        tension: 0.35,
        pointRadius: 4,
        pointHoverRadius: 6,
        fill: false
      };
    });
  } else if (filter === '__total__') {
    const totals = {};
    filtered.forEach(r => { totals[r.month] = (totals[r.month] || 0) + r.total; });
    datasets = [{
      label: 'Total Spend',
      data: months.map(m => +(totals[m] || 0).toFixed(2)),
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,0.08)',
      tension: 0.35,
      pointRadius: 4,
      pointHoverRadius: 6,
      fill: true
    }];
  } else {
    const byMonth = {};
    filtered.filter(r => r.category === filter).forEach(r => { byMonth[r.month] = r.total; });
    datasets = [{
      label: filter,
      data: months.map(m => +(byMonth[m] || 0).toFixed(2)),
      borderColor: '#7c3aed',
      backgroundColor: 'rgba(124,58,237,0.08)',
      tension: 0.35,
      pointRadius: 4,
      pointHoverRadius: 6,
      fill: true
    }];
  }

  if (lineChart) lineChart.destroy();
  lineChart = new Chart(document.getElementById('chart-line'), {
    type: 'line',
    data: { labels: monthLabels, datasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { font: { size: 11 }, padding: 12, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: ctx => ' ' + ctx.dataset.label + ': $' + ctx.parsed.y.toLocaleString('en-US', { minimumFractionDigits: 2 })
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { callback: v => '$' + Number(v).toLocaleString() },
          grid: { color: '#f1f5f9' }
        },
        x: { grid: { color: '#f1f5f9' } }
      }
    }
  });
}

// --- Transaction History ---
async function loadHistory() {
  loadAnalytics();

  const loadingDiv = document.getElementById('history-loading');
  const emptyDiv   = document.getElementById('history-empty');
  const tableWrap  = document.getElementById('history-table-wrap');
  const tbody      = document.getElementById('history-body');

  loadingDiv.classList.remove('hidden');
  emptyDiv.classList.add('hidden');
  tableWrap.style.display = 'none';
  closeBatchDetail();

  try {
    const res = await fetch('/api/transactions/history', {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to load history');

    const batches = data.batches || [];
    tbody.innerHTML = '';

    if (!batches.length) {
      emptyDiv.classList.remove('hidden');
    } else {
      batches.forEach(b => {
        const tr  = document.createElement('tr');
        const dt  = new Date(b.created_at);
        const dateStr = dt.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const sp = b.statement_period || '';
        tr.innerHTML =
          '<td>' + dateStr + '</td>' +
          '<td class="desc" title="' + esc(b.filename) + '">' + esc(b.filename || '—') + '</td>' +
          '<td style="white-space:nowrap">' +
            '<input type="month" class="month-input" value="' + sp + '" style="width:140px" ' +
              'onchange="updateStatementPeriod(' + b.id + ',this)" title="Statement billing period" />' +
          '</td>' +
          '<td style="text-align:center">' + b.transaction_count + '</td>' +
          '<td>' + esc(b.uploaded_by) + '</td>' +
          '<td class="history-actions">' +
            '<button class="btn btn-sm btn-primary" onclick="viewBatch(' + b.id + ',\'' + esc(b.filename) + '\',\'' + dateStr + '\')">View</button>' +
            '<button class="btn btn-sm btn-danger" onclick="deleteBatch(' + b.id + ',this)">Delete</button>' +
          '</td>';
        tbody.appendChild(tr);
      });
      tableWrap.style.display = '';
    }
  } catch (err) {
    emptyDiv.textContent = 'Error loading history: ' + err.message;
    emptyDiv.classList.remove('hidden');
  } finally {
    loadingDiv.classList.add('hidden');
  }
}

async function deleteBatch(batchId, btnEl) {
  if (!confirm('Delete this batch and all its transactions? This cannot be undone.')) return;
  btnEl.disabled = true;
  try {
    const res = await fetch('/api/transactions/batch/' + batchId, {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) throw new Error('Delete failed');
    if (activeBatchId === batchId) closeBatchDetail();
    loadHistory();
  } catch (err) {
    alert('Delete failed: ' + err.message);
    btnEl.disabled = false;
  }
}

async function updateStatementPeriod(batchId, inputEl) {
  const val = inputEl.value;  // 'YYYY-MM' or ''
  if (!val) return;
  const orig = inputEl.dataset.orig || inputEl.value;
  inputEl.dataset.orig = val;
  try {
    const res = await fetch('/api/transactions/batch/' + batchId + '/statement-period', {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ statement_period: val })
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) throw new Error('Update failed');
    // Refresh the analytics chart silently if history tab is active
    loadAnalytics();
  } catch (err) {
    alert('Could not update statement period: ' + err.message);
    inputEl.value = orig;
  }
}

async function viewBatch(batchId, filename, dateStr) {
  activeBatchId = batchId;
  const detail     = document.getElementById('history-batch-detail');
  const detailBody = document.getElementById('batch-detail-body');

  document.getElementById('batch-detail-title').textContent = filename || 'Transactions';
  document.getElementById('batch-detail-sub').textContent   = 'Saved ' + dateStr;
  detailBody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:#64748b">Loading…</td></tr>';
  detail.classList.remove('hidden');
  detail.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch('/api/transactions/batch/' + batchId, {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Load failed');
    batchTxns = data.transactions || [];
    renderBatchDetail(batchTxns);
  } catch (err) {
    detailBody.innerHTML = '<tr><td colspan="7" style="color:#dc2626;padding:1rem">' + esc(err.message) + '</td></tr>';
  }
}

function closeBatchDetail() {
  activeBatchId = null;
  batchTxns     = [];
  document.getElementById('history-batch-detail').classList.add('hidden');
}

function renderBatchDetail(txns) {
  // Cardholder rename bar
  const names = [...new Set(txns.map(t => t.cardholder || 'Primary'))].sort();
  const renameEl = document.getElementById('batch-ch-rename');
  renameEl.style.display = names.length ? '' : 'none';
  renameEl.innerHTML = names.map(name =>
    '<div class="ch-row">' +
      '<span class="ch-badge">' + esc(name) + '</span>' +
      '<span class="ch-arrow">&#8594;</span>' +
      '<input class="ch-input" type="text" placeholder="Rename to…" data-old="' + esc(name) + '" />' +
      '<button class="btn btn-sm btn-primary ch-apply" onclick="renameSavedCardholder(this)">Apply</button>' +
    '</div>'
  ).join('');

  // Transaction rows
  const tbody = document.getElementById('batch-detail-body');
  tbody.innerHTML = '';
  txns.forEach(txn => {
    const amt = parseFloat(txn.amount) || 0;
    const tr  = document.createElement('tr');
    tr.innerHTML =
      '<td>' + esc(txn.sale_date || '') + '</td>' +
      '<td>' + esc(txn.post_date || '') + '</td>' +
      '<td class="desc" title="' + esc(txn.description || '') + '">' + esc(txn.description || '') + '</td>' +
      '<td class="amount' + (amt < 0 ? ' negative' : '') + '">$' + Math.abs(amt).toFixed(2) + '</td>' +
      '<td><select class="category-select" onchange="patchTxnCategory(' + txn.id + ',this.value)">' + buildOptions(txn.category) + '</select></td>' +
      '<td>' + esc(txn.cardholder || 'Primary') + '</td>' +
      '<td><input class="notes-input" type="text" value="' + esc(txn.notes || '') + '" placeholder="Add note…" oninput="schedulePatchNotes(' + txn.id + ',this.value)" /></td>';
    tbody.appendChild(tr);
  });
}

async function renameSavedCardholder(btnEl) {
  const input   = btnEl.previousElementSibling;
  const oldName = input.dataset.old;
  const newName = input.value.trim();
  if (!newName || newName === oldName) return;

  btnEl.disabled = true;
  btnEl.textContent = 'Saving…';
  try {
    const res = await fetch('/api/transactions/batch/' + activeBatchId + '/rename-cardholder', {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_name: oldName, new_name: newName })
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Rename failed');
    // Update in-memory records and re-render
    batchTxns.forEach(t => { if ((t.cardholder || 'Primary') === oldName) t.cardholder = newName; });
    renderBatchDetail(batchTxns);
  } catch (e) {
    alert('Rename failed: ' + e.message);
    btnEl.disabled = false;
    btnEl.textContent = 'Apply';
  }
}

async function patchTxnCategory(txnId, category) {
  try {
    const res = await fetch('/api/transactions/' + txnId, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ category })
    });
    if (res.status === 401) logout();
  } catch (e) { /* silent */ }
}

var _noteTimers = {};
function schedulePatchNotes(txnId, notes) {
  clearTimeout(_noteTimers[txnId]);
  _noteTimers[txnId] = setTimeout(async () => {
    try {
      const res = await fetch('/api/transactions/' + txnId, {
        method: 'PATCH',
        headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes })
      });
      if (res.status === 401) logout();
    } catch (e) { /* silent */ }
  }, 600);
}

function downloadBatchCSV() {
  if (!batchTxns.length) return;
  const headers = ['Sale Date', 'Post Date', 'Description', 'Amount', 'Category', 'Cardholder', 'Notes', 'Processed By'];
  const rows = batchTxns.map(t =>
    [t.sale_date, t.post_date, t.description, t.amount, t.category, t.cardholder, t.notes, t.processed_by]
      .map(v => '"' + String(v || '').replace(/"/g, '""') + '"').join(',')
  );
  const name = (document.getElementById('batch-detail-title').textContent || 'transactions').replace('.pdf','') + '.csv';
  triggerCSVDownload([headers.join(',')].concat(rows).join('\n'), name);
}

function triggerCSVDownload(csv, filename) {
  const blob = new Blob([csv], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
}

// --- Helpers ---
function showError(msg) { errorEl.textContent = msg; errorEl.classList.remove('hidden'); }
function hideError()    { errorEl.classList.add('hidden'); }
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function applyVendorFilter(bodyId, selectId) {
  const val = document.getElementById(selectId).value;
  document.querySelectorAll('#' + bodyId + ' tr').forEach(tr => {
    tr.style.display = (!val || tr.dataset.vendor === val) ? '' : 'none';
  });
}

function populateVendorDropdown(selectId, sorted) {
  const fmt = v => '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sel = document.getElementById(selectId);
  sel.innerHTML = '<option value="">All Vendors</option>';
  sorted.forEach(row => {
    const opt = document.createElement('option');
    opt.value = row.vendor;
    opt.textContent = row.vendor + ' — ' + fmt(row.total);
    sel.appendChild(opt);
  });
}

// --- Vendor Analysis ---
let vendorChart = null;

const VENDOR_MAP = [
  [/amzn|amazon/i,                        'Amazon'],
  [/upwork/i,                              'Upwork'],
  [/godaddy/i,                             'GoDaddy'],
  [/intuit|quickbooks|turbotax/i,          'Intuit / QuickBooks'],
  [/at&t|att\.com/i,                       'AT&T'],
  [/google/i,                              'Google'],
  [/microsoft|msft/i,                      'Microsoft'],
  [/apple\.com|apple store/i,              'Apple'],
  [/dropbox/i,                             'Dropbox'],
  [/zoom/i,                                'Zoom'],
  [/slack/i,                               'Slack'],
  [/adobe/i,                               'Adobe'],
  [/shopify/i,                             'Shopify'],
  [/paypal/i,                              'PayPal'],
  [/stripe/i,                              'Stripe'],
  [/square/i,                              'Square'],
  [/uber\s?eats|ubereats/i,                'Uber Eats'],
  [/\buber\b/i,                            'Uber'],
  [/lyft/i,                                'Lyft'],
  [/doordash/i,                            'DoorDash'],
  [/grubhub/i,                             'Grubhub'],
  [/fedex/i,                               'FedEx'],
  [/usps/i,                                'USPS'],
  [/\bups\b/i,                             'UPS'],
  [/dhl/i,                                 'DHL'],
  [/verizon/i,                             'Verizon'],
  [/t-mobile|tmobile/i,                    'T-Mobile'],
  [/comcast|xfinity/i,                     'Comcast / Xfinity'],
  [/notion/i,                              'Notion'],
  [/canva/i,                               'Canva'],
  [/mailchimp/i,                           'Mailchimp'],
  [/hubspot/i,                             'HubSpot'],
  [/salesforce/i,                          'Salesforce'],
  [/docusign/i,                            'DocuSign'],
  [/propstream/i,                          'PropStream'],
  [/costar/i,                              'CoStar'],
  [/openai/i,                              'OpenAI'],
  [/chatgpt/i,                             'ChatGPT'],
];

// --- Categories Management ---
const CATEGORIES_STORAGE_KEY = 'shema_categories';

function loadStoredCategories() {
  const stored = localStorage.getItem(CATEGORIES_STORAGE_KEY);
  if (!stored) return;
  try {
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed) && parsed.length > 0) {
      CATEGORIES.length = 0;
      parsed.forEach(c => CATEGORIES.push(c));
    }
  } catch (e) {}
}

function saveCategories() {
  localStorage.setItem(CATEGORIES_STORAGE_KEY, JSON.stringify(CATEGORIES));
}

loadStoredCategories();

let _categoryWarningCallback = null;

function showCategoryWarning(onConfirm) {
  _categoryWarningCallback = onConfirm;
  document.getElementById('category-warning-modal').classList.remove('hidden');
}

function dismissCategoryWarning() {
  document.getElementById('category-warning-modal').classList.add('hidden');
  _categoryWarningCallback = null;
}

function confirmCategoryWarning() {
  document.getElementById('category-warning-modal').classList.add('hidden');
  if (_categoryWarningCallback) _categoryWarningCallback();
  _categoryWarningCallback = null;
}

function renderCategories() {
  const list = document.getElementById('cat-list');
  if (!list) return;
  list.innerHTML = '';
  CATEGORIES.forEach((cat, i) => {
    const isUnclassified = cat === 'Unclassified';
    const row = document.createElement('div');
    row.className = 'cat-row';
    row.innerHTML =
      '<span class="cat-badge">' + esc(cat) + '</span>' +
      '<input class="cat-rename-input" type="text" value="' + esc(cat) + '" id="cat-input-' + i + '"' + (isUnclassified ? ' disabled title="This category cannot be renamed."' : '') + ' />' +
      '<button class="btn btn-sm btn-ghost" onclick="promptRenameCategory(' + i + ')"' + (isUnclassified ? ' disabled' : '') + '>Rename</button>' +
      '<button class="btn btn-sm btn-danger" onclick="promptDeleteCategory(' + i + ')"' + (isUnclassified ? ' disabled title="This category cannot be deleted."' : '') + '>Delete</button>';
    list.appendChild(row);
  });
}

function promptRenameCategory(index) {
  const input = document.getElementById('cat-input-' + index);
  const newName = (input ? input.value : '').trim();
  if (!newName || newName === CATEGORIES[index]) return;
  if (CATEGORIES.some((c, i) => i !== index && c.toLowerCase() === newName.toLowerCase())) {
    alert('A category with that name already exists.');
    return;
  }
  showCategoryWarning(() => {
    CATEGORIES[index] = newName;
    saveCategories();
    renderCategories();
  });
}

function promptAddCategory() {
  const input = document.getElementById('cat-new-input');
  const newCat = (input ? input.value : '').trim();
  if (!newCat) return;
  if (CATEGORIES.map(c => c.toLowerCase()).includes(newCat.toLowerCase())) {
    alert('That category already exists.');
    return;
  }
  showCategoryWarning(() => {
    const insertAt = CATEGORIES.indexOf('Unclassified');
    CATEGORIES.splice(insertAt >= 0 ? insertAt : CATEGORIES.length, 0, newCat);
    saveCategories();
    renderCategories();
    if (input) input.value = '';
  });
}

function promptDeleteCategory(index) {
  if (CATEGORIES[index] === 'Unclassified') return;
  showCategoryWarning(() => {
    CATEGORIES.splice(index, 1);
    saveCategories();
    renderCategories();
  });
}

function normalizeVendor(desc) {
  let s = (desc || '').trim();
  for (const [re, name] of VENDOR_MAP) { if (re.test(s)) return name; }
  s = s.replace(/\*.*$/, '').trim();
  s = s.replace(/[\s-]?\d[\d\s-]{6,}\d/g, '').trim();
  s = s.replace(/\s+[A-Z]{2}$/, '').trim();
  s = s.replace(/https?:\/\/\S+/gi, '').trim();
  s = s.replace(/\w+\.(com|net|org|io|co)\b/gi, '').trim();
  return s.split(/\s+/).filter(Boolean).slice(0, 3).join(' ') || 'Unknown';
}

function renderVendorAnalysis() {
  const vendorMap = {};
  transactions.forEach(t => {
    const amt = parseFloat(t.Amount) || 0;
    if (amt <= 0) return;
    const vendor = normalizeVendor(t.Description);
    if (!vendorMap[vendor]) vendorMap[vendor] = { count: 0, total: 0 };
    vendorMap[vendor].count++;
    vendorMap[vendor].total += amt;
  });

  const sorted = Object.entries(vendorMap)
    .map(([vendor, v]) => ({ vendor, count: v.count, total: v.total, avg: v.total / v.count }))
    .sort((a, b) => b.total - a.total);

  const fmt = v => '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const tbody = document.getElementById('vendor-body');
  tbody.innerHTML = '';
  sorted.forEach(row => {
    const tr = document.createElement('tr');
    tr.dataset.vendor = row.vendor;
    tr.innerHTML =
      '<td class="desc">' + esc(row.vendor) + '</td>' +
      '<td style="text-align:center">' + row.count + '</td>' +
      '<td class="amount">' + fmt(row.total) + '</td>' +
      '<td class="amount">' + fmt(row.avg) + '</td>';
    tbody.appendChild(tr);
  });
  populateVendorDropdown('vendor-filter-select', sorted);

  const top = sorted.slice(0, 10);
  if (vendorChart) vendorChart.destroy();
  vendorChart = new Chart(document.getElementById('chart-vendor'), {
    type: 'bar',
    data: {
      labels: top.map(r => r.vendor.length > 30 ? r.vendor.slice(0, 28) + '…' : r.vendor),
      datasets: [{
        label: 'Total Spend ($)',
        data: top.map(r => +r.total.toFixed(2)),
        backgroundColor: CHART_COLORS.slice(0, top.length),
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: 'y', responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { callback: v => '$' + Number(v).toLocaleString() } } }
    }
  });
}

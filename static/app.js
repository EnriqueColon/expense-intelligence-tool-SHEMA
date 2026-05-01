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

// --- State ---
let transactions = [];
let donutChart   = null;
let barChart     = null;

const CATEGORIES = [
  'Advertising & Marketing', 'Bank Charges & Fees', 'Business Meals & Entertainment',
  'Computer & Internet', 'Dues and Subscriptions', 'Equipment & Supplies',
  'Insurance', 'Legal & Professional', 'Meals & Entertainment',
  'Office Supplies', 'Other Expense', 'Postage & Shipping',
  'Rent', 'Repairs & Maintenance', 'Software', 'Travel',
  'Utilities', 'Vehicle', 'Unclassified'
];

const CHART_COLORS = [
  '#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6',
  '#06b6d4','#f97316','#84cc16','#ec4899','#64748b',
  '#0ea5e9','#a78bfa','#34d399','#fbbf24','#f87171',
  '#7dd3fc','#6ee7b7','#fcd34d','#fca5a5','#c4b5fd'
];

// --- Upload ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const loadingEl = document.getElementById('loading');
const errorEl   = document.getElementById('error');
const resultsEl = document.getElementById('results');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => { if (e.target.files[0]) handleFile(e.target.files[0]); });

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) { showError('Please upload a PDF file.'); return; }
  hideError();
  dropZone.classList.add('hidden');
  loadingEl.classList.remove('hidden');
  resultsEl.classList.add('hidden');
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
      throw new Error(err.detail || 'Server error ' + res.status);
    }
    const data = await res.json();
    transactions = data.transactions || [];
    render();
    resultsEl.classList.remove('hidden');
  } catch (err) {
    showError(err.message);
    dropZone.classList.remove('hidden');
  } finally {
    loadingEl.classList.add('hidden');
  }
}

function render() { renderStats(); renderCharts(); renderTable(); renderVendorAnalysis(); }

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
    '<div class="stat-card red"><div class="stat-label">Net Spend</div><div class="stat-value">' + fmt(charges - credits) + '</div></div>' +
    '<div class="stat-card"><div class="stat-label">Uploaded By</div><div class="stat-value" style="font-size:1.1rem">' + (username || '-') + '</div></div>';
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
  const labels = sorted.map(function(x){ return x[0]; });
  const data   = sorted.map(function(x){ return +x[1].toFixed(2); });

  if (donutChart) donutChart.destroy();
  donutChart = new Chart(document.getElementById('chart-donut'), {
    type: 'doughnut',
    data: { labels: labels, datasets: [{ data: data, backgroundColor: CHART_COLORS.slice(0, labels.length), borderWidth: 2 }] },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 10 } },
        tooltip: { callbacks: { label: function(ctx) { return ' $' + ctx.parsed.toLocaleString('en-US', { minimumFractionDigits: 2 }); } } }
      }
    }
  });

  const top = sorted.slice(0, 10);
  if (barChart) barChart.destroy();
  barChart = new Chart(document.getElementById('chart-bar'), {
    type: 'bar',
    data: {
      labels: top.map(function(x){ return x[0]; }),
      datasets: [{ label: 'Total ($)', data: top.map(function(x){ return +x[1].toFixed(2); }), backgroundColor: '#3b82f6', borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { callback: function(v) { return '$' + Number(v).toLocaleString(); } } } }
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
  const unique = all.filter(function(v, i, a) { return a.indexOf(v) === i; });
  return unique.map(function(c) {
    return '<option value="' + esc(c) + '"' + (c === selected ? ' selected' : '') + '>' + esc(c) + '</option>';
  }).join('');
}

function updateCategory(i, val) {
  transactions[i].Category = val;
  renderCharts();
  renderStats();
}

function downloadCSV() {
  const headers = ['Sale Date', 'Post Date', 'Description', 'Amount', 'Category', 'Cardholder', 'Processed By'];
  const rows = transactions.map(function(t) {
    return headers.map(function(h) { return '"' + String(t[h] || '').replace(/"/g, '""') + '"'; }).join(',');
  });
  const blob = new Blob([[headers.join(',')].concat(rows).join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'classified_expenses.csv';
  document.body.appendChild(a); a.click(); a.remove();
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
      body: JSON.stringify({ transactions: transactions })
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Retrain failed');
    const persistMsg = data.persisted
      ? 'Model saved to Vercel Blob — will be used on all future requests.'
      : 'Model updated for this session. To persist across restarts, add Vercel Blob Storage to your project.';
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

function showError(msg) { errorEl.textContent = msg; errorEl.classList.remove('hidden'); }
function hideError()    { errorEl.classList.add('hidden'); }
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// --- Vendor Analysis ---
let vendorChart = null;

var VENDOR_MAP = [
  [/amzn|amazon/i,                         'Amazon'],
  [/upwork/i,                               'Upwork'],
  [/godaddy/i,                              'GoDaddy'],
  [/intuit|quickbooks|turbotax/i,           'Intuit / QuickBooks'],
  [/at&t|att\.com/i,                        'AT&T'],
  [/google/i,                               'Google'],
  [/microsoft|msft/i,                       'Microsoft'],
  [/apple\.com|apple store/i,               'Apple'],
  [/dropbox/i,                              'Dropbox'],
  [/zoom/i,                                 'Zoom'],
  [/slack/i,                                'Slack'],
  [/adobe/i,                                'Adobe'],
  [/shopify/i,                              'Shopify'],
  [/paypal/i,                               'PayPal'],
  [/stripe/i,                               'Stripe'],
  [/square/i,                               'Square'],
  [/uber\s?eats|ubereats/i,                 'Uber Eats'],
  [/\buber\b/i,                             'Uber'],
  [/lyft/i,                                 'Lyft'],
  [/doordash/i,                             'DoorDash'],
  [/grubhub/i,                              'Grubhub'],
  [/fedex/i,                                'FedEx'],
  [/usps/i,                                 'USPS'],
  [/\bups\b/i,                              'UPS'],
  [/dhl/i,                                  'DHL'],
  [/verizon/i,                              'Verizon'],
  [/t-mobile|tmobile/i,                     'T-Mobile'],
  [/comcast|xfinity/i,                      'Comcast / Xfinity'],
  [/notion/i,                               'Notion'],
  [/canva/i,                                'Canva'],
  [/mailchimp/i,                            'Mailchimp'],
  [/hubspot/i,                              'HubSpot'],
  [/salesforce/i,                           'Salesforce'],
  [/docusign/i,                             'DocuSign'],
  [/propstream/i,                           'PropStream'],
  [/costar/i,                               'CoStar'],
  [/openai/i,                               'OpenAI'],
  [/chatgpt/i,                              'ChatGPT'],
];

function normalizeVendor(desc) {
  var s = (desc || '').trim();

  // Check known vendor patterns first
  for (var i = 0; i < VENDOR_MAP.length; i++) {
    if (VENDOR_MAP[i][0].test(s)) return VENDOR_MAP[i][1];
  }

  // Strip common noise: everything after * (e.g. "AMZN Mktp US*G293S70U3")
  s = s.replace(/\*.*$/, '').trim();

  // Strip phone numbers (sequences of 7+ digits possibly with dashes)
  s = s.replace(/[\s-]?\d[\d\s-]{6,}\d/g, '').trim();

  // Strip trailing 2-letter state code (e.g. "VENDOR NAME CA")
  s = s.replace(/\s+[A-Z]{2}$/, '').trim();

  // Strip URLs
  s = s.replace(/https?:\/\/\S+/gi, '').trim();
  s = s.replace(/\w+\.(com|net|org|io|co)\b/gi, '').trim();

  // Take first 3 meaningful words
  var words = s.split(/\s+/).filter(Boolean).slice(0, 3);
  s = words.join(' ');

  return s || 'Unknown';
}

function renderVendorAnalysis() {
  // Build vendor totals from positive-amount transactions only
  var vendorMap = {};
  transactions.forEach(function(t) {
    var amt = parseFloat(t.Amount) || 0;
    if (amt <= 0) return;
    var vendor = normalizeVendor(t.Description);
    if (!vendorMap[vendor]) vendorMap[vendor] = { count: 0, total: 0 };
    vendorMap[vendor].count += 1;
    vendorMap[vendor].total += amt;
  });

  var sorted = Object.entries(vendorMap)
    .map(function(e) { return { vendor: e[0], count: e[1].count, total: e[1].total, avg: e[1].total / e[1].count }; })
    .sort(function(a, b) { return b.total - a.total; });

  var fmt = function(v) { return '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };

  // Vendor table
  var tbody = document.getElementById('vendor-body');
  tbody.innerHTML = '';
  sorted.forEach(function(row) {
    var tr = document.createElement('tr');
    tr.innerHTML =
      '<td class="desc">' + esc(row.vendor) + '</td>' +
      '<td style="text-align:center">' + row.count + '</td>' +
      '<td class="amount">' + fmt(row.total) + '</td>' +
      '<td class="amount">' + fmt(row.avg) + '</td>';
    tbody.appendChild(tr);
  });

  // Vendor bar chart (top 10)
  var top = sorted.slice(0, 10);
  if (vendorChart) vendorChart.destroy();
  vendorChart = new Chart(document.getElementById('chart-vendor'), {
    type: 'bar',
    data: {
      labels: top.map(function(r) { return r.vendor.length > 30 ? r.vendor.slice(0, 28) + '…' : r.vendor; }),
      datasets: [{
        label: 'Total Spend ($)',
        data: top.map(function(r) { return +r.total.toFixed(2); }),
        backgroundColor: CHART_COLORS.slice(0, top.length),
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { callback: function(v) { return '$' + Number(v).toLocaleString(); } } } }
    }
  });
}

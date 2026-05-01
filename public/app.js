const CATEGORIES = [
  'Advertising & Marketing', 'Bank Charges & Fees', 'Business Meals & Entertainment',
  'Computer & Internet', 'Dues & Subscriptions', 'Equipment & Supplies',
  'Insurance', 'Legal & Professional', 'Meals & Entertainment',
  'Office Supplies', 'Other Expense', 'Payroll', 'Postage & Shipping',
  'Rent', 'Repairs & Maintenance', 'Software', 'Travel',
  'Utilities', 'Vehicle', 'Unclassified'
];

let transactions = [];

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const loading  = document.getElementById('loading');
const errorEl  = document.getElementById('error');
const results  = document.getElementById('results');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => { if (e.target.files[0]) handleFile(e.target.files[0]); });

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showError('Please upload a PDF file.');
    return;
  }

  hideError();
  dropZone.classList.add('hidden');
  loading.classList.remove('hidden');
  results.classList.add('hidden');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }
    const data = await res.json();
    transactions = data.transactions || [];
    render();
    results.classList.remove('hidden');
  } catch (err) {
    showError(err.message);
    dropZone.classList.remove('hidden');
  } finally {
    loading.classList.add('hidden');
  }
}

function render() {
  renderStats();
  renderTable();
}

function renderStats() {
  const total = transactions.length;
  let purchases = 0, credits = 0, chargesCount = 0;

  transactions.forEach(t => {
    const amt = parseFloat(t.Amount) || 0;
    if (amt < 0) credits += Math.abs(amt);
    else { purchases += amt; chargesCount++; }
  });

  const grid = document.getElementById('stats-grid');
  grid.innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Total Transactions</div>
      <div class="stat-value">${total}</div>
    </div>
    <div class="stat-card amber">
      <div class="stat-label">Total Charges</div>
      <div class="stat-value">$${purchases.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</div>
    </div>
    <div class="stat-card green">
      <div class="stat-label">Total Credits / Payments</div>
      <div class="stat-value">$${credits.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</div>
    </div>
    <div class="stat-card red">
      <div class="stat-label">Net Spend</div>
      <div class="stat-value">$${(purchases - credits).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</div>
    </div>
  `;
}

function renderTable() {
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';

  transactions.forEach((txn, i) => {
    const amt = parseFloat(txn.Amount) || 0;
    const isNeg = amt < 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${txn['Sale Date'] || ''}</td>
      <td>${txn['Post Date'] || ''}</td>
      <td class="desc" title="${escHtml(txn.Description || '')}">${escHtml(txn.Description || '')}</td>
      <td class="amount${isNeg ? ' negative' : ''}">$${Math.abs(amt).toFixed(2)}</td>
      <td>
        <select class="category-select" onchange="updateCategory(${i}, this.value)">
          ${buildOptions(txn.Category)}
        </select>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function buildOptions(selected) {
  const cats = CATEGORIES.includes(selected) ? CATEGORIES : [selected, ...CATEGORIES].filter(Boolean);
  return [...new Set(cats)]
    .map(c => `<option value="${escHtml(c)}"${c === selected ? ' selected' : ''}>${escHtml(c)}</option>`)
    .join('');
}

function updateCategory(index, value) {
  transactions[index].Category = value;
}

function downloadCSV() {
  const headers = ['Sale Date', 'Post Date', 'Description', 'Amount', 'Category'];
  const rows = transactions.map(t =>
    headers.map(h => `"${String(t[h] || '').replace(/"/g, '""')}"`).join(',')
  );
  const csv = [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: 'classified_expenses.csv' });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function showError(msg) { errorEl.textContent = msg; errorEl.classList.remove('hidden'); }
function hideError() { errorEl.classList.add('hidden'); }
function escHtml(str) { return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

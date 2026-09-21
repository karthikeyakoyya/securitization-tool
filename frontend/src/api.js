const BASE = '/api';

export async function listSampleFiles() {
  const r = await fetch(`${BASE}/documents/sample-files`);
  return r.json();
}

export async function extractSample(filename) {
  const r = await fetch(`${BASE}/documents/extract-sample/${filename}`, { method: 'POST' });
  return r.json();
}

export async function listDocuments() {
  const r = await fetch(`${BASE}/documents`);
  return r.json();
}

export async function getSampleCashflowRequest() {
  const r = await fetch(`${BASE}/cashflow/sample-request`);
  return r.json();
}

export async function runWaterfall(payload) {
  const r = await fetch(`${BASE}/cashflow/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function exportExcel(payload) {
  const r = await fetch(`${BASE}/cashflow/export-excel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const blob = await r.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'securitization_cashflow_export.xlsx';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

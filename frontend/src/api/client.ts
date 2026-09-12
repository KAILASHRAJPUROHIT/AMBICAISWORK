// Adapted from payment-auditor/frontend/src/api/client.ts — same functions,
// same shapes. The only real change: auth moved from an implicit LAN-IP
// check to an explicit X-Notifier-Token header, since this now runs on the
// public internet. The token is entered once and kept in localStorage (see
// App.tsx's gate) rather than baked into the bundle.
const BASE_URL = window.location.origin;

export function getNotifierToken() {
  return localStorage.getItem('apn_notifier_token') || '';
}

export function setNotifierToken(token: string) {
  localStorage.setItem('apn_notifier_token', token);
}

export function clearNotifierToken() {
  localStorage.removeItem('apn_notifier_token');
}

function getHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-Notifier-Token': getNotifierToken(),
  };
}

async function handleJsonResponse(response: Response, errorMessage: string) {
  const contentType = response.headers.get('content-type') || '';
  if (!response.ok) {
    if (response.status === 401) {
      clearNotifierToken();
      window.location.reload();
    }
    if (contentType.includes('application/json')) {
      const error = await response.json();
      throw new Error(error.detail || `${errorMessage} (Server returned ${response.status})`);
    }
    const text = await response.text();
    console.error(`Expected JSON but received ${contentType || 'unknown content type'}:`, text.slice(0, 300));
    throw new Error(`${errorMessage} (Server returned ${response.status})`);
  }
  if (!contentType.includes('application/json')) {
    return response.text();
  }
  return response.json();
}

export async function getBankActivity() {
  const response = await fetch(`${BASE_URL}/api/bank-activity`, { headers: getHeaders() });
  return handleJsonResponse(response, 'Failed to fetch bank activity');
}

export async function recordBankActivityReferenceCopy(reference: string, source: 'dashboard' | 'popup' = 'dashboard') {
  const response = await fetch(`${BASE_URL}/api/bank-activity/reference-copied`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ reference, source }),
  });
  return handleJsonResponse(response, 'Failed to record Ref / UTR copy');
}

export async function getKYCDocuments() {
  const response = await fetch(`${BASE_URL}/api/kyc-documents/open`, { headers: getHeaders() });
  return handleJsonResponse(response, 'Failed to fetch KYC documents');
}

export async function getDocumentDashboard() {
  const response = await fetch(`${BASE_URL}/api/documents`, { headers: getHeaders() });
  return handleJsonResponse(response, 'Failed to fetch documents');
}

export async function reprintDocument(bundleId: string) {
  const response = await fetch(`${BASE_URL}/api/documents/${encodeURIComponent(bundleId)}/reprint`, { method: 'POST', headers: getHeaders() });
  return handleJsonResponse(response, 'Could not queue document reprint');
}

export async function resendDocumentToBiller(bundleId: string) {
  const response = await fetch(`${BASE_URL}/api/documents/${encodeURIComponent(bundleId)}/resend-to-biller`, { method: 'POST', headers: getHeaders() });
  return handleJsonResponse(response, 'Could not resend documents to biller');
}

export function documentDownloadUrl(bundleId: string, filename: string) {
  return `${BASE_URL}/api/documents/${encodeURIComponent(bundleId)}/files/${encodeURIComponent(filename)}?token=${encodeURIComponent(getNotifierToken())}`;
}

export async function recordKYCFieldCopy(docId: string, field: string, source: 'dashboard' = 'dashboard') {
  const response = await fetch(`${BASE_URL}/api/kyc-documents/field-copied`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ doc_id: docId, field, source }),
  });
  return handleJsonResponse(response, 'Failed to record field copy');
}

export async function saveBankActivityCorrection(id: number, correction: Record<string, string>) {
  const response = await fetch(`${BASE_URL}/api/bank-activity/${id}/correction`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(correction),
  });
  return handleJsonResponse(response, 'Failed to save bank activity correction');
}

export async function sendBankActivityTestPopup() {
  const response = await fetch(`${BASE_URL}/api/bank-activity/test-popup`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleJsonResponse(response, 'Failed to send test popup');
}

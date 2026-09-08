const BASE_URL = window.location.origin;
const RECONCILIATION_TIMEOUT_MS = 15000;

export function getSessionToken() {
  return localStorage.getItem('aradhana_session_token') || localStorage.getItem('session_token') || '';
}

export function getHeaders() {
  const token = getSessionToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'X-Session-Token': token } : {})
  };
}

async function handleResponse(response: Response, errorMessage: string) {
  const contentType = response.headers.get('content-type');
  if (!response.ok) {
    if (contentType && contentType.includes('application/json')) {
      const error = await response.json();
      throw new Error(error.detail || errorMessage);
    } else {
      const text = await response.text();
      console.error(`Backend error (${response.status}):`, text);
      throw new Error(`${errorMessage} (Server returned ${response.status})`);
    }
  }
  
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

async function handleJsonResponse(response: Response, errorMessage: string) {
  const contentType = response.headers.get('content-type') || '';
  if (!response.ok) {
    if (contentType.includes('application/json')) {
      const error = await response.json();
      throw new Error(error.detail || `${errorMessage} (Server returned ${response.status})`);
    }
    const text = await response.text();
    console.error(`Expected JSON but received ${contentType || 'unknown content type'}:`, text.slice(0, 300));
    throw new Error(`${errorMessage} (Server returned ${response.status} ${contentType || 'non-JSON response'})`);
  }
  if (!contentType.includes('application/json')) {
    const text = await response.text();
    console.error(`Expected JSON response, got ${contentType || 'unknown content type'}:`, text.slice(0, 300));
    throw new Error(`${errorMessage} (Expected JSON but received ${contentType || 'non-JSON response'})`);
  }
  return response.json();
}

export async function getHealth() {
  const response = await fetch(`${BASE_URL}/health`);
  return handleResponse(response, 'Failed to fetch health status');
}

export async function login(employee_id: string, password: string) {
  const response = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_id, password })
  });
  return handleResponse(response, 'Login failed');
}

export async function verifyOTP(employee_id: string, otp_code: string) {
  const response = await fetch(`${BASE_URL}/api/auth/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_id, otp_code })
  });
  return handleResponse(response, 'Verification failed');
}

export async function getMe() {
  const response = await fetch(`${BASE_URL}/api/auth/me`, {
    headers: getHeaders()
  });
  return handleResponse(response, 'Not authenticated');
}

export async function logout() {
    const response = await fetch(`${BASE_URL}/api/auth/logout`, {
        method: 'POST',
        headers: getHeaders()
    });
    localStorage.removeItem('aradhana_session_token');
    localStorage.removeItem('session_token');
    localStorage.removeItem('user');
    return handleResponse(response, 'Logout failed');
}

export async function getPermissions(role: string) {
  const response = await fetch(`${BASE_URL}/api/permissions/${role}`, {
    headers: getHeaders()
  });
  return handleResponse(response, `Failed to fetch permissions for role: ${role}`);
}

export async function getOpenReviews(signal?: AbortSignal) {
  const response = await fetch(`${BASE_URL}/api/reconciliation/open`, {
    headers: getHeaders(),
    signal
  });
  const data = await handleJsonResponse(response, 'Failed to fetch open reconciliation items');
  if (!Array.isArray(data)) {
    throw new Error('Failed to fetch open reconciliation items (Invalid response shape: expected an array)');
  }
  return data;
}

export async function getOpenReviewsWithTimeout(timeoutMs = RECONCILIATION_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await getOpenReviews(controller.signal);
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      throw new Error('Reconciliation request timed out. Please retry.');
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function openInvoicePdf(billId: number) {
  const token = getSessionToken();
  const response = await fetch(`${BASE_URL}/api/invoices/pdf/${billId}`, {
    headers: { ...(token ? { 'X-Session-Token': token } : {}) }
  });
  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }
    throw new Error('Failed to load invoice PDF');
  }
  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  window.open(blobUrl, '_blank');
}

export async function fetchProofPreview(proofUrl: string) {
  const token = getSessionToken();
  const response = await fetch(`${BASE_URL}${proofUrl}`, {
    headers: { ...(token ? { 'X-Session-Token': token } : {}) }
  });
  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }
    throw new Error('Failed to load payment proof');
  }
  return response.text();
}

export async function getOpenEscalations() {
  const response = await fetch(`${BASE_URL}/api/escalations/open`, {
    headers: getHeaders()
  });
  return handleResponse(response, 'Failed to fetch open escalations');
}

export async function getBankActivity() {
  const response = await fetch(`${BASE_URL}/api/bank-activity`, {
    headers: getHeaders()
  });
  return handleJsonResponse(response, 'Failed to fetch bank activity');
}

export async function recordBankActivityReferenceCopy(reference: string, source: 'dashboard' | 'popup' = 'dashboard') {
  const response = await fetch(`${BASE_URL}/api/bank-activity/reference-copied`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reference, source }),
  });
  return handleJsonResponse(response, 'Failed to record Ref / UTR copy');
}

export async function getKYCDocuments() {
  const response = await fetch(`${BASE_URL}/api/kyc-documents/open`, {
    headers: getHeaders()
  });
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
  return `${BASE_URL}/api/documents/${encodeURIComponent(bundleId)}/files/${encodeURIComponent(filename)}`;
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(correction),
  });
  return handleJsonResponse(response, 'Failed to save bank activity correction');
}

export async function sendBankActivityTestPopup() {
  const response = await fetch(`${BASE_URL}/api/bank-activity/test-popup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return handleJsonResponse(response, 'Failed to send test popup');
}

export async function getOwnerReport() {
  let response = await fetch(`${BASE_URL}/api/reports/owner`, {
    headers: getHeaders()
  });
  if (response.status === 404) {
    response = await fetch(`${BASE_URL}/reports/owner`, {
      headers: getHeaders()
    });
  }
  return handleResponse(response, 'Failed to fetch owner report');
}

export async function approveAccountantVerification(billId: number, note: string = '') {
  const response = await fetch(`${BASE_URL}/api/accountant-verification/approve`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ bill_id: billId, note })
  });
  return handleJsonResponse(response, 'Failed to approve item');
}

export async function rejectAccountantVerification(billId: number, note: string) {
  const response = await fetch(`${BASE_URL}/api/accountant-verification/reject`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ bill_id: billId, note })
  });
  return handleJsonResponse(response, 'Failed to reject item');
}

export async function furtherReviewAccountantVerification(billId: number, note: string) {
  const response = await fetch(`${BASE_URL}/api/accountant-verification/further-review`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ bill_id: billId, note })
  });
  return handleJsonResponse(response, 'Failed to flag for further review');
}

const BASE_URL = window.location.origin;

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

export async function getOpenReviews() {
  const response = await fetch(`${BASE_URL}/api/reconciliation/open`, {
    headers: getHeaders()
  });
  const data = await handleResponse(response, 'Failed to fetch open reviews');
  if (!Array.isArray(data)) {
    throw new Error('Reconciliation endpoint returned an invalid response shape.');
  }
  return data;
}

export async function getOpenEscalations() {
  const response = await fetch(`${BASE_URL}/api/escalations/open`, {
    headers: getHeaders()
  });
  return handleResponse(response, 'Failed to fetch open escalations');
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

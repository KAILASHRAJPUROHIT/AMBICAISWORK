const BASE_URL = window.location.origin;

export function getHeaders() {
  const token = localStorage.getItem('session_token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'X-Session-Token': token } : {})
  };
}

export async function getHealth() {
  const response = await fetch(`${BASE_URL}/health`);
  if (!response.ok) {
    throw new Error('Failed to fetch health status');
  }
  return response.json();
}

export async function login(employee_id: string, password: string) {
  const response = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_id, password })
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Login failed');
  }
  return response.json();
}

export async function verifyOTP(employee_id: string, otp_code: string) {
  const response = await fetch(`${BASE_URL}/api/auth/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_id, otp_code })
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Verification failed');
  }
  return response.json();
}

export async function getMe() {
  const response = await fetch(`${BASE_URL}/api/auth/me`, {
    headers: getHeaders()
  });
  if (!response.ok) {
    throw new Error('Not authenticated');
  }
  return response.json();
}

export async function logout() {
    const response = await fetch(`${BASE_URL}/api/auth/logout`, {
        method: 'POST',
        headers: getHeaders()
    });
    localStorage.removeItem('session_token');
    localStorage.removeItem('user');
    return response.json();
}

export async function getPermissions(role: string) {
  const response = await fetch(`${BASE_URL}/api/permissions/${role}`, {
    headers: getHeaders()
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch permissions for role: ${role}`);
  }
  return response.json();
}

export async function getOpenReviews() {
  const response = await fetch(`${BASE_URL}/api/reviews/open`, {
    headers: getHeaders()
  });
  if (!response.ok) {
    throw new Error('Failed to fetch open reviews');
  }
  return response.json();
}

export async function getOpenEscalations() {
  const response = await fetch(`${BASE_URL}/api/escalations/open`, {
    headers: getHeaders()
  });
  if (!response.ok) {
    throw new Error('Failed to fetch open escalations');
  }
  return response.json();
}

export async function getOwnerReport() {
  const response = await fetch(`${BASE_URL}/api/reports/owner`, {
    headers: getHeaders()
  });
  if (!response.ok) {
    throw new Error('Failed to fetch owner report');
  }
  return response.json();
}

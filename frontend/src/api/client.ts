const BASE_URL = 'http://127.0.0.1:8000';

export async function getHealth() {
  const response = await fetch(`${BASE_URL}/health`);
  if (!response.ok) {
    throw new Error('Failed to fetch health status');
  }
  return response.json();
}

export async function getPermissions(role: string) {
  const response = await fetch(`${BASE_URL}/permissions/${role}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch permissions for role: ${role}`);
  }
  return response.json();
}

export async function getOpenReviews() {
  const response = await fetch(`${BASE_URL}/reviews/open`);
  if (!response.ok) {
    throw new Error('Failed to fetch open reviews');
  }
  return response.json();
}

export async function getOpenEscalations() {
  const response = await fetch(`${BASE_URL}/escalations/open`);
  if (!response.ok) {
    throw new Error('Failed to fetch open escalations');
  }
  return response.json();
}

export async function getOwnerReport() {
  const response = await fetch(`${BASE_URL}/reports/owner`);
  if (!response.ok) {
    throw new Error('Failed to fetch owner report');
  }
  return response.json();
}

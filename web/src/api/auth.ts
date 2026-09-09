import { apiClient } from './client';

// Endpoints (see server: com.hmdm.rest.resource.AuthResource):
//   POST /rest/public/auth/login   body: { login, password }
//   POST /rest/public/auth/logout
//   GET  /rest/public/auth/options
//
// The browser encrypts the raw password with RSA-OAEP/SHA-256. The server
// verifies PBKDF2 hashes and transparently migrates legacy hashes after a
// successful plaintext login. A missing public key fails closed.

/** Subset of the user object returned on successful login (UserView). */
export interface AuthUser {
  id: number;
  login: string;
  name?: string;
  email?: string;
  // The server may also signal a forced password reset or 2FA step.
  passwordReset?: boolean;
  passwordResetToken?: string;
  twoFactor?: boolean;
  superAdmin?: boolean;
  singleCustomer?: boolean;
  userRole?: {
    superAdmin?: boolean;
    permissions?: { name: string }[];
  };
}

export interface AuthOptions {
  signup: boolean;
  recover: boolean;
  /** Base64 RSA public key, present only when transmit.password mode is on. */
  publicKey?: string;
}

function base64ToArrayBuffer(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function bytesToBase64(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

async function encryptPassword(password: string, publicKey: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('Secure browser cryptography is unavailable. Use a supported modern browser.');
  }
  const key = await crypto.subtle.importKey(
    'spki',
    base64ToArrayBuffer(publicKey),
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  );
  const encrypted = await crypto.subtle.encrypt(
    { name: 'RSA-OAEP' },
    key,
    new TextEncoder().encode(password).buffer as ArrayBuffer,
  );
  return bytesToBase64(encrypted);
}

async function securedPasswordPayload(password: string): Promise<string> {
  const options = await fetchAuthOptions();
  if (!options.publicKey) {
    throw new Error('Secure login is not enabled on this AMBIC MDM server.');
  }
  return encryptPassword(password, options.publicKey);
}

export async function fetchAuthOptions(): Promise<AuthOptions> {
  return apiClient.get<AuthOptions>('/public/auth/options');
}

export async function login(
  username: string,
  password: string,
): Promise<AuthUser> {
  const payload = {
    login: username,
    password: await securedPasswordPayload(password),
  };
  return apiClient.post<AuthUser>('/public/auth/login', payload);
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post<void>('/public/auth/logout');
  } catch {
    // Best effort: invalidating the session client-side is enough for the UI.
  }
}

/**
 * Complete a forced password reset using the same encrypted plaintext channel
 * as login, then store the new PBKDF2 hash server-side.
 */
export async function submitForcedPasswordReset(
  passwordResetToken: string,
  newPassword: string,
): Promise<void> {
  await apiClient.post('/public/passwordReset/reset', {
    passwordResetToken,
    newPassword: await securedPasswordPayload(newPassword),
  });
}

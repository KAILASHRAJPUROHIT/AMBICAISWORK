import { apiClient, API_BASE } from './client';

// Fleet-wide settings backed by the Java server's `settings` table
// (com.hmdm.rest.resource.SettingsResource, /rest/private/settings/*).

export interface FleetSettings {
  adminPasscodeSet: boolean;
}

export async function getFleetSettings(): Promise<FleetSettings> {
  const data = await apiClient.get<{ adminPasscodeSet?: boolean }>('/private/settings');
  return { adminPasscodeSet: !!data.adminPasscodeSet };
}

/** Set the fleet-wide admin passcode. Pass an empty string to clear it. Only the hash is ever
 *  persisted server-side or sent to devices — see SettingsResource#updateAdminPasscode. */
export async function setAdminPasscode(passcode: string): Promise<void> {
  await apiClient.post<void>('/private/settings/adminPasscode', { passcode });
}

// ---------------------------------------------------------------- client branding

export type BrandingSlot = 'logo' | 'mark';

export interface ClientBranding {
  clientName: string | null;
  clientLogoUrl: string | null;
  clientMarkUrl: string | null;
}

/** Turns a server-hosted path into the absolute URL managed devices will fetch. */
function absUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  const origin = API_BASE.replace(/\/rest\/?$/i, '');
  return origin + (path.startsWith('/') ? path : `/${path}`);
}

/** Current client branding, as stored in settings. */
export async function getClientBranding(): Promise<ClientBranding> {
  const d = await apiClient.get<Partial<ClientBranding>>('/private/settings');
  return {
    clientName: d.clientName ?? null,
    clientLogoUrl: absUrl(d.clientLogoUrl),
    clientMarkUrl: absUrl(d.clientMarkUrl),
  };
}

/**
 * Uploads a PNG into the server's branding store and returns the absolute URL devices
 * fetch it from. PNG only, 4 MB ceiling (also enforced server-side).
 */
export async function uploadClientBrandingImage(file: File, kind: BrandingSlot): Promise<string> {
  if (!/\.png$/i.test(file.name)) {
    throw new Error('Only PNG images are accepted');
  }
  if (file.size > 4 * 1024 * 1024) {
    throw new Error('Image must be 4 MB or smaller');
  }
  const form = new FormData();
  form.append('kind', kind);
  form.append('file', file, file.name);
  const r = await apiClient.postForm<{ path?: string }>(
    '/private/client-branding/image',
    form,
  );
  const url = absUrl(r?.path);
  if (!url) throw new Error('Server did not return an image path');
  return url;
}

/** Saves the branding shown on managed devices. Blank values clear a field. */
export async function saveClientBranding(b: {
  name: string;
  logoUrl: string;
  markUrl: string;
}): Promise<void> {
  await apiClient.post<void>('/private/settings/clientBranding', {
    name: b.name,
    logoUrl: b.logoUrl,
    markUrl: b.markUrl,
  });
}

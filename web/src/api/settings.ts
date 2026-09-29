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

// --- Kiosk sections (which parts of the tablet UI are shown) ---------------------------------------

export type KioskSectionKey = 'leaderboard' | 'quickControls' | 'clientLogo' | 'clockCard' | 'statusPills';
export type KioskSectionMap = Record<KioskSectionKey, boolean>;

/** The switchable parts of the tablet, in display order. The admin menu button is never switchable. */
export const KIOSK_SECTIONS: { key: KioskSectionKey; label: string; hint: string }[] = [
  { key: 'leaderboard', label: 'Sales leaderboard', hint: "Today's ranking of salespeople, under the clock." },
  { key: 'quickControls', label: 'Quick Controls', hint: 'The bottom bar (Rotate, Wi-Fi, Brightness) and the full Quick Controls sheet.' },
  { key: 'clientLogo', label: 'Client logo', hint: "Your client's logo beside the clock, on the idle screen and on the agent screen." },
  { key: 'clockCard', label: 'Clock & device card', hint: 'The big time, the date, the device name and the Managed light.' },
  { key: 'statusPills', label: 'Battery & Wi-Fi status', hint: 'The battery and Wi-Fi indicators at the top of the screen.' },
];

/** Current switches. A section is on unless the server has stored an explicit false. */
export async function getKioskSections(): Promise<KioskSectionMap> {
  const d = await apiClient.get<{ kioskSections?: string | null }>('/private/settings');
  const map = Object.fromEntries(KIOSK_SECTIONS.map((s) => [s.key, true])) as KioskSectionMap;
  if (d?.kioskSections) {
    try {
      const stored = JSON.parse(d.kioskSections) as Record<string, unknown>;
      for (const s of KIOSK_SECTIONS) if (stored[s.key] === false) map[s.key] = false;
    } catch {
      /* unreadable value: leave everything on */
    }
  }
  return map;
}

/** Saves the switches for every managed device. */
export async function saveKioskSections(map: KioskSectionMap): Promise<void> {
  await apiClient.post<void>('/private/settings/kioskSections', map);
}

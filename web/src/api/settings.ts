import { apiClient } from './client';

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

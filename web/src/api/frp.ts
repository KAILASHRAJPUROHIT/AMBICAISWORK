import { apiClient } from './client';

export interface FrpRecoveryAccount {
  id: number;
  googleUserId: string;
  email: string;
  connectedAt: number;
}

const BASE = '/private/agent/v1/frp';

export const listFrpRecoveryAccounts = () => apiClient.get<FrpRecoveryAccount[]>(`${BASE}/accounts`);

/** Google owns authentication. AMBIC MDM never receives a Google password, MFA code, or token. */
export const beginFrpRecoveryAccountConnection = () =>
  apiClient.post<{ authorizationUrl: string }>(`${BASE}/accounts/connect`, {});

export const removeFrpRecoveryAccount = (id: number) => apiClient.del(`${BASE}/accounts/${id}`);

/** Device numbers with an FRP-enable command queued but not yet done. */
export const listPendingFrpDevices = () => apiClient.get<string[]>(`${BASE}/pending-devices`);

/** Queues an ID-bearing EFRP command; Android rejects the old unsafe generic enable action. */
export const applyFrpToDevice = (deviceId: string) =>
  apiClient.post(`${BASE}/devices/${encodeURIComponent(deviceId)}/apply`, {});

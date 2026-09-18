// Staged Library-app rollout (canary → fleet), tracked per device — sibling to rollout.ts (which
// tracks the agent's own self-update). Talks to /private/agent/v1/rollout/apps on the Java server.
// Unlike the agent rollout, progress is derived from the live status of the specific app.install
// command sent to each device (not a version comparison — the server has no installed-version
// record for an arbitrary package), so each active rollout also carries a per-device breakdown.
import { apiClient } from './client';

export interface AppRolloutDeviceStatus {
  deviceNumber: string;
  status: 'UPDATED' | 'PENDING' | 'OUTSTANDING' | 'INELIGIBLE';
}

export interface AppRolloutCounts {
  total: number;
  updated: number;
  pending: number;
  outstanding: number;
  ineligible: number;
}

export interface AppRolloutProgress {
  stage: string;
  targetVersion: string;
  canary: AppRolloutCounts;
  fleet: AppRolloutCounts | null;
  canaryDevices: AppRolloutDeviceStatus[];
  fleetDevices: AppRolloutDeviceStatus[] | null;
}

export interface AppRollout {
  id: number;
  targetVersion: string;
  packageName: string;
  displayName: string | null;
  apkVersionCode: number | null;
  stage: 'canary' | 'fleet' | 'done' | 'cancelled';
  createdAt: number;
  updatedAt: number;
  progress: AppRolloutProgress;
}

const BASE = '/private/agent/v1/rollout';

/** Start a canary-stage push of one Library app version to the selected devices. Every APK detail
 *  (url/pkg/sha256/versionCode) is resolved server-side from applicationVersionId. Throws ApiError
 *  (e.g. a rollout for this app's package is already active). */
export async function createAppRollout(
  applicationVersionId: number,
  canaryDeviceNumbers: string[],
): Promise<AppRollout> {
  return apiClient.post<AppRollout>(`${BASE}/apps`, { applicationVersionId, canaryDeviceNumbers });
}

/** Every in-progress Library-app rollout for this customer. */
export async function listActiveAppRollouts(): Promise<AppRollout[]> {
  return apiClient.get<AppRollout[]>(`${BASE}/apps/active`);
}

/** Advance a canary rollout to the rest of the fleet. Shared with the agent rollout endpoint. */
export async function promoteAppRollout(id: number): Promise<AppRollout> {
  return apiClient.post<AppRollout>(`${BASE}/${id}/promote`);
}

/** Stop offering the update (in-flight installs run their course). */
export async function cancelAppRollout(id: number): Promise<void> {
  await apiClient.post<void>(`${BASE}/${id}/cancel`);
}

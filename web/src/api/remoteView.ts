import { apiClient, API_BASE } from './client';

export type RemoteKind = 'screen' | 'cameraFront' | 'cameraBack' | 'mic';

export interface RemoteSessionRequest {
  durationSec: number;
  intervalSec: number;
  kinds: RemoteKind[];
}

export interface RemoteSession {
  sessionId: string;
  durationSec: number;
  intervalSec: number;
  kinds: RemoteKind[];
}

export interface RemoteSnapshotMeta {
  kind: RemoteKind;
  capturedAt: number;
  contentType: string;
}

const base = (deviceId: string) => `/private/agent/v1/devices/${encodeURIComponent(deviceId)}/remote`;

export function startRemoteSession(deviceId: string, request: RemoteSessionRequest): Promise<RemoteSession> {
  return apiClient.post<RemoteSession>(`${base(deviceId)}/start`, request);
}

export function stopRemoteSession(deviceId: string): Promise<void> {
  return apiClient.post<void>(`${base(deviceId)}/stop`);
}

export function getLatestSnapshots(deviceId: string): Promise<RemoteSnapshotMeta[]> {
  return apiClient.get<RemoteSnapshotMeta[]>(`${base(deviceId)}/latest`);
}

export function snapshotUrl(deviceId: string, kind: RemoteKind, capturedAt: number): string {
  return `${API_BASE}${base(deviceId)}/snapshot/${kind}?_=${capturedAt}`;
}

export interface RemoteInputRequest {
  action: 'tap' | 'swipe' | 'key';
  x?: number;
  y?: number;
  endX?: number;
  endY?: number;
  durationMs?: number;
  key?: 'back' | 'home' | 'recents' | 'notifications' | 'lock';
}

export function sendRemoteInput(deviceId: string, request: RemoteInputRequest): Promise<void> {
  return apiClient.post<void>(`${base(deviceId)}/input`, request);
}

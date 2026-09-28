import { apiClient } from './client';

export interface DeviceEvent {
  id: number;
  type: string;
  ts: number;
  detail?: string | null;
}

/** Newest first. The server defaults to 200 and caps at 500 per call. */
export async function getEvents(deviceId: number | string, since = 0, limit?: number): Promise<DeviceEvent[]> {
  const lim = limit ? `&limit=${limit}` : '';
  return apiClient.get<DeviceEvent[]>(`/private/agent/v1/devices/${deviceId}/events?since=${since}${lim}`);
}

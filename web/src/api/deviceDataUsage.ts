import { apiClient } from './client';

// Device data-usage history — GET /private/agent/v1/devices/{n}/dataUsage?since=
// Each snapshot is the device's cumulative cellular/Wi-Fi bytes for the local day it was
// captured in (see device_data_usage table) — a running total, not a delta between rows.

export interface DataUsageSnapshot {
  id?: number;
  deviceNumber?: string;
  mobileRxBytes: number;
  mobileTxBytes: number;
  wifiRxBytes: number;
  wifiTxBytes: number;
  windowStart: number;
  capturedAt: number;
  recordedAt?: number;
}

export async function listDataUsage(
  deviceId: number | string,
  since = 0,
): Promise<DataUsageSnapshot[]> {
  return apiClient.get<DataUsageSnapshot[]>(
    `/private/agent/v1/devices/${deviceId}/dataUsage?since=${since}`,
  );
}

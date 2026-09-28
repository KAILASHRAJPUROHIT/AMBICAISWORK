import { apiClient } from './client';

/** One device x day x app total from the agents' appUsage events. */
export interface AppUsageRow {
  deviceNumber: string;
  /** Local day (Asia/Kolkata), "yyyy-MM-dd". */
  day: string;
  pkg: string;
  label: string;
  seconds: number;
  sessions: number;
}

export async function getAppUsage(from: number, to: number, device?: string): Promise<AppUsageRow[]> {
  const dev = device ? `&device=${encodeURIComponent(device)}` : '';
  return apiClient.get<AppUsageRow[]>(`/private/agent/v1/reports/app-usage?from=${from}&to=${to}${dev}`);
}

/** "3h 10m", "12m", "40s". */
export function fmtDuration(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

/** Start of the local day `daysAgo` days back (browser time zone = shop time zone). */
export function dayStart(daysAgo = 0): number {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - daysAgo);
  return d.getTime();
}

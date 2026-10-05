import { apiClient } from './client';

export interface WindowsDisk {
  label: string;
  filesystem: string;
  usagePercent: number;
  size: string;
  remaining: string;
  bitlockerStatus: string;
}

export interface WindowsPc {
  id: string;
  hostname: string;
  nickname: string;
  description: string;
  ip: string;
  mac: string;
  status: string; // WaitingForAdmission | Enabled | Disabled
  online: boolean;
  firstContact: number;
  lastContact: number;
  restartRequired: boolean;
  manufacturer: string;
  model: string;
  serial: string;
  memoryMB: number;
  cpu: string;
  cpuCores: number;
  osVersion: string;
  osEdition: string;
  osDescription: string;
  osArch: string;
  domain: string;
  loggedInUser: string;
  lastBoot: number;
  updateStatus: string;
  pendingUpdates: boolean | null;
  lastUpdateSearch: number;
  antivirus: { name: string; active: boolean; updated: boolean } | null;
  appCount: number;
  disks?: WindowsDisk[];
}

export type WindowsAction = 'report' | 'admit' | 'restart-agent';

const BASE = '/private/windows/v1';

export const getWindowsStatus = () => apiClient.get<{ configured: boolean }>(`${BASE}/status`);

export const listWindowsPcs = () => apiClient.get<{ devices: WindowsPc[]; commands: string[] }>(`${BASE}/devices`);

export const getWindowsPc = (id: string) =>
  apiClient.get<{ device: WindowsPc; commands: string[] }>(`${BASE}/devices/${encodeURIComponent(id)}`);

export const sendWindowsCommand = (id: string, action: WindowsAction) =>
  apiClient.post(`${BASE}/devices/${encodeURIComponent(id)}/commands/${action}`, {});

export const windowsName = (d: WindowsPc) => d.nickname || d.hostname;

/** Plain-language state for the badge. */
export function windowsState(d: WindowsPc): { label: string; tone: 'ok' | 'warn' | 'off' } {
  if (d.status === 'WaitingForAdmission') return { label: 'Waiting for approval', tone: 'warn' };
  if (d.status === 'Disabled') return { label: 'Disabled', tone: 'off' };
  return d.online ? { label: 'Online', tone: 'ok' } : { label: 'Offline', tone: 'off' };
}

export const fmtMemory = (mb: number) => (mb >= 1024 ? `${Math.round(mb / 1024)} GB` : `${mb} MB`);

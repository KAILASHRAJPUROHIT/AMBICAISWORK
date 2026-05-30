// frontend/src/mockPrimeRobotData.ts

export interface PrimeRobotStatus {
  robotStatus: 'Running' | 'Idle' | 'Failed' | 'Paused';
  processedCount: number;
  remainingCount: number;
  currentInvoice: string | null;
  lastActivity: string; // ISO string or similar
  lastError: string | null;
  primePCStatus: 'Online' | 'Offline' | 'Connecting';
}

export const mockPrimeRobotStatus: PrimeRobotStatus = {
  robotStatus: 'Running',
  processedCount: 125,
  remainingCount: 37,
  currentInvoice: 'INV-2023-0123',
  lastActivity: new Date().toISOString(),
  lastError: null,
  primePCStatus: 'Online',
};

export const mockPrimeRobotStatusFailed: PrimeRobotStatus = {
  robotStatus: 'Failed',
  processedCount: 120,
  remainingCount: 42,
  currentInvoice: 'INV-2023-0120',
  lastActivity: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
  lastError: 'Failed to connect to Prime ERP: Authentication error.',
  primePCStatus: 'Online',
};

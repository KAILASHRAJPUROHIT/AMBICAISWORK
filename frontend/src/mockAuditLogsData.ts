// frontend/src/mockAuditLogsData.ts

export interface AuditLogItem {
  id: string;
  timestamp: string; // ISO string
  actor: string;
  action: string;
  result: 'Success' | 'Failure' | 'Info';
  details: string; // Additional details in string format
}

export const mockAuditLogs: AuditLogItem[] = [
  {
    id: 'log-001',
    timestamp: new Date(Date.now() - 10 * 60 * 1000).toISOString(), // 10 minutes ago
    actor: 'AdminUser',
    action: 'Login',
    result: 'Success',
    details: 'User "AdminUser" logged in from IP 192.168.1.100.',
  },
  {
    id: 'log-002',
    timestamp: new Date(Date.now() - 25 * 60 * 1000).toISOString(), // 25 minutes ago
    actor: 'ReconciliationBot',
    action: 'Run Reconciliation',
    result: 'Success',
    details: 'Daily reconciliation job completed. 150 records processed.',
  },
  {
    id: 'log-003',
    timestamp: new Date(Date.now() - 40 * 60 * 1000).toISOString(), // 40 minutes ago
    actor: 'FinanceTeam',
    action: 'Update Reconciliation Item',
    result: 'Failure',
    details: 'Failed to update item "rec-002": Mismatch too high.',
  },
];

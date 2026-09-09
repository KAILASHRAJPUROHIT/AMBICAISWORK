import { apiClient } from './client';

// Customer-scoped admin-alert rules — notify a webhook and/or email when a matching
// device event fires. See server: com.hmdm.rest.resource.AgentAdminResource #alertRules.

export interface AlertRule {
  id?: number;
  customerId?: number;
  /** Event type to match (e.g. "lowBattery"); empty/undefined matches any event. */
  eventType?: string;
  webhookUrl?: string;
  email?: string;
  enabled?: boolean;
  createdAt?: number;
}

export async function listAlertRules(): Promise<AlertRule[]> {
  return apiClient.get<AlertRule[]>('/private/agent/v1/alertRules');
}

export async function createAlertRule(rule: AlertRule): Promise<AlertRule> {
  return apiClient.post<AlertRule>('/private/agent/v1/alertRules', rule);
}

export async function updateAlertRule(id: number, rule: AlertRule): Promise<void> {
  await apiClient.put(`/private/agent/v1/alertRules/${id}`, rule);
}

export async function deleteAlertRule(id: number): Promise<void> {
  await apiClient.del(`/private/agent/v1/alertRules/${id}`);
}

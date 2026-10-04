import { apiClient } from './client';

export type SmtpSecurity = 'ssl' | 'starttls' | 'none';

/** What the server reports. The password is never sent back: only whether one is stored. */
export interface SmtpView {
  configured: boolean;
  /** "console" = entered here, "server" = from the server's environment, "none" = no outgoing email. */
  source: 'console' | 'server' | 'none';
  recipient: string;
  /** True while sign-ins from new computers really are checked. */
  deviceCheckActive: boolean;
  host?: string;
  port?: number;
  security?: SmtpSecurity;
  username?: string;
  fromAddress?: string;
  hasPassword?: boolean;
  updatedAt?: number;
  updatedBy?: string;
}

export interface SmtpSave {
  host: string;
  port: number;
  security: SmtpSecurity;
  username: string;
  /** Leave empty to keep the stored password. */
  password: string;
  fromAddress: string;
}

export const getSmtp = () => apiClient.get<SmtpView>('/private/smtp-settings');
export const saveSmtp = (body: SmtpSave) => apiClient.put<SmtpView>('/private/smtp-settings', body);
export const clearSmtp = () => apiClient.del<SmtpView>('/private/smtp-settings');
export const testSmtp = () => apiClient.post<{ ok: boolean; message: string; sentTo: string }>('/private/smtp-settings/test');

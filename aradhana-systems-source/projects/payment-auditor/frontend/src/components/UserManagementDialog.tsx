import React, { useEffect, useState } from 'react';
import { getHeaders } from '../api/client';

export const PERMISSION_GROUPS = [
  { key: 'dashboard_access', label: 'Dashboard Access' },
  { key: 'reconciliation_access', label: 'Reconciliation Access' },
  { key: 'reports_access', label: 'Reports Access' },
  { key: 'extraction_review_access', label: 'Extraction Review Access' },
  { key: 'audit_logs_access', label: 'Audit Logs Access' },
  { key: 'master_console_access', label: 'Master Console Access' },
  { key: 'user_management_access', label: 'User Management Access' },
  { key: 'emergency_controls_access', label: 'Emergency Controls Access' },
  { key: 'financial_metrics_access', label: 'Financial Metrics Access' },
];

export const ROLE_PRESETS: Record<string, string[]> = {
  OWNER: PERMISSION_GROUPS.map(group => group.key),
  ACCOUNTANT: ['dashboard_access', 'reconciliation_access', 'reports_access', 'extraction_review_access', 'audit_logs_access'],
  STAFF: ['dashboard_access', 'extraction_review_access'],
  DEVELOPER: ['dashboard_access', 'audit_logs_access'],
  VIEWER: ['dashboard_access', 'reports_access', 'audit_logs_access'],
};

const ROLES = ['OWNER', 'ACCOUNTANT', 'STAFF', 'DEVELOPER', 'VIEWER'];

export interface ManagedUser {
  id: number;
  employee_id: string;
  name: string;
  email: string | null;
  security_email: string | null;
  role: string;
  is_active: boolean;
  password_reset_required: boolean;
  created_at: string | null;
  is_archived: boolean;
  is_migrated: boolean;
  is_test_user: boolean;
  permissions: string[];
}

interface UserManagementDialogProps {
  isOpen: boolean;
  mode: 'create' | 'edit';
  user?: ManagedUser | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface UserFormState {
  employee_id: string;
  name: string;
  email: string;
  security_email: string;
  role: string;
  is_active: boolean;
  password_reset_required: boolean;
  send_otp_to_security_email: boolean;
  temporary_password: string;
  permissions: string[];
}

const makeInitialState = (mode: 'create' | 'edit', user?: ManagedUser | null): UserFormState => {
  if (mode === 'edit' && user) {
    return {
      employee_id: user.employee_id,
      name: user.name || '',
      email: user.email || '',
      security_email: user.security_email || '',
      role: user.role || 'STAFF',
      is_active: user.is_active,
      password_reset_required: user.password_reset_required,
      send_otp_to_security_email: false,
      temporary_password: '',
      permissions: user.permissions?.length ? user.permissions : ROLE_PRESETS[user.role] || ROLE_PRESETS.STAFF,
    };
  }
  return {
    employee_id: '',
    name: '',
    email: '',
    security_email: '',
    role: 'ACCOUNTANT',
    is_active: true,
    password_reset_required: true,
    send_otp_to_security_email: false,
    temporary_password: '',
    permissions: ROLE_PRESETS.ACCOUNTANT,
  };
};

const UserManagementDialog: React.FC<UserManagementDialogProps> = ({ isOpen, mode, user, onClose, onSuccess }) => {
  const [formData, setFormData] = useState<UserFormState>(() => makeInitialState(mode, user));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = mode === 'edit';

  useEffect(() => {
    if (isOpen) {
      setFormData(makeInitialState(mode, user));
      setError(null);
    }
  }, [isOpen, mode, user]);

  if (!isOpen) return null;

  const applyRolePreset = (role: string) => {
    setFormData(prev => ({
      ...prev,
      role,
      permissions: ROLE_PRESETS[role] || [],
    }));
  };

  const togglePermission = (permission: string) => {
    setFormData(prev => ({
      ...prev,
      permissions: prev.permissions.includes(permission)
        ? prev.permissions.filter(item => item !== permission)
        : [...prev.permissions, permission],
    }));
  };

  const submitUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const endpoint = isEdit && user
        ? `${window.location.origin}/api/admin/users/${encodeURIComponent(user.employee_id)}`
        : `${window.location.origin}/api/admin/users`;
      const payload = {
        employee_id: formData.employee_id,
        name: formData.name,
        email: formData.email || null,
        security_email: formData.security_email || null,
        role: formData.role,
        is_active: formData.is_active,
        password_reset_required: formData.password_reset_required,
        permissions: formData.permissions,
        ...(isEdit ? {} : {
          password: formData.temporary_password || null,
          send_otp_to_security_email: formData.send_otp_to_security_email,
        }),
      };
      const response = await fetch(endpoint, {
        method: isEdit ? 'PATCH' : 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to save user');
      }
      onSuccess();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save user');
    } finally {
      setLoading(false);
    }
  };

  const resetPassword = async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${window.location.origin}/api/admin/users/${encodeURIComponent(user.employee_id)}/reset-password`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          temporary_password: formData.temporary_password || null,
          send_reset_otp: formData.send_otp_to_security_email,
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to trigger password reset');
      }
      onSuccess();
      setFormData(prev => ({ ...prev, temporary_password: '', password_reset_required: true }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger password reset');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6 z-[100]">
      <div className="bg-white max-w-5xl w-full max-h-[92vh] overflow-y-auto rounded-3xl p-8 shadow-2xl border border-gray-100">
        <div className="flex items-start justify-between gap-6 mb-6">
          <div>
            <h3 className="text-2xl font-black uppercase tracking-tight">{isEdit ? 'Edit User' : 'Create New User'}</h3>
            <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mt-2">Owner-controlled identity and access</p>
          </div>
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-xl bg-gray-100 text-gray-500 font-black text-xs uppercase">Close</button>
        </div>

        {error && <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-xl text-xs font-bold uppercase">{error}</div>}

        <form onSubmit={submitUser} className="space-y-8">
          <section>
            <h4 className="text-xs font-black uppercase tracking-widest text-gray-400 mb-4">Basic Details</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <label className="space-y-2">
                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Employee ID</span>
                <input
                  type="text"
                  className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                  value={formData.employee_id}
                  onChange={e => setFormData({ ...formData, employee_id: e.target.value.toUpperCase() })}
                  required
                />
              </label>
              <label className="space-y-2">
                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Full Name</span>
                <input
                  type="text"
                  className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </label>
              <label className="space-y-2">
                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Role</span>
                <select
                  className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-black uppercase text-xs"
                  value={formData.role}
                  onChange={e => applyRolePreset(e.target.value)}
                >
                  {ROLES.map(role => <option key={role} value={role}>{role}</option>)}
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Email</span>
                <input
                  type="email"
                  className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                  value={formData.email}
                  onChange={e => setFormData({ ...formData, email: e.target.value })}
                />
              </label>
              <label className="space-y-2">
                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Security Email</span>
                <input
                  type="email"
                  className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                  value={formData.security_email}
                  onChange={e => setFormData({ ...formData, security_email: e.target.value })}
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="p-4 bg-gray-50 border border-gray-100 rounded-2xl flex items-center gap-3">
                  <input type="checkbox" checked={formData.is_active} onChange={e => setFormData({ ...formData, is_active: e.target.checked })} />
                  <span className="text-[10px] font-black uppercase text-gray-500">Active</span>
                </label>
                <label className="p-4 bg-gray-50 border border-gray-100 rounded-2xl flex items-center gap-3">
                  <input type="checkbox" checked={formData.password_reset_required} onChange={e => setFormData({ ...formData, password_reset_required: e.target.checked })} />
                  <span className="text-[10px] font-black uppercase text-gray-500">Reset Required</span>
                </label>
              </div>
            </div>
          </section>

          <section>
            <h4 className="text-xs font-black uppercase tracking-widest text-gray-400 mb-4">Access Permissions</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {PERMISSION_GROUPS.map(group => (
                <label key={group.key} className="p-4 bg-gray-50 border border-gray-100 rounded-2xl flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={formData.permissions.includes(group.key)}
                    onChange={() => togglePermission(group.key)}
                  />
                  <span className="text-[10px] font-black uppercase text-gray-600 tracking-wide">{group.label}</span>
                </label>
              ))}
            </div>
          </section>

          <section>
            <h4 className="text-xs font-black uppercase tracking-widest text-gray-400 mb-4">Security</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <label className="space-y-2 md:col-span-2">
                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">
                  {isEdit ? 'Temporary Password For Reset' : 'Temporary Password'}
                </span>
                <input
                  type="password"
                  className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                  value={formData.temporary_password}
                  onChange={e => setFormData({ ...formData, temporary_password: e.target.value })}
                  required={!isEdit}
                  placeholder={isEdit ? 'Leave blank to only require reset' : ''}
                />
              </label>
              <label className="p-4 bg-gray-50 border border-gray-100 rounded-2xl flex items-center gap-3 self-end">
                <input
                  type="checkbox"
                  checked={formData.send_otp_to_security_email}
                  onChange={e => setFormData({ ...formData, send_otp_to_security_email: e.target.checked })}
                />
                <span className="text-[10px] font-black uppercase text-gray-500">Send Reset OTP</span>
              </label>
            </div>
            <p className="mt-3 text-[10px] font-bold uppercase tracking-widest text-gray-400">Existing passwords and password hashes are never displayed.</p>
          </section>

          <div className="pt-2 flex flex-wrap gap-4 justify-end">
            {isEdit && (
              <button
                type="button"
                onClick={resetPassword}
                disabled={loading}
                className="px-6 py-4 rounded-2xl bg-blue-50 text-blue-700 font-black uppercase text-xs tracking-widest"
              >
                Trigger Password Reset
              </button>
            )}
            <button type="button" onClick={onClose} className="px-6 py-4 rounded-2xl font-black uppercase text-xs tracking-widest text-gray-400 hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={loading} className="px-8 py-4 rounded-2xl bg-black text-white font-black uppercase text-xs tracking-widest shadow-xl shadow-black/10">
              {loading ? 'Saving...' : isEdit ? 'Save User' : 'Create User'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default UserManagementDialog;

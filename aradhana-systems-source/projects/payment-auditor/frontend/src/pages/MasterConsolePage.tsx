import React, { useState, useEffect } from 'react';
import { getHeaders } from '../api/client';
import UserManagementDialog from '../components/UserManagementDialog';
import type { ManagedUser } from '../components/UserManagementDialog';
import ConfirmationDialog from '../components/ConfirmationDialog';
import './MasterConsolePage.css';

interface SecurityStats {
  failed_login_count: number;
  active_session_count: number;
  otp_total_count: number;
  recent_events: any[];
}

interface FinancialHealth {
  pending_review_count: number;
  cheques_pending_count: number;
  bank_variance_amount: number;
  reconciliation_accuracy: number;
}

type SectionKey = 'users' | 'security' | 'financial' | 'emergency';

type SectionErrors = Partial<Record<SectionKey, string>>;

interface ApiResult<T> {
    data: T | null;
    error?: string;
}

const MasterConsolePage: React.FC = () => {
    const [users, setUsers] = useState<ManagedUser[]>([]);
    const [securityStats, setSecurityStats] = useState<SecurityStats | null>(null);
    const [financialHealth, setFinancialHealth] = useState<FinancialHealth | null>(null);
    const [systemMode, setSystemMode] = useState('PRODUCTION');
    const [loading, setLoading] = useState(true);
    const [sectionErrors, setSectionErrors] = useState<SectionErrors>({});
    const [activeTab, setActiveTab] = useState<'USERS' | 'SECURITY' | 'FINANCIAL' | 'EMERGENCY'>('USERS');
    const [userDialogOpen, setUserDialogOpen] = useState(false);
    const [userDialogMode, setUserDialogMode] = useState<'create' | 'edit'>('create');
    const [selectedUser, setSelectedUser] = useState<ManagedUser | null>(null);
    const [userFilters, setUserFilters] = useState({
        includeInactive: false,
        includeArchived: false,
        includeTest: false,
        role: '',
        search: '',
    });
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [confirmAction, setConfirmAction] = useState({ title: '', msg: '', cmd: '' });

    const API_BASE = window.location.origin;
    const systemModeClass = systemMode === 'PRODUCTION'
        ? 'bg-green-50 text-green-700 border-green-200'
        : systemMode === 'UNKNOWN'
            ? 'bg-gray-50 text-gray-500 border-gray-200'
            : 'bg-red-50 text-red-700 border-red-200';
    const maintenanceButtonClass = systemMode === 'PRODUCTION'
        ? 'bg-red-600 text-white hover:bg-red-700 shadow-red-200'
        : systemMode === 'UNKNOWN'
            ? 'bg-gray-200 text-gray-500 shadow-gray-100 cursor-not-allowed'
            : 'bg-green-600 text-white hover:bg-green-700 shadow-green-200';
    const maintenanceButtonLabel = systemMode === 'PRODUCTION'
        ? 'Enter Maintenance Mode'
        : systemMode === 'UNKNOWN'
            ? 'System Mode Unavailable'
            : 'Exit Maintenance Mode';

    const fetchJson = async <T,>(url: string): Promise<ApiResult<T>> => {
        try {
            const response = await fetch(url, { headers: getHeaders() });
            const contentType = response.headers.get('content-type') || '';
            const body = contentType.includes('application/json') ? await response.json() : await response.text();

            if (!response.ok) {
                const detail = typeof body === 'object' && body !== null && 'detail' in body
                    ? JSON.stringify(body.detail)
                    : String(body || 'No response body');
                return { data: null, error: `Server returned ${response.status}: ${detail}` };
            }

            return { data: body as T };
        } catch (error) {
            return { data: null, error: error instanceof Error ? error.message : 'Request failed' };
        }
    };

    const buildUserQuery = () => {
        const params = new URLSearchParams({
            include_inactive: String(userFilters.includeInactive),
            include_archived: String(userFilters.includeArchived),
            include_test: String(userFilters.includeTest),
        });
        if (userFilters.role) params.set('role', userFilters.role);
        if (userFilters.search.trim()) params.set('search', userFilters.search.trim());
        return params.toString();
    };

    const fetchData = async () => {
        const [usersRes, statsRes, modeRes, healthRes] = await Promise.all([
            fetchJson<ManagedUser[]>(`${API_BASE}/api/admin/users?${buildUserQuery()}`),
            fetchJson<SecurityStats>(`${API_BASE}/api/admin/security/stats`),
            fetchJson<{ mode?: string }>(`${API_BASE}/api/admin/system/mode`),
            fetchJson<FinancialHealth>(`${API_BASE}/api/admin/financial/health`)
        ]);

        const nextErrors: SectionErrors = {};

        if (usersRes.error) {
            nextErrors.users = usersRes.error;
            setUsers([]);
        } else {
            setUsers(Array.isArray(usersRes.data) ? usersRes.data : []);
        }

        if (statsRes.error) {
            nextErrors.security = statsRes.error;
            setSecurityStats(null);
        } else {
            const stats = statsRes.data;
            setSecurityStats({
                failed_login_count: stats?.failed_login_count ?? 0,
                active_session_count: stats?.active_session_count ?? 0,
                otp_total_count: stats?.otp_total_count ?? 0,
                recent_events: Array.isArray(stats?.recent_events) ? stats.recent_events : []
            });
        }

        if (modeRes.error) {
            nextErrors.emergency = modeRes.error;
            setSystemMode('UNKNOWN');
        } else {
            setSystemMode(modeRes.data?.mode || 'PRODUCTION');
        }

        if (healthRes.error) {
            nextErrors.financial = healthRes.error;
            setFinancialHealth(null);
        } else {
            setFinancialHealth(healthRes.data);
        }

        setSectionErrors(nextErrors);
        setLoading(false);
    };

    useEffect(() => {
        fetchData();
    }, [userFilters]);

    const openCreateUser = () => {
        setUserDialogMode('create');
        setSelectedUser(null);
        setUserDialogOpen(true);
    };

    const openEditUser = (user: ManagedUser) => {
        setUserDialogMode('edit');
        setSelectedUser(user);
        setUserDialogOpen(true);
    };

    const toggleUser = async (empId: string) => {
        try {
            const response = await fetch(`${API_BASE}/api/admin/users/${empId}/toggle`, { 
                method: 'POST', 
                headers: getHeaders() 
            });
            if (!response.ok) throw new Error(`Server returned ${response.status}`);
            fetchData();
        } catch (error) {
            setSectionErrors(prev => ({ ...prev, users: error instanceof Error ? error.message : 'Unable to update user' }));
        }
    };

    const archiveUser = async (empId: string) => {
        try {
            const response = await fetch(`${API_BASE}/api/admin/users/${empId}/archive`, {
                method: 'POST',
                headers: getHeaders()
            });
            if (!response.ok) throw new Error(`Server returned ${response.status}`);
            fetchData();
        } catch (error) {
            setSectionErrors(prev => ({ ...prev, users: error instanceof Error ? error.message : 'Unable to archive user' }));
        }
    };

    const restoreUser = async (empId: string) => {
        try {
            const response = await fetch(`${API_BASE}/api/admin/users/${empId}/restore`, {
                method: 'POST',
                headers: getHeaders()
            });
            if (!response.ok) throw new Error(`Server returned ${response.status}`);
            fetchData();
        } catch (error) {
            setSectionErrors(prev => ({ ...prev, users: error instanceof Error ? error.message : 'Unable to restore user' }));
        }
    };

    const handleMaintenanceToggle = () => {
        const isProd = systemMode === 'PRODUCTION';
        setConfirmAction({
            title: isProd ? 'Enter Maintenance Mode?' : 'Exit Maintenance Mode?',
            msg: isProd 
                ? 'This will block operational access for all staff members. Only developers will be allowed access for troubleshooting.'
                : 'This will restore full operational access for all staff members.',
            cmd: isProd ? 'MAINTENANCE' : 'PRODUCTION'
        });
        setConfirmOpen(true);
    };

    const executeModeChange = async () => {
        try {
            const response = await fetch(`${API_BASE}/api/admin/system/mode?mode=${confirmAction.cmd}&reason=Manual+Toggle+via+Console`, { 
                method: 'POST', 
                headers: getHeaders() 
            });
            if (!response.ok) throw new Error(`Server returned ${response.status}`);
            setConfirmOpen(false);
            fetchData();
        } catch (error) {
            setSectionErrors(prev => ({ ...prev, emergency: error instanceof Error ? error.message : 'Unable to change system mode' }));
        }
    };

    const forceSync = async (cmd: string) => {
        try {
            const response = await fetch(`${API_BASE}/api/admin/emergency/sync?command=${cmd}`, { 
                method: 'POST', 
                headers: getHeaders() 
            });
            if (!response.ok) throw new Error(`Server returned ${response.status}`);
            alert(`Command ${cmd} sent successfully.`);
        } catch (error) {
            setSectionErrors(prev => ({ ...prev, emergency: error instanceof Error ? error.message : 'Unable to run emergency sync' }));
        }
    };

    const SectionError = ({ title, detail }: { title: string; detail?: string }) => (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-red-700">
            <p className="font-black uppercase tracking-widest text-xs">{title}</p>
            {detail && <p className="mt-2 text-xs font-bold break-words">{detail}</p>}
        </div>
    );

    if (loading) return <div className="p-20 text-center font-black animate-pulse uppercase tracking-widest text-gray-400">Loading Master Console Architecture...</div>;

    return (
        <div className="master-console p-10 bg-gray-50 min-h-screen">
            <header className="mb-12 flex justify-between items-start">
                <div>
                    <h1 className="text-4xl font-black text-gray-900 tracking-tight uppercase">Master Console</h1>
                    <p className="text-gray-500 font-bold tracking-widest mt-2 uppercase text-xs">Owner-Level Administrative Privileges Only</p>
                </div>
                <div className={`px-6 py-2 rounded-xl font-black text-[10px] uppercase tracking-widest border-2 ${systemModeClass}`}>
                    System Status: {systemMode}
                </div>
            </header>

            <nav className="flex space-x-4 mb-10 border-b border-gray-200 pb-4">
                {['USERS', 'SECURITY', 'FINANCIAL', 'EMERGENCY'].map(tab => (
                    <button 
                        key={tab}
                        onClick={() => setActiveTab(tab as any)}
                        className={`px-8 py-3 rounded-xl font-black text-xs tracking-widest uppercase transition-all ${activeTab === tab ? 'bg-black text-white shadow-xl shadow-black/20' : 'text-gray-400 hover:text-black'}`}
                    >
                        {tab}
                    </button>
                ))}
            </nav>

            {activeTab === 'USERS' && (
                <section className="space-y-8 animate-in fade-in">
                    <div className="flex justify-between items-center">
                        <div>
                            <h2 className="text-xl font-black uppercase">User Administration</h2>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mt-1">Default view hides migrated, test, archived, and inactive users</p>
                        </div>
                        <button 
                            onClick={openCreateUser}
                            className="bg-black text-white px-6 py-3 rounded-xl font-black text-xs uppercase tracking-widest"
                        >
                            Create New User
                        </button>
                    </div>

                    {sectionErrors.users && <SectionError title="Unable to load user administration" detail={sectionErrors.users} />}

                    <div className="bg-white rounded-3xl border border-gray-100 shadow-sm p-6 space-y-5">
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <label className="md:col-span-2 space-y-2">
                                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Search</span>
                                <input
                                    type="search"
                                    value={userFilters.search}
                                    onChange={e => setUserFilters(prev => ({ ...prev, search: e.target.value }))}
                                    placeholder="Employee ID, name, email"
                                    className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-bold"
                                />
                            </label>
                            <label className="space-y-2">
                                <span className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Role</span>
                                <select
                                    value={userFilters.role}
                                    onChange={e => setUserFilters(prev => ({ ...prev, role: e.target.value }))}
                                    className="w-full p-4 bg-gray-50 border border-gray-100 rounded-2xl font-black uppercase text-xs"
                                >
                                    <option value="">All Roles</option>
                                    {['OWNER', 'ACCOUNTANT', 'STAFF', 'DEVELOPER', 'VIEWER'].map(role => <option key={role} value={role}>{role}</option>)}
                                </select>
                            </label>
                            <button
                                type="button"
                                onClick={() => setUserFilters({ includeInactive: false, includeArchived: false, includeTest: false, role: '', search: '' })}
                                className="self-end p-4 rounded-2xl bg-gray-100 text-gray-500 font-black uppercase text-xs tracking-widest"
                            >
                                Reset Filters
                            </button>
                        </div>
                        <div className="flex flex-wrap gap-3">
                            {[
                                { key: 'includeInactive', label: 'Show inactive' },
                                { key: 'includeArchived', label: 'Show archived/migrated' },
                                { key: 'includeTest', label: 'Show test users' },
                            ].map(filter => (
                                <label key={filter.key} className="px-4 py-3 bg-gray-50 border border-gray-100 rounded-2xl flex items-center gap-3">
                                    <input
                                        type="checkbox"
                                        checked={Boolean(userFilters[filter.key as keyof typeof userFilters])}
                                        onChange={e => setUserFilters(prev => ({ ...prev, [filter.key]: e.target.checked }))}
                                    />
                                    <span className="text-[10px] font-black uppercase tracking-widest text-gray-500">{filter.label}</span>
                                </label>
                            ))}
                        </div>
                    </div>

                    <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden">
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="bg-gray-50 border-b border-gray-100">
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Employee ID</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Name</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Role</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Email</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Access</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-center">Status</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {!sectionErrors.users && users.length === 0 && (
                                    <tr>
                                        <td colSpan={7} className="p-10 text-center text-xs font-black uppercase tracking-widest text-gray-400">No users found</td>
                                    </tr>
                                )}
                                {users.map(u => (
                                    <tr key={u.id} className="border-b border-gray-50">
                                        <td className="p-6 font-black text-gray-900 font-mono">
                                            <div>{u.employee_id}</div>
                                            <div className="flex gap-2 mt-2">
                                                {u.is_migrated && <span className="bg-orange-50 text-orange-600 px-2 py-1 rounded-md text-[9px] uppercase font-black">Migrated</span>}
                                                {u.is_test_user && <span className="bg-purple-50 text-purple-600 px-2 py-1 rounded-md text-[9px] uppercase font-black">Test</span>}
                                                {u.is_archived && <span className="bg-gray-100 text-gray-500 px-2 py-1 rounded-md text-[9px] uppercase font-black">Archived</span>}
                                            </div>
                                        </td>
                                        <td className="p-6 font-bold text-gray-700">{u.name}</td>
                                        <td className="p-6 uppercase">
                                            <span className="bg-gray-100 px-3 py-1 rounded-lg font-black text-[10px] text-gray-500">{u.role}</span>
                                        </td>
                                        <td className="p-6 text-xs font-bold text-gray-500">
                                            <div>{u.email || 'No email'}</div>
                                            <div className="text-gray-400">{u.security_email || 'No security email'}</div>
                                        </td>
                                        <td className="p-6">
                                            <span className="bg-blue-50 text-blue-700 px-3 py-1 rounded-lg font-black text-[10px] uppercase">{u.permissions?.length || 0} groups</span>
                                        </td>
                                        <td className="p-6 text-center">
                                            <div className={`inline-block w-3 h-3 rounded-full ${u.is_active ? 'bg-green-500 shadow-green-200' : 'bg-red-500 shadow-red-200'} shadow-lg`}></div>
                                            {u.password_reset_required && <div className="mt-2 text-[9px] text-yellow-700 font-black uppercase">Reset Required</div>}
                                        </td>
                                        <td className="p-6 text-right space-x-3 whitespace-nowrap">
                                            <button
                                                onClick={() => openEditUser(u)}
                                                className="text-[10px] font-black text-blue-600 uppercase hover:underline"
                                            >
                                                Edit
                                            </button>
                                            <button 
                                                onClick={() => toggleUser(u.employee_id)}
                                                className={`text-[10px] font-black uppercase hover:underline ${u.is_active ? 'text-red-600' : 'text-green-600'}`}
                                            >
                                                {u.is_active ? 'Disable' : 'Enable'}
                                            </button>
                                            {u.is_archived ? (
                                                <button
                                                    onClick={() => restoreUser(u.employee_id)}
                                                    className="text-[10px] font-black text-green-600 uppercase hover:underline"
                                                >
                                                    Restore
                                                </button>
                                            ) : (
                                                <button
                                                    onClick={() => archiveUser(u.employee_id)}
                                                    className="text-[10px] font-black text-gray-500 uppercase hover:underline"
                                                >
                                                    Archive
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>
            )}

            {activeTab === 'SECURITY' && (
                <section className="animate-in fade-in space-y-12">
                    {sectionErrors.security && <SectionError title="Unable to load security stats" detail={sectionErrors.security} />}

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                        <div className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm">
                            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Failed Logins</p>
                            <p className="text-5xl font-black text-red-600">{securityStats?.failed_login_count || 0}</p>
                        </div>
                        <div className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm">
                            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Active Sessions</p>
                            <p className="text-5xl font-black text-green-600">{securityStats?.active_session_count || 0}</p>
                        </div>
                        <div className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm">
                            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">OTPs Generated</p>
                            <p className="text-5xl font-black text-blue-600">{securityStats?.otp_total_count || 0}</p>
                        </div>
                    </div>

                    <div>
                        <h3 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Recent Access Logs</h3>
                        <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="bg-gray-50 border-b border-gray-100">
                                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">User</th>
                                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Event</th>
                                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">IP Address</th>
                                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Timestamp</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(securityStats?.recent_events ?? []).length === 0 && (
                                        <tr>
                                            <td colSpan={4} className="p-8 text-center text-xs font-black uppercase tracking-widest text-gray-400">No access logs available</td>
                                        </tr>
                                    )}
                                    {(securityStats?.recent_events ?? []).map((log, i) => {
                                        const event = String(log.event ?? log.event_type ?? 'UNKNOWN');
                                        const ip = log.ip ?? log.ip_address ?? 'N/A';
                                        const time = log.time ?? log.created_at;
                                        return (
                                        <tr key={i} className="border-b border-gray-50">
                                            <td className="p-4 font-black text-gray-900">{log.employee_id}</td>
                                            <td className="p-4">
                                                <span className={`text-[10px] font-black px-2 py-1 rounded-md uppercase ${event.includes('FAILED') ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                                                    {event}
                                                </span>
                                            </td>
                                            <td className="p-4 font-mono text-xs text-gray-400">{ip}</td>
                                            <td className="p-4 text-right text-xs font-bold text-gray-500">{time ? new Date(time).toLocaleString() : 'N/A'}</td>
                                        </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>
            )}

            {activeTab === 'FINANCIAL' && (
                <section className="animate-in fade-in space-y-12">
                    {sectionErrors.financial && <SectionError title="Unable to load financial health" detail={sectionErrors.financial} />}

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
                        <div className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm">
                            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Review Required</p>
                            <p className="text-4xl font-black text-gray-900">{financialHealth?.pending_review_count || 0}</p>
                        </div>
                        <div className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm">
                            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Cheques Pending</p>
                            <p className="text-4xl font-black text-gray-900">{financialHealth?.cheques_pending_count || 0}</p>
                        </div>
                        <div className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm">
                            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Bank Variance</p>
                            <p className={`text-4xl font-black ${financialHealth?.bank_variance_amount !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                                ₹{(financialHealth?.bank_variance_amount || 0).toLocaleString()}
                            </p>
                        </div>
                        <div className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm">
                            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Audit Accuracy</p>
                            <p className="text-4xl font-black text-blue-600">{financialHealth?.reconciliation_accuracy || 100}%</p>
                        </div>
                    </div>
                </section>
            )}

            {activeTab === 'EMERGENCY' && (
                <section className="animate-in fade-in space-y-8">
                    {sectionErrors.emergency && <SectionError title="Unable to load emergency controls" detail={sectionErrors.emergency} />}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
                    <div className="bg-white p-10 rounded-3xl border border-gray-100 shadow-sm">
                        <h3 className="text-xl font-black uppercase mb-8">Pipeline Controls</h3>
                        <div className="space-y-4">
                            {[
                                { id: 'SCAN', label: 'Force Invoice PDF Scan', desc: 'Rescan network share for new invoices' },
                                { id: 'POLL_EMAIL', label: 'Force Bank Email Poll', desc: 'Sync immediate alerts from ICICI/HDFC' },
                                { id: 'POLL_SMS', label: 'Force SMS Gateway Poll', desc: 'Fetch latest Android SMS forwarder logs' },
                                { id: 'RECONCILE', label: 'Force Reconciliation Run', desc: 'Reprocess all unmatched entries' }
                            ].map(btn => (
                                <div key={btn.id} className="p-6 rounded-2xl bg-gray-50 border border-gray-100 flex justify-between items-center hover:bg-gray-100 transition-all cursor-pointer" onClick={() => forceSync(btn.id)}>
                                    <div>
                                        <p className="font-black text-gray-900 uppercase text-xs tracking-widest">{btn.label}</p>
                                        <p className="text-[10px] text-gray-400 font-bold mt-1">{btn.desc}</p>
                                    </div>
                                    <div className="w-10 h-10 bg-white rounded-xl border border-gray-200 flex items-center justify-center text-gray-900 font-black shadow-sm">
                                        →
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="bg-red-50 p-10 rounded-3xl border-2 border-red-200 shadow-sm">
                        <h3 className="text-xl font-black uppercase mb-4 text-red-700">Danger Zone</h3>
                        <p className="text-sm font-bold text-red-500 mb-8 uppercase tracking-tighter">Emergency administrative overrides</p>
                        
                        <div className="space-y-4">
                             <button 
                                onClick={handleMaintenanceToggle}
                                disabled={systemMode === 'UNKNOWN'}
                                className={`w-full p-6 rounded-2xl font-black uppercase text-xs tracking-widest transition-all shadow-xl ${maintenanceButtonClass}`}
                             >
                                {maintenanceButtonLabel}
                             </button>
                             <button className="w-full p-6 rounded-2xl bg-white text-red-600 font-black uppercase text-xs tracking-widest border-2 border-red-200 hover:bg-red-50 transition-all">
                                Wipe System Checkpoints
                             </button>
                             <button className="w-full p-6 rounded-2xl bg-white text-gray-400 font-black uppercase text-xs tracking-widest border-2 border-gray-100 opacity-50 cursor-not-allowed">
                                Rollback Version (Disable)
                             </button>
                        </div>
                    </div>
                    </div>
                </section>
            )}

            <UserManagementDialog 
                isOpen={userDialogOpen}
                mode={userDialogMode}
                user={selectedUser}
                onClose={() => setUserDialogOpen(false)}
                onSuccess={fetchData}
            />

            <ConfirmationDialog 
                isOpen={confirmOpen}
                title={confirmAction.title}
                message={confirmAction.msg}
                confirmLabel="Confirm Change"
                onConfirm={executeModeChange}
                onCancel={() => setConfirmOpen(false)}
                type="CRITICAL"
            />
        </div>
    );
};

export default MasterConsolePage;

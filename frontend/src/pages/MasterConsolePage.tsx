import React, { useState, useEffect } from 'react';
import { getHeaders } from '../api/client';
import UserManagementDialog from '../components/UserManagementDialog';
import ConfirmationDialog from '../components/ConfirmationDialog';
import './MasterConsolePage.css';

interface User {
  id: number;
  employee_id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
}

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

const MasterConsolePage: React.FC = () => {
    const [users, setUsers] = useState<User[]>([]);
    const [securityStats, setSecurityStats] = useState<SecurityStats | null>(null);
    const [financialHealth, setFinancialHealth] = useState<FinancialHealth | null>(null);
    const [systemMode, setSystemMode] = useState('PRODUCTION');
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'USERS' | 'SECURITY' | 'FINANCIAL' | 'EMERGENCY'>('USERS');
    const [userDialogOpen, setUserDialogOpen] = useState(false);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [confirmAction, setConfirmAction] = useState({ title: '', msg: '', cmd: '' });

    const API_BASE = window.location.origin;

    const fetchData = async () => {
        try {
            const [usersRes, statsRes, modeRes, healthRes] = await Promise.all([
                fetch(`${API_BASE}/api/admin/users`, { headers: getHeaders() }).then(res => res.json()),
                fetch(`${API_BASE}/api/admin/security/stats`, { headers: getHeaders() }).then(res => res.json()),
                fetch(`${API_BASE}/api/admin/system/mode`, { headers: getHeaders() }).then(res => res.json()),
                fetch(`${API_BASE}/api/admin/financial/health`, { headers: getHeaders() }).then(res => res.json())
            ]);
            setUsers(usersRes);
            setSecurityStats(statsRes);
            setSystemMode(modeRes.mode);
            setFinancialHealth(healthRes);
        } catch (e) {
            console.error("Failed to load admin data", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const toggleUser = async (empId: string) => {
        await fetch(`${API_BASE}/api/admin/users/${empId}/toggle`, { 
            method: 'POST', 
            headers: getHeaders() 
        });
        fetchData();
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
        await fetch(`${API_BASE}/api/admin/system/mode?mode=${confirmAction.cmd}&reason=Manual+Toggle+via+Console`, { 
            method: 'POST', 
            headers: getHeaders() 
        });
        setConfirmOpen(false);
        fetchData();
    };

    const forceSync = async (cmd: string) => {
        await fetch(`${API_BASE}/api/admin/emergency/sync?command=${cmd}`, { 
            method: 'POST', 
            headers: getHeaders() 
        });
        alert(`Command ${cmd} sent successfully.`);
    };

    if (loading) return <div className="p-20 text-center font-black animate-pulse uppercase tracking-widest text-gray-400">Loading Master Console Architecture...</div>;

    return (
        <div className="master-console p-10 bg-gray-50 min-h-screen">
            <header className="mb-12 flex justify-between items-start">
                <div>
                    <h1 className="text-4xl font-black text-gray-900 tracking-tight uppercase">Master Console</h1>
                    <p className="text-gray-500 font-bold tracking-widest mt-2 uppercase text-xs">Owner-Level Administrative Privileges Only</p>
                </div>
                <div className={`px-6 py-2 rounded-xl font-black text-[10px] uppercase tracking-widest border-2 ${systemMode === 'PRODUCTION' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
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
                        <h2 className="text-xl font-black uppercase">User Administration</h2>
                        <button 
                            onClick={() => setUserDialogOpen(true)}
                            className="bg-black text-white px-6 py-3 rounded-xl font-black text-xs uppercase tracking-widest"
                        >
                            Create New User
                        </button>
                    </div>

                    <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden">
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="bg-gray-50 border-b border-gray-100">
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Employee ID</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Name</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Role</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-center">Status</th>
                                    <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.map(u => (
                                    <tr key={u.id} className="border-b border-gray-50">
                                        <td className="p-6 font-black text-gray-900 font-mono">{u.employee_id}</td>
                                        <td className="p-6 font-bold text-gray-700">{u.name}</td>
                                        <td className="p-6 uppercase">
                                            <span className="bg-gray-100 px-3 py-1 rounded-lg font-black text-[10px] text-gray-500">{u.role}</span>
                                        </td>
                                        <td className="p-6 text-center">
                                            <div className={`inline-block w-3 h-3 rounded-full ${u.is_active ? 'bg-green-500 shadow-green-200' : 'bg-red-500 shadow-red-200'} shadow-lg`}></div>
                                        </td>
                                        <td className="p-6 text-right space-x-2">
                                            <button className="text-[10px] font-black text-blue-600 uppercase hover:underline">Reset OTP</button>
                                            <button 
                                                onClick={() => toggleUser(u.employee_id)}
                                                className={`text-[10px] font-black uppercase hover:underline ${u.is_active ? 'text-red-600' : 'text-green-600'}`}
                                            >
                                                {u.is_active ? 'Disable' : 'Enable'}
                                            </button>
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
                                    {securityStats?.recent_events.map((log, i) => (
                                        <tr key={i} className="border-b border-gray-50">
                                            <td className="p-4 font-black text-gray-900">{log.employee_id}</td>
                                            <td className="p-4">
                                                <span className={`text-[10px] font-black px-2 py-1 rounded-md uppercase ${log.event.includes('FAILED') ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                                                    {log.event}
                                                </span>
                                            </td>
                                            <td className="p-4 font-mono text-xs text-gray-400">{log.ip}</td>
                                            <td className="p-4 text-right text-xs font-bold text-gray-500">{new Date(log.time).toLocaleString()}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>
            )}

            {activeTab === 'FINANCIAL' && (
                <section className="animate-in fade-in space-y-12">
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
                <section className="animate-in fade-in grid grid-cols-1 md:grid-cols-2 gap-12">
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
                                className={`w-full p-6 rounded-2xl font-black uppercase text-xs tracking-widest transition-all shadow-xl ${systemMode === 'PRODUCTION' ? 'bg-red-600 text-white hover:bg-red-700 shadow-red-200' : 'bg-green-600 text-white hover:bg-green-700 shadow-green-200'}`}
                             >
                                {systemMode === 'PRODUCTION' ? 'Enter Maintenance Mode' : 'Exit Maintenance Mode'}
                             </button>
                             <button className="w-full p-6 rounded-2xl bg-white text-red-600 font-black uppercase text-xs tracking-widest border-2 border-red-200 hover:bg-red-50 transition-all">
                                Wipe System Checkpoints
                             </button>
                             <button className="w-full p-6 rounded-2xl bg-white text-gray-400 font-black uppercase text-xs tracking-widest border-2 border-gray-100 opacity-50 cursor-not-allowed">
                                Rollback Version (Disable)
                             </button>
                        </div>
                    </div>
                </section>
            )}

            <UserManagementDialog 
                isOpen={userDialogOpen}
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

import React, { useState, useEffect } from 'react';
import AuditLogsTable from '../components/AuditLogsTable';
import '../Reconciliation.css'; 

const AuditLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // In a real run, this would fetch from /api/audit-logs
    // For now, we show an empty state as mock data is prohibited.
    setLoading(false);
    setLogs([]);
  }, []);

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
       <header className="mb-10">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">System Audit Logs</h1>
        <p className="mt-2 text-lg text-gray-600 font-medium">Immutable record of all system events and reviews.</p>
      </header>
      
      {loading ? (
        <div className="p-20 text-center text-gray-400 font-bold text-xl uppercase">Loading logs...</div>
      ) : logs.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl">
          Zero audit events recorded in current session.
        </div>
      ) : (
        <AuditLogsTable logs={logs} loading={loading} />
      )}
    </div>
  );
};

export default AuditLogsPage;

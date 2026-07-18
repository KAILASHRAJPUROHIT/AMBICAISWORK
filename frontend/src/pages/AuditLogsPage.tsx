import { useEffect, useState } from 'react';
import AuditLogsTable from '../components/AuditLogsTable';
import { getAuditLogs } from '../api/client';
import type { AuditLogItem } from '../types';
import '../Reconciliation.css';

const AuditLogsPage = () => {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAuditLogs()
      .then(setLogs)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10"><h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">System Audit Logs</h1><p className="mt-2 text-lg text-gray-600 font-medium">Recorded tenant events and financial state changes.</p></header>
      <AuditLogsTable logs={logs} loading={loading} error={error} />
    </div>
  );
};

export default AuditLogsPage;

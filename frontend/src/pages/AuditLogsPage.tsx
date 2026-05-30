import React, { useState, useEffect } from 'react';
import AuditLogsTable from '../components/AuditLogsTable';
import { mockAuditLogs } from '../mockAuditLogsData';
import type { AuditLogItem } from '../mockAuditLogsData';
import '../Reconciliation.css'; // Import shared styles

const AuditLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Simulate fetching data
    const fetchData = async () => {
      setLoading(true);
      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Simulate success
      setLogs(mockAuditLogs);
      setError(null);
      setLoading(false);
    };

    fetchData();
  }, []);

  return (
    <div className="audit-logs-page">
      <h1>Audit Logs</h1>
      <p>Review system activities and changes.</p>
      <AuditLogsTable logs={logs} loading={loading} error={error} />
    </div>
  );
};

export default AuditLogsPage;

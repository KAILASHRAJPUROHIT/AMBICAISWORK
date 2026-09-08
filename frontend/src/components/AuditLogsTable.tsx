import React from 'react';
import type { AuditLogItem } from '../types';
import '../Reconciliation.css'; 

interface AuditLogsTableProps {
  logs: AuditLogItem[];
  loading?: boolean;
  error?: string | null;
}

const AuditLogsTable: React.FC<AuditLogsTableProps> = ({ logs, loading, error }) => {
  if (loading) {
    return (
      <div className="table-container audit-logs-table-container">
        <div className="loading-indicator">Loading audit logs...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="table-container audit-logs-table-container">
        <div className="error-message">{error}</div>
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="table-container audit-logs-table-container">
        <div className="empty-state">No audit logs to display.</div>
      </div>
    );
  }

  const getResultClassName = (result: AuditLogItem['result']) => {
    switch (result) {
      case 'Success': return 'status-verified';
      case 'Failure': return 'status-risk-mismatch';
      case 'Info': return 'status-cheque-pending'; 
      default: return '';
    }
  };

  return (
    <div className="table-container audit-logs-table-container">
      <table className="audit-logs-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Result</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              <td>{new Date(log.timestamp).toLocaleString()}</td>
              <td>{log.actor}</td>
              <td>{log.action}</td>
              <td>
                <span className={`status-badge ${getResultClassName(log.result)}`}>
                  {log.result}
                </span>
              </td>
              <td>{log.details}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AuditLogsTable;

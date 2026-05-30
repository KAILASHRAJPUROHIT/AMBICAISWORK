import React from 'react';
import type { PrimeRobotStatus } from '../mockPrimeRobotData';
import '../Reconciliation.css'; // Import shared styles

interface PrimeRobotStatusCardProps {
  status: PrimeRobotStatus | null;
  loading: boolean;
  error: string | null;
}

const PrimeRobotStatusCard: React.FC<PrimeRobotStatusCardProps> = ({ status, loading, error }) => {
  if (loading) {
    return (
      <div className="status-card loading-state">
        <div className="loading-indicator">Loading robot status...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="status-card error-state">
        <div className="error-message">{error}</div>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="status-card empty-state">
        <div className="empty-state-message">No robot status data available.</div>
      </div>
    );
  }

  const getStatusColorClass = (robotStatus: PrimeRobotStatus['robotStatus']) => {
    switch (robotStatus) {
      case 'Running': return 'status-verified'; // Green
      case 'Idle': return 'status-pending';    // Yellow
      case 'Failed': return 'status-risk-mismatch'; // Red
      case 'Paused': return 'status-cheque-pending'; // Blue (or other suitable color)
      default: return '';
    }
  };

  return (
    <div className="status-card prime-robot-card">
      <div className="card-header">
        <h3>Prime ERP Robot Status</h3>
        <span className={`status-badge ${getStatusColorClass(status.robotStatus)}`}>
          {status.robotStatus}
        </span>
      </div>
      <div className="card-body">
        <div className="detail-item">
          <span className="detail-label">Processed:</span>
          <span className="detail-value">{status.processedCount} invoices</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Remaining:</span>
          <span className="detail-value">{status.remainingCount} invoices</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Current Invoice:</span>
          <span className="detail-value">{status.currentInvoice || 'N/A'}</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Last Activity:</span>
          <span className="detail-value">{new Date(status.lastActivity).toLocaleString()}</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Last Error:</span>
          <span className="detail-value error-message">{status.lastError || 'None'}</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Prime PC Status:</span>
          <span className="detail-value">{status.primePCStatus}</span>
        </div>
      </div>
    </div>
  );
};

export default PrimeRobotStatusCard;
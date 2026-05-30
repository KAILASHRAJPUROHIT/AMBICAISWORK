import React from 'react';
import type { ReconciliationItem } from '../mockReconciliationData';
import '../Reconciliation.css'; // Will create this CSS file next

interface ReconciliationTableProps {
  items: ReconciliationItem[];
  onRowClick: (item: ReconciliationItem) => void;
}

const ReconciliationTable: React.FC<ReconciliationTableProps> = ({ items, onRowClick }) => {
  if (items.length === 0) {
    return <div className="empty-state">No reconciliation items to display.</div>;
  }

  const getStatusClassName = (status: ReconciliationItem['status']) => {
    switch (status) {
      case 'Verified':
        return 'status-verified'; // Green
      case 'Pending':
        return 'status-pending'; // Yellow
      case 'Delivered Before Payment':
        return 'status-delivered-before-payment'; // Orange
      case 'Risk / Mismatch':
        return 'status-risk-mismatch'; // Red
      case 'Cheque Pending':
        return 'status-cheque-pending'; // Blue
      case 'Archived':
        return 'status-archived'; // Grey
      default:
        return '';
    }
  };

  return (
    <div className="table-container reconciliation-table-container">
      <table className="reconciliation-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Customer</th>
            <th>Bill No</th>
            <th>Invoice Amount</th>
            <th>Bank Amount</th>
            <th>Difference</th>
            <th>Source</th>
            <th>Match Confidence</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} onClick={() => onRowClick(item)} className="reconciliation-table-row">
              <td>{item.date}</td>
              <td>{item.customer}</td>
              <td>{item.billNo}</td>
              <td>₹{item.invoiceAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
              <td>₹{item.bankAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
              <td>₹{item.difference.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
              <td>{item.source}</td>
              <td>{item.matchConfidence}</td>
              <td>
                <span className={`status-badge ${getStatusClassName(item.status)}`}>
                  {item.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ReconciliationTable;

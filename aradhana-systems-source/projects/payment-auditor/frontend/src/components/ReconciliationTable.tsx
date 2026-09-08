import React from 'react';
import type { ReconciliationItem } from '../types';
import type { ReconciliationSortDirection, ReconciliationSortKey } from '../pages/ReconciliationQueuePage';
import '../Reconciliation.css';

interface ReconciliationTableProps {
  items: ReconciliationItem[];
  onRowClick: (item: ReconciliationItem) => void;
  onViewInvoice: (item: ReconciliationItem) => void;
  sortKey: ReconciliationSortKey;
  sortDirection: ReconciliationSortDirection;
  onSort: (key: ReconciliationSortKey) => void;
}

const formatDateTime = (value?: string | null) => {
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  return date.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const formatInvoiceTimestamp = (item: ReconciliationItem) => {
  const value = item.invoiceTimestamp || item.invoiceGeneratedAt || item.invoiceDate;
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  if (!item.invoiceTimeRecorded) {
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  return formatDateTime(value);
};

const ReconciliationTable: React.FC<ReconciliationTableProps> = ({ items, onRowClick, onViewInvoice, sortKey, sortDirection, onSort }) => {
  if (items.length === 0) {
    return <div className="empty-state">No reconciliation items to display.</div>;
  }

  const getStatusColor = (status: ReconciliationItem['status']) => {
    switch (status) {
      case 'Verified': return 'bg-green-100 text-green-800 border-green-200';
      case 'Pending': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'Delivered Before Payment': return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'Risk / Mismatch': return 'bg-red-100 text-red-800 border-red-200';
      case 'Cheque Pending':
      case 'Realizing Cheque': return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'ACCOUNTANT APPROVAL REQUIRED': return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'Archived': return 'bg-gray-100 text-gray-800 border-gray-200';
      case 'Advance Pending': return 'bg-purple-50 text-purple-700 border-purple-100';
      case 'Ambiguous Match': return 'bg-orange-50 text-orange-700 border-orange-100';
      default: return 'bg-gray-50 text-gray-600 border-gray-100';
    }
  };

  const header = (label: string, key: ReconciliationSortKey, align = 'text-left') => (
    <th className={`p-4 text-xs font-bold text-gray-400 uppercase tracking-widest ${align}`}>
      <button type="button" onClick={() => onSort(key)} className={`inline-flex items-center gap-1 ${align === 'text-right' ? 'justify-end w-full' : ''}`}>
        <span>{label}</span>
        <span className="text-[10px] text-gray-300">{sortKey === key ? (sortDirection === 'asc' ? '▲' : '▼') : '↕'}</span>
      </button>
    </th>
  );

  const getProofStatus = (item: ReconciliationItem) => {
    const invoiceAvailable = Boolean(item.invoicePdfAvailable && item.invoiceProofUrl && item.billId);
    const paymentProofAvailable = item.paymentBreakdown.some(payment => Boolean(payment.proofUrl));
    if (invoiceAvailable && paymentProofAvailable) return { label: 'Invoice PDF available / Payment proof available', className: 'bg-green-50 text-green-700 border-green-100' };
    if (invoiceAvailable) return { label: 'Invoice PDF available / Missing payment proof', className: 'bg-yellow-50 text-yellow-700 border-yellow-100' };
    if (paymentProofAvailable) return { label: 'Payment proof available', className: 'bg-blue-50 text-blue-700 border-blue-100' };
    return { label: 'Missing payment proof', className: 'bg-red-50 text-red-700 border-red-100' };
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50/50">
            {header('Bill No', 'billNo')}
            {header('Customer', 'customer')}
            {header('Invoice Date', 'invoiceDate')}
            {header('Invoice Amount', 'invoiceAmount')}
            {header('Bank Amount', 'bankAmount', 'text-right')}
            {header('Difference', 'difference', 'text-right')}
            {header('Mode', 'paymentMode')}
            {header('Confidence', 'matchConfidence')}
            {header('Status', 'status', 'text-center')}
            <th className="p-4 text-xs font-bold text-gray-400 uppercase tracking-widest text-center">Proof</th>
            <th className="p-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Proof Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {items.map((item) => {
            const proofStatus = getProofStatus(item);
            return (
              <tr
                key={item.id}
                onClick={() => onRowClick(item)}
                className="hover:bg-blue-50/30 transition-colors duration-200 cursor-pointer group"
              >
              <td className="p-4 text-sm font-mono font-bold text-gray-900">{item.billNo}</td>
              <td className="p-4 text-sm text-gray-600 font-medium">{item.customer}</td>
              <td className="p-4 text-xs text-gray-600 font-semibold min-w-[150px]">{formatInvoiceTimestamp(item)}</td>
              <td className="p-4 text-sm font-bold text-gray-900">₹{item.invoiceAmount.toLocaleString('en-IN')}</td>
              <td className="p-4 text-sm font-bold text-gray-900 text-right">₹{item.bankAmount.toLocaleString('en-IN')}</td>
              <td className={`p-4 text-sm font-black text-right ${item.difference > 0 ? 'text-red-600' : item.difference < 0 ? 'text-orange-600' : 'text-green-600'}`}>
                ₹{item.difference.toLocaleString('en-IN')}
              </td>
              <td className="p-4 text-xs font-bold text-gray-400 uppercase">{item.paymentMode}</td>
              <td className="p-4 text-sm">
                <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter ${
                  item.matchConfidence === 'High' ? 'bg-green-50 text-green-700' :
                  item.matchConfidence === 'Medium' ? 'bg-yellow-50 text-yellow-700' : 'bg-red-50 text-red-700'
                }`}>
                  {item.matchConfidence}
                </span>
              </td>
              <td className="p-4 text-center">
                <span className={`px-3 py-2 rounded-xl text-xs font-black border ${getStatusColor(item.status)} shadow-sm inline-block min-w-[120px] max-w-[190px]`}>
                  {item.status}
                </span>
              </td>
                <td className="p-4 text-center">
                  {item.invoicePdfAvailable && item.invoiceProofUrl && item.billId ? (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onViewInvoice(item);
                      }}
                      className="rounded-lg border border-blue-100 px-3 py-2 text-xs font-black text-blue-700 hover:bg-blue-50"
                    >
                      View PDF
                    </button>
                  ) : (
                    <span className="text-[10px] font-black uppercase text-gray-300">Not Recorded</span>
                  )}
                </td>
                <td className="p-4">
                  <span className={`inline-block rounded-lg border px-2 py-1 text-[10px] font-black uppercase ${proofStatus.className}`}>
                    {proofStatus.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default ReconciliationTable;

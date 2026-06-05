import React from 'react';
import type { ReconciliationItem } from '../types';
import type { ReconciliationSortDirection, ReconciliationSortKey } from '../pages/ReconciliationQueuePage';
import '../Reconciliation.css';

interface ReconciliationTableProps {
  items: ReconciliationItem[];
  onRowClick: (item: ReconciliationItem) => void;
  sortKey: ReconciliationSortKey;
  sortDirection: ReconciliationSortDirection;
  onSort: (key: ReconciliationSortKey) => void;
}

const formatMoney = (value: number) => `₹${value.toLocaleString('en-IN')}`;

const formatDateTime = (value?: string | null) => {
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};

const ReconciliationTable: React.FC<ReconciliationTableProps> = ({ items, onRowClick, sortKey, sortDirection, onSort }) => {
  if (items.length === 0) {
    return <div className="empty-state">No open reconciliation items</div>;
  }

  const getStatusColor = (status: ReconciliationItem['status']) => {
    switch (status) {
      case 'CLEAR': return 'bg-green-100 text-green-800 border-green-200';
      case 'PARTIAL PAYMENT':
      case 'REALIZING CHEQUE': return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'PENDING BANK': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'ADVANCE PENDING':
      case 'ACCOUNTANT APPROVAL REQUIRED': return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'RISK / MISMATCH': return 'bg-red-100 text-red-800 border-red-200';
      default: return 'bg-gray-50 text-gray-600 border-gray-100';
    }
  };

  const header = (label: string, key: ReconciliationSortKey, align = 'text-left') => (
    <th className={`p-4 text-xs font-bold text-gray-400 uppercase tracking-widest ${align}`}>
      <button
        type="button"
        onClick={() => onSort(key)}
        className={`inline-flex items-center gap-1 ${align === 'text-right' ? 'justify-end w-full' : ''}`}
      >
        <span>{label}</span>
        <span className="text-[10px] text-gray-300">{sortKey === key ? (sortDirection === 'asc' ? '▲' : '▼') : '↕'}</span>
      </button>
    </th>
  );

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
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {items.map((item) => (
            <tr
              key={item.id}
              onClick={() => onRowClick(item)}
              className="hover:bg-blue-50/30 transition-colors duration-200 cursor-pointer group"
            >
              <td className="p-4 text-sm font-mono font-bold text-gray-900">{item.billNo}</td>
              <td className="p-4 text-sm text-gray-600 font-medium">{item.customer}</td>
              <td className="p-4 text-xs text-gray-600 font-semibold min-w-[155px]">
                {formatDateTime(item.invoiceGeneratedAt || item.invoiceDate)}
              </td>
              <td className="p-4 text-sm font-bold text-gray-900">{formatMoney(item.invoiceAmount)}</td>
              <td className="p-4 text-sm font-bold text-gray-900 text-right">{formatMoney(item.bankAmount)}</td>
              <td className={`p-4 text-sm font-black text-right ${item.difference === 0 ? 'text-green-600' : item.difference > 0 ? 'text-red-600' : 'text-orange-600'}`}>
                {formatMoney(item.difference)}
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
                <span className={`px-3 py-2 rounded-xl text-xs font-black border ${getStatusColor(item.status)} shadow-sm inline-block min-w-[112px] max-w-[190px]`}>
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

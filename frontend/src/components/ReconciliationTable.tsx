import React from 'react';
import type { ReconciliationItem } from '../types';
import '../Reconciliation.css'; 

interface ReconciliationTableProps {
  items: ReconciliationItem[];
  onRowClick: (item: ReconciliationItem) => void;
}

const ReconciliationTable: React.FC<ReconciliationTableProps> = ({ items, onRowClick }) => {
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
      case 'Archived': return 'bg-gray-100 text-gray-800 border-gray-200';
      case 'Advance Pending': return 'bg-yellow-50 text-yellow-700 border-yellow-100';
      case 'Ambiguous Match': return 'bg-orange-50 text-orange-700 border-orange-100';
      default: return 'bg-gray-50 text-gray-600 border-gray-100';
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse whitespace-nowrap">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50/50">
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest">Date</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest">Bill No</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest truncate max-w-[120px]">Customer</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest text-right">Invoice Amount</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest text-right">Bank Amount</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest text-right">Difference</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest text-center">Mode</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest text-center">Confidence</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest text-center">Status</th>
            <th className="p-3 text-[10px] font-black text-gray-400 uppercase tracking-widest text-center">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {items.map((item) => (
            <tr 
              key={item.id} 
              className="hover:bg-blue-50/30 transition-colors duration-200 group"
            >
              <td className="p-3 text-xs text-gray-500 font-medium cursor-pointer" onClick={() => onRowClick(item)}>{item.invoiceDate || '---'}</td>
              <td className="p-3 text-xs font-mono font-bold text-gray-900 cursor-pointer" onClick={() => onRowClick(item)}>{item.billNo}</td>
              <td className="p-3 text-xs text-gray-600 font-medium truncate max-w-[120px] cursor-pointer" onClick={() => onRowClick(item)} title={item.customer}>{item.customer}</td>
              <td className="p-3 text-xs font-bold text-gray-900 text-right cursor-pointer" onClick={() => onRowClick(item)}>₹{item.invoiceAmount.toLocaleString()}</td>
              <td className="p-3 text-xs font-bold text-gray-900 text-right cursor-pointer" onClick={() => onRowClick(item)}>₹{item.bankAmount.toLocaleString()}</td>
              <td className={`p-3 text-xs font-black text-right cursor-pointer ${item.difference > 0 ? 'text-red-600' : 'text-green-600'}`} onClick={() => onRowClick(item)}>
                ₹{item.difference.toLocaleString()}
              </td>
              <td className="p-3 text-[10px] font-bold text-gray-400 uppercase text-center cursor-pointer" onClick={() => onRowClick(item)}>{item.paymentMode}</td>
              <td className="p-3 text-center cursor-pointer" onClick={() => onRowClick(item)}>
                <span className={`px-2 py-0.5 rounded-sm text-[9px] font-black uppercase tracking-tighter ${
                  item.matchConfidence === 'High' ? 'bg-green-50 text-green-700' : 
                  item.matchConfidence === 'Medium' ? 'bg-yellow-50 text-yellow-700' : 'bg-red-50 text-red-700'
                }`}>
                  {item.matchConfidence}
                </span>
              </td>
              <td className="p-3 text-center cursor-pointer" onClick={() => onRowClick(item)}>
                <span className={`px-2 py-0.5 rounded-sm text-[9px] font-black border ${getStatusColor(item.status)} shadow-sm inline-block min-w-[90px]`}>
                  {item.status}
                </span>
              </td>
              <td className="p-3 flex gap-2 justify-center items-center">
                {item.invoiceUrl ? (
                  <a href={item.invoiceUrl} target="_blank" rel="noreferrer" className="text-[10px] bg-blue-50 text-blue-700 font-black px-2 py-1 rounded hover:bg-blue-100 transition-colors uppercase tracking-tighter">
                    PDF
                  </a>
                ) : (
                  <span className="text-[9px] text-gray-300 font-bold uppercase">No PDF</span>
                )}
                {item.proofUrl ? (
                  <a href={item.proofUrl} target="_blank" rel="noreferrer" className="text-[10px] bg-purple-50 text-purple-700 font-black px-2 py-1 rounded hover:bg-purple-100 transition-colors uppercase tracking-tighter">
                    Proof
                  </a>
                ) : (
                  <span className="text-[9px] text-gray-300 font-bold uppercase">No Proof</span>
                )}
                <button onClick={() => onRowClick(item)} className="text-[10px] bg-gray-100 text-gray-600 font-black px-2 py-1 rounded hover:bg-gray-200 transition-colors uppercase tracking-tighter">
                  View
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ReconciliationTable;

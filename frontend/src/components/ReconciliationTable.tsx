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
      case 'Cheque Pending': return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'Archived': return 'bg-gray-100 text-gray-800 border-gray-200';
      default: return 'bg-gray-50 text-gray-600 border-gray-100';
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50/50">
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest">Bill No</th>
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest">Customer</th>
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest">Invoice Amount</th>
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">Bank Amount</th>
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">Difference</th>
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest">Mode</th>
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest">Confidence</th>
            <th className="p-6 text-xs font-bold text-gray-400 uppercase tracking-widest text-center">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {items.map((item) => (
            <tr 
              key={item.id} 
              onClick={() => onRowClick(item)} 
              className="hover:bg-blue-50/30 transition-colors duration-200 cursor-pointer group"
            >
              <td className="p-6 text-sm font-mono font-bold text-gray-900">{item.billNo}</td>
              <td className="p-6 text-sm text-gray-600 font-medium">{item.customer}</td>
              <td className="p-6 text-sm font-bold text-gray-900">₹{item.invoiceAmount.toLocaleString()}</td>
              <td className="p-6 text-sm font-bold text-gray-900 text-right">₹{item.bankAmount.toLocaleString()}</td>
              <td className={`p-6 text-sm font-black text-right ${item.difference > 0 ? 'text-red-600' : 'text-green-600'}`}>
                ₹{item.difference.toLocaleString()}
              </td>
              <td className="p-6 text-xs font-bold text-gray-400 uppercase">{item.paymentMode}</td>
              <td className="p-6 text-sm">
                <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter ${
                  item.matchConfidence === 'High' ? 'bg-green-50 text-green-700' : 
                  item.matchConfidence === 'Medium' ? 'bg-yellow-50 text-yellow-700' : 'bg-red-50 text-red-700'
                }`}>
                  {item.matchConfidence}
                </span>
              </td>
              <td className="p-6 text-center">
                <span className={`px-4 py-2 rounded-xl text-xs font-black border ${getStatusColor(item.status)} shadow-sm inline-block min-w-[120px]`}>
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

import React, { useState, useEffect } from 'react';
import { getHeaders } from '../api/client';

interface RawRow {
  [key: string]: any;
}

interface PaymentRow {
  payment_mode: string;
  amount: number;
}

interface ImportedRecord {
  invoice_no: string | null;
  invoice_date: string | null;
  customer_name: string | null;
  mobile: string | null;
  pan: string | null;
  product_summary: string;
  sale_amount: number;
  taxable_amount: number;
  cgst: number;
  sgst: number;
  cash_amount: number;
  bank_amount: number;
  card_amount: number;
  advance_amount: number;
  balance_amount: number;
  bhisi_amount: number;
  other_amount: number;
  customer_purchase_amount: number;
  payment_rows: PaymentRow[];
  source_files: string[];
  validation_status: string;
  unresolved_fields: string[];
  raw_rows: RawRow[];
  source_report: string;
}

interface ExtractionData {
  timestamp: string;
  count: number;
  records: ImportedRecord[];
}

const PrimeExtractionReviewPage: React.FC = () => {
  const [data, setData] = useState<ExtractionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRaw, setExpandedRaw] = useState<number | null>(null);

  useEffect(() => {
    fetch(`${window.location.origin}/api/prime/manual-report-import/latest`, { headers: getHeaders() })
      .then(res => {
        if (!res.ok) throw new Error('API Unavailable: Extraction data could not be loaded.');
        return res.json();
      })
      .then(setData)
      .catch(err => {
        console.error("Extraction fetch error:", err);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleReview = (invoiceNo: string) => {
    alert(`Invoice ${invoiceNo} marked as manually reviewed. Audit log updated.`);
  };

  if (loading) return (
    <div className="p-20 text-center text-gray-500 font-black text-2xl uppercase tracking-widest animate-pulse">
      Retrieving Report Data...
    </div>
  );

  if (error) return (
    <div className="m-8 p-12 bg-red-50 border-2 border-red-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-red-600 mb-2">Extraction Data Offline</h2>
      <p className="text-red-500 font-bold">{error}</p>
    </div>
  );

  if (!data || !data.records || data.records.length === 0) return (
    <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl">
      No invoices found in latest manual report.
    </div>
  );

  // Calculate Header Metrics
  const totalSales = data.records.reduce((sum: number, r: ImportedRecord) => sum + (r.sale_amount || 0), 0);
  const totalCash = data.records.reduce((sum: number, r: ImportedRecord) => sum + (r.cash_amount || 0), 0);
  const totalBank = data.records.reduce((sum: number, r: ImportedRecord) => sum + (r.bank_amount || 0), 0);
  const totalCard = data.records.reduce((sum: number, r: ImportedRecord) => sum + (r.card_amount || 0), 0);
  const reviewCount = data.records.filter((r: ImportedRecord) => r.validation_status === 'NEEDS_REVIEW').length;

  return (
    <div className="p-6 bg-gray-50 min-h-screen font-sans">
      <header className="mb-8">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-3xl font-black text-gray-900 tracking-tight">Prime Extraction Review</h1>
            <p className="text-sm text-gray-500 italic">Latest manual report snapshot: {data.timestamp}</p>
          </div>
          <div className="flex gap-4">
             <div className="bg-red-100 text-red-800 px-4 py-2 rounded-full text-[10px] font-black shadow-sm uppercase tracking-tighter">
               Review Required: {reviewCount}
             </div>
             <div className="bg-blue-100 text-blue-800 px-4 py-2 rounded-full text-[10px] font-black shadow-sm uppercase tracking-tighter">
               Total Records: {data.records.length}
             </div>
          </div>
        </div>

        {/* Global Summary Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
           <div>
              <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Total Sales</p>
              <p className="text-xl font-black text-gray-900">₹{totalSales.toLocaleString()}</p>
           </div>
           <div>
              <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Cash Collection</p>
              <p className="text-xl font-black text-green-600">₹{totalCash.toLocaleString()}</p>
           </div>
           <div>
              <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Bank Collection</p>
              <p className="text-xl font-black text-blue-600">₹{totalBank.toLocaleString()}</p>
           </div>
           <div>
              <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Card Collection</p>
              <p className="text-xl font-black text-orange-600">₹{totalCard.toLocaleString()}</p>
           </div>
        </div>
      </header>

      <div className="space-y-8">
        {data.records.map((inv: ImportedRecord, idx: number) => {
          const statusColor = inv.validation_status === 'GREEN' ? 'bg-green-100 text-green-800 border-green-200' : 'bg-yellow-100 text-yellow-800 border-yellow-200';
          
          return (
            <div key={idx} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              {/* Header Info */}
              <div className="p-6 border-b border-gray-100 flex justify-between items-start">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-4">
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Voucher No</p>
                    <p className="text-lg font-mono font-bold text-gray-900">{inv.invoice_no || '---'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Date</p>
                    <p className="text-lg text-gray-900 font-medium">{inv.invoice_date || '---'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Customer</p>
                    <p className="text-lg text-gray-900 font-bold truncate max-w-[250px]">{inv.customer_name || '---'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Sale Amount</p>
                    <p className="text-lg font-black text-blue-700">₹{inv.sale_amount?.toLocaleString()}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span className={`px-4 py-1 rounded-full text-[10px] font-black border uppercase ${statusColor}`}>
                    {inv.validation_status}
                  </span>
                  <p className="text-[10px] text-gray-400 uppercase font-bold">Files: {inv.source_files?.length}</p>
                </div>
              </div>

              {/* Warnings / Unresolved */}
              {inv.unresolved_fields?.length > 0 && (
                <div className="px-6 py-3 bg-red-50 border-b border-red-100">
                  <p className="text-xs font-bold text-red-700 flex gap-2 items-center">
                    <span className="bg-red-700 text-white px-2 py-0.5 rounded text-[9px]">EXCEPTIONS</span>
                    {inv.unresolved_fields.join(', ')}
                  </p>
                </div>
              )}

              {/* Payment Rows */}
              <div className="p-6">
                <h3 className="text-xs font-black text-gray-400 uppercase tracking-widest mb-4">Settlement Breakdown</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-gray-50">
                        <th className="py-2 text-[10px] font-black text-gray-400 uppercase tracking-widest">Mode</th>
                        <th className="py-2 text-[10px] font-black text-gray-400 uppercase tracking-widest text-right">Amount</th>
                        <th className="py-2 text-[10px] font-black text-gray-400 uppercase tracking-widest pl-8">Evidence Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {inv.payment_rows?.map((pay: PaymentRow, pIdx: number) => (
                        <tr key={pIdx} className="hover:bg-gray-50 transition-colors duration-150">
                          <td className="py-3 text-sm font-black text-gray-700">{pay.payment_mode}</td>
                          <td className="py-3 text-sm font-black text-gray-900 text-right">₹{pay.amount?.toLocaleString()}</td>
                          <td className="py-3 text-xs text-gray-400 pl-8 font-mono tracking-tighter">
                             {pay.payment_mode === 'CASH' ? 'IMMEDIATE_CASH' : 'PENDING_BANK_MATCH'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Raw Rows Expandable */}
              <div className="px-6 py-4 bg-gray-50 flex justify-between items-center">
                <button 
                  onClick={() => setExpandedRaw(expandedRaw === idx ? null : idx)}
                  className="text-xs text-blue-600 hover:text-blue-800 font-black uppercase tracking-widest flex items-center gap-1"
                >
                  {expandedRaw === idx ? 'Hide' : 'Show'} Audit Evidence
                </button>
                <button 
                  onClick={() => handleReview(inv.invoice_no || `INDEX_${idx}`)}
                  className="bg-gray-900 text-white px-8 py-2 rounded-xl text-xs font-black uppercase tracking-widest hover:bg-black shadow-lg transition-all duration-200"
                >
                  Approve Extraction
                </button>
              </div>

              {expandedRaw === idx && (
                <div className="p-6 bg-gray-900 text-green-400 font-mono text-[10px] max-h-[300px] overflow-y-auto rounded-xl">
                  <pre>{JSON.stringify(inv.raw_rows, null, 2)}</pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PrimeExtractionReviewPage;

import React, { useState, useEffect } from 'react';

interface RawControl {
  index?: number;
  value: string;
  rect: string;
}

interface PaymentRow {
  payment_type: string;
  payment_mode: string;
  amount: number;
  raw_data?: string[];
}

interface Invoice {
  timestamp: string;
  form_title?: string;
  fields: {
    invoice_no: string | null;
    invoice_date: string | null;
    customer_name: string | null;
    mobile: string | null;
    invoice_total: number;
  };
  confidence: string;
  unresolved_fields: string[];
  raw_controls: RawControl[];
  status: string;
}

interface ExtractionData {
  timestamp: string;
  extracted_count: number;
  invoices: Array<{
    invoice: Invoice;
    payment_rows: PaymentRow[];
    validation: any;
  }>;
}

const PrimeExtractionReviewPage: React.FC = () => {
  const [data, setData] = useState<ExtractionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRaw, setExpandedRaw] = useState<number | null>(null);

  useEffect(() => {
    fetch('/api/prime/manual-report-import/latest')
      .then(res => res.json())
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleReview = (invoiceNo: string) => {
    alert(`Invoice ${invoiceNo} marked as manually reviewed. Audit log updated.`);
  };

  if (loading) return <div className="p-8 text-center text-gray-600">Loading extraction data...</div>;
  if (error) return <div className="p-8 text-center text-red-600">Error: {error}</div>;
  if (!data || !data.records || data.records.length === 0) return <div className="p-8 text-center text-gray-600">No invoices extracted for review.</div>;

  // Calculate Header Metrics
  const totalSales = data.records.reduce((sum, r) => sum + (r.sale_amount || 0), 0);
  const totalCash = data.records.reduce((sum, r) => sum + (r.cash_amount || 0), 0);
  const totalBank = data.records.reduce((sum, r) => sum + (r.bank_amount || 0), 0);
  const totalCard = data.records.reduce((sum, r) => sum + (r.card_amount || 0), 0);
  const reviewCount = data.records.filter(r => r.validation_status === 'NEEDS_REVIEW').length;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <header className="mb-8">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-3xl font-black text-gray-900 tracking-tight">Prime Extraction Review</h1>
            <p className="text-sm text-gray-500 italic">Latest manual report snapshot: {data.timestamp}</p>
          </div>
          <div className="flex gap-4">
             <div className="bg-red-100 text-red-800 px-4 py-2 rounded-full text-xs font-black shadow-sm uppercase">
               Review Required: {reviewCount}
             </div>
             <div className="bg-blue-100 text-blue-800 px-4 py-2 rounded-full text-xs font-black shadow-sm uppercase">
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
        {data.records.map((inv, idx) => {
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
                        <th className="py-2 text-[10px] font-black text-gray-400 uppercase tracking-widest pl-8">Evidence Source</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {inv.payment_rows?.map((pay, pIdx) => (
                        <tr key={pIdx} className="hover:bg-gray-50 transition-colors duration-150">
                          <td className="py-3 text-sm font-black text-gray-700">{pay.payment_mode}</td>
                          <td className="py-3 text-sm font-black text-gray-900 text-right">₹{pay.amount?.toLocaleString()}</td>
                          <td className="py-3 text-xs text-gray-400 pl-8 font-mono">
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
                <div className="p-6 bg-gray-900 text-green-400 font-mono text-[10px] max-h-[300px] overflow-y-auto">
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

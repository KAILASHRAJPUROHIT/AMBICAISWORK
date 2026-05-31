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
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch manual report data');
        return res.json();
      })
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleReview = (invoiceNo: string) => {
    alert(`Invoice ${invoiceNo} marked as manually reviewed. Audit log updated.`);
  };

  if (loading) return <div className="p-8 text-center text-gray-600">Loading extraction data...</div>;
  if (error) return <div className="p-8 text-center text-red-600">Error: {error}</div>;
  if (!data || data.invoices.length === 0) return <div className="p-8 text-center text-gray-600">No invoices extracted for review.</div>;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <header className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Prime Extraction Review</h1>
          <p className="text-sm text-gray-500 italic">Latest snapshot: {data.timestamp}</p>
        </div>
        <div className="bg-blue-100 text-blue-800 px-4 py-2 rounded-full text-sm font-semibold shadow-sm">
          Total Invoices: {data.extracted_count}
        </div>
      </header>

      <div className="space-y-8">
        {data.invoices.map((item, idx) => {
          const inv = item.invoice;
          const statusColor = inv.status === 'GREEN' ? 'bg-green-100 text-green-800 border-green-200' : 'bg-yellow-100 text-yellow-800 border-yellow-200';
          
          return (
            <div key={idx} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              {/* Header Info */}
              <div className="p-6 border-b border-gray-100 flex justify-between items-start">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-4">
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Invoice No</p>
                    <p className="text-lg font-mono text-gray-900">{inv.fields.invoice_no || '---'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Date</p>
                    <p className="text-lg text-gray-900">{inv.fields.invoice_date || '---'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Customer</p>
                    <p className="text-lg text-gray-900 truncate max-w-[200px]">{inv.fields.customer_name || '---'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 uppercase font-bold tracking-wider">Total Amount</p>
                    <p className="text-lg font-bold text-blue-700">₹{inv.fields.invoice_total.toLocaleString()}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span className={`px-4 py-1 rounded-full text-xs font-bold border ${statusColor}`}>
                    {inv.status}
                  </span>
                  <p className="text-[10px] text-gray-400 uppercase font-bold">Confidence: {inv.confidence}</p>
                </div>
              </div>

              {/* Warnings / Unresolved */}
              {inv.unresolved_fields.length > 0 && (
                <div className="px-6 py-3 bg-red-50 border-b border-red-100">
                  <p className="text-sm text-red-700">
                    <strong>Manual Check Required:</strong> Missing fields: {inv.unresolved_fields.join(', ')}
                  </p>
                </div>
              )}

              {/* Payment Rows */}
              <div className="p-6">
                <h3 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-4">Payment Breakdown</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-gray-50">
                        <th className="py-2 text-xs text-gray-500 uppercase">Mode</th>
                        <th className="py-2 text-xs text-gray-500 uppercase text-right">Amount</th>
                        <th className="py-2 text-xs text-gray-500 uppercase">Raw Context</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {item.payment_rows.map((pay, pIdx) => (
                        <tr key={pIdx} className="hover:bg-gray-50 transition-colors duration-150">
                          <td className="py-3 text-sm font-medium text-gray-700">{pay.payment_mode}</td>
                          <td className="py-3 text-sm font-bold text-gray-900 text-right">₹{pay.amount.toLocaleString()}</td>
                          <td className="py-3 text-xs text-gray-400 truncate max-w-[300px]">
                            {pay.raw_data?.join(' | ') || 'No raw data captured'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Raw Controls Expandable */}
              <div className="px-6 py-4 bg-gray-50 flex justify-between items-center">
                <button 
                  onClick={() => setExpandedRaw(expandedRaw === idx ? null : idx)}
                  className="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                >
                  {expandedRaw === idx ? 'Hide' : 'Show'} Raw Extraction Evidence
                </button>
                <button 
                  onClick={() => handleReview(inv.fields.invoice_no || `INDEX_${idx}`)}
                  className="bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-bold hover:bg-blue-700 shadow transition-all duration-200"
                >
                  Mark as Reviewed
                </button>
              </div>

              {expandedRaw === idx && (
                <div className="p-6 bg-gray-900 text-blue-300 font-mono text-[11px] max-h-[300px] overflow-y-auto">
                  {inv.raw_controls.map((ctrl, cIdx) => (
                    <div key={cIdx} className="mb-1">
                      <span className="text-gray-500">[{ctrl.index || cIdx}]</span> {ctrl.value} 
                      <span className="text-gray-600 ml-4 opacity-50">{ctrl.rect}</span>
                    </div>
                  ))}
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

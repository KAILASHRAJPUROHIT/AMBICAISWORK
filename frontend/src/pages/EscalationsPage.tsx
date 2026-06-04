import React, { useState, useEffect } from 'react';
import { getHeaders } from '../api/client';

const EscalationsPage: React.FC = () => {
  const [escalations, setEscalations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${window.location.origin}/api/prime/manual-report-import/latest`, { headers: getHeaders() })
      .then(res => {
        if (!res.ok) throw new Error('API Unavailable: Could not fetch escalation records.');
        return res.json();
      })
      .then(data => {
        const records = data.records || [];
        const filtered = records.filter((r: any) => r.validation_status === 'NEEDS_REVIEW');
        setEscalations(filtered);
      })
      .catch(err => {
        console.error("Escalations fetch error:", err);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-12 text-center text-gray-500 font-bold text-xl uppercase tracking-widest animate-pulse">Scanning for exceptions...</div>;

  if (error) return (
    <div className="m-8 p-12 bg-red-50 border-2 border-red-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-red-600 mb-2">Escalation Engine Offline</h2>
      <p className="text-red-500 font-bold">{error}</p>
    </div>
  );

  return (
    <div className="p-8 bg-gray-50 min-h-screen font-sans">
      <header className="mb-12">
        <h1 className="text-4xl font-black text-red-600 tracking-tight">Accountant Escalations</h1>
        <p className="mt-2 text-lg text-gray-600">Critical mismatches and missing fields identified from Prime reports.</p>
      </header>
      
      <div className="max-w-5xl space-y-6">
        {escalations.length === 0 ? (
          <div className="bg-white p-16 text-center rounded-3xl border border-gray-100 shadow-sm">
            <p className="text-green-600 text-2xl font-black mb-2">Clean Slate</p>
            <p className="text-gray-400 font-medium">All imported records are currently validated. No escalations found.</p>
          </div>
        ) : (
          escalations.map((item, idx) => (
            <div key={idx} className="bg-white p-8 rounded-2xl shadow-sm border-l-[12px] border-red-500 flex justify-between items-center group hover:shadow-md transition-all duration-300">
              <div>
                <div className="flex items-center gap-4 mb-2">
                  <h3 className="text-2xl font-black text-gray-900 font-mono tracking-tighter">
                     {item.invoice_no || 'MANUAL_MATCH_REQUIRED'}
                  </h3>
                  <span className="bg-red-50 text-red-600 px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border border-red-100">
                    {item.unresolved_fields?.[0] || 'CRITICAL_ERROR'}
                  </span>
                </div>
                <p className="text-gray-500 font-bold uppercase text-[11px] tracking-widest mb-4">{item.customer_name}</p>
                
                <div className="bg-gray-50 px-4 py-3 rounded-xl border border-gray-100 max-w-xl">
                   <p className="text-xs text-gray-600 leading-relaxed">
                     <strong>Alert:</strong> Total Sale <b>₹{item.sale_amount?.toLocaleString()}</b> does not match the sum of extracted payment rows. 
                     Audit trail indicates missing or conflicting settlement data in Prime.
                   </p>
                </div>
              </div>
              
              <div className="text-right">
                 <p className="text-[10px] font-black text-gray-400 uppercase mb-1">Mismatch Amount</p>
                 <p className="text-3xl font-black text-red-600">₹{(item.sale_amount || 0).toLocaleString()}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default EscalationsPage;

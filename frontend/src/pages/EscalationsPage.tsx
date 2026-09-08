import React, { useState, useEffect, useCallback } from 'react';
import { getOpenEscalations } from '../api/client';

interface Escalation {
  escalation_id: string;
  bill_id: number;
  bill_no: string;
  customer_name: string;
  invoice_amount: number;
  received_amount: number;
  difference: number;
  payment_mode: string;
  reason: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  status: string;
  confidence: string;
  invoice_date: string | null;
  invoice_timestamp: string | null;
  pdf_available: boolean;
}

interface EscalationsResponse {
  count: number;
  critical_count: number;
  high_count: number;
  escalations: Escalation[];
}

const inr = (n: number) =>
  '₹' + (n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });

const fmtDate = (iso: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: 'bg-red-100 text-red-700 border-red-200',
  HIGH: 'bg-orange-100 text-orange-700 border-orange-200',
  MEDIUM: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  LOW: 'bg-gray-100 text-gray-600 border-gray-200',
};

const EscalationsPage: React.FC = () => {
  const [data, setData] = useState<EscalationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    isRefresh ? setRefreshing(true) : setLoading(true);
    setError(null);
    try {
      const res = (await getOpenEscalations()) as EscalationsResponse;
      setData(res);
    } catch (err: any) {
      console.error('Escalations fetch error:', err);
      setError(err?.message || 'Could not load escalations.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openPdf = (billId: number) => {
    window.open(`${window.location.origin}/api/invoices/pdf/${billId}`, '_blank');
  };

  if (loading) {
    return (
      <div className="p-20 text-center text-gray-400 font-black text-xl uppercase tracking-widest animate-pulse">
        Scanning for exceptions…
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="m-2 p-12 bg-red-50 border-2 border-red-200 rounded-3xl text-center">
          <h2 className="text-2xl font-black text-red-600 mb-2">Escalation Engine Offline</h2>
          <p className="text-red-500 font-bold">{error}</p>
          <button
            onClick={() => load()}
            className="mt-6 bg-gray-900 text-white px-8 py-3 rounded-xl text-xs font-black uppercase tracking-widest hover:bg-black"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const escalations = data?.escalations ?? [];

  return (
    <div className="p-6 bg-gray-50 min-h-screen font-sans">
      <header className="mb-8">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-3xl font-black text-gray-900 tracking-tight">Owner Escalations</h1>
            <p className="text-sm text-gray-500 italic">
              Bills flagged by the reconciliation engine as needing owner attention
            </p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="bg-white border border-gray-200 text-gray-700 px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-gray-50 shadow-sm disabled:opacity-50"
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>

        {/* Summary chips */}
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Open Escalations</p>
            <p className="text-2xl font-black text-gray-900">{data?.count ?? 0}</p>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Critical (Risk / Mismatch)</p>
            <p className="text-2xl font-black text-red-600">{data?.critical_count ?? 0}</p>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">High (Approval Required)</p>
            <p className="text-2xl font-black text-orange-600">{data?.high_count ?? 0}</p>
          </div>
        </div>
      </header>

      {escalations.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100">
          <div className="text-5xl mb-4">✓</div>
          <p className="text-gray-700 font-black text-xl uppercase tracking-wide">All clear</p>
          <p className="text-gray-400 font-bold mt-1">No bills currently require owner escalation.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {['Severity', 'Bill No', 'Customer', 'Invoice', 'Received', 'Difference', 'Reason', 'Mode', 'Date', ''].map((h) => (
                    <th key={h} className="py-3 px-4 text-[10px] font-black text-gray-400 uppercase tracking-widest whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {escalations.map((e) => (
                  <tr key={e.escalation_id} className="hover:bg-gray-50 transition-colors">
                    <td className="py-3 px-4">
                      <span className={`px-3 py-1 rounded-full text-[9px] font-black border uppercase ${SEVERITY_STYLES[e.severity] || SEVERITY_STYLES.LOW}`}>
                        {e.severity}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-gray-900 whitespace-nowrap">{e.bill_no}</td>
                    <td className="py-3 px-4 text-gray-800 font-semibold truncate max-w-[200px]">{e.customer_name}</td>
                    <td className="py-3 px-4 font-black text-gray-900 text-right whitespace-nowrap">{inr(e.invoice_amount)}</td>
                    <td className="py-3 px-4 text-gray-700 text-right whitespace-nowrap">{inr(e.received_amount)}</td>
                    <td className={`py-3 px-4 text-right font-bold whitespace-nowrap ${Math.abs(e.difference) > 0.01 ? 'text-red-600' : 'text-green-600'}`}>
                      {inr(e.difference)}
                    </td>
                    <td className="py-3 px-4 text-xs font-bold text-gray-600 whitespace-nowrap">{e.reason}</td>
                    <td className="py-3 px-4 text-xs text-gray-500 whitespace-nowrap">{e.payment_mode}</td>
                    <td className="py-3 px-4 text-xs text-gray-500 whitespace-nowrap">{fmtDate(e.invoice_date)}</td>
                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      {e.pdf_available && (
                        <button
                          onClick={() => openPdf(e.bill_id)}
                          className="text-blue-600 hover:text-blue-800 text-[10px] font-black uppercase tracking-widest"
                        >
                          Invoice
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default EscalationsPage;

import React, { useEffect, useState } from 'react';
import { getAccountantVerificationQueue } from '../api/client';

interface AccountantQueueItem {
  id: number;
  invoice_no: string;
  customer_name?: string;
  amount?: number;
  payment_mode?: string;
  proof_status?: string;
  payment_status?: string;
  confidence_level?: string;
  due_at?: string;
  remaining_seconds?: number;
  reason?: string;
}

const formatCurrency = (value?: number) => {
  if (value === undefined || value === null) return '₹0';
  return `₹${value.toLocaleString('en-IN')}`;
};

const formatDueAt = (value?: string) => {
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatRemaining = (seconds?: number) => {
  if (seconds === undefined || seconds === null) return 'Not Recorded';
  const overdue = seconds < 0;
  const absolute = Math.abs(seconds);
  const hours = Math.floor(absolute / 3600);
  const minutes = Math.floor((absolute % 3600) / 60);
  const label = `${hours}h ${minutes}m`;
  return overdue ? `${label} overdue` : `${label} left`;
};

const EscalationsPage: React.FC = () => {
  const [items, setItems] = useState<AccountantQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getAccountantVerificationQueue()
      .then((data) => {
        if (!mounted) return;
        setItems(Array.isArray(data) ? data : []);
        setError(null);
      })
      .catch((err) => {
        if (!mounted) return;
        console.error('Accountant verification queue fetch error:', err);
        setError(err.message || 'Unable to load accountant verification queue.');
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="p-12 text-center text-gray-500 font-bold text-xl uppercase tracking-widest animate-pulse">
        Loading accountant verification queue...
      </div>
    );
  }

  if (error) {
    return (
      <div className="m-8 p-10 bg-red-50 border border-red-200 rounded-2xl">
        <h2 className="text-2xl font-black text-red-600 mb-2">Unable to load accountant verification queue.</h2>
        <p className="text-red-500 font-bold">{error}</p>
      </div>
    );
  }

  return (
    <div className="p-8 bg-gray-50 min-h-screen font-sans">
      <header className="mb-8">
        <h1 className="text-4xl font-black text-red-600 tracking-tight">Accountant Escalations</h1>
        <p className="mt-2 text-lg text-gray-600">Payments requiring accountant verification before closure.</p>
      </header>

      {items.length === 0 ? (
        <div className="bg-white p-12 text-center rounded-2xl border border-gray-100 shadow-sm">
          <p className="text-green-600 text-2xl font-black mb-2">No accountant verification items.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <p className="text-xs font-black uppercase tracking-widest text-gray-500">Open Queue</p>
            <p className="text-sm font-black text-gray-900">{items.length} items</p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-100 text-gray-500 uppercase text-[11px] tracking-widest">
                <tr>
                  <th className="text-left p-4">Invoice</th>
                  <th className="text-left p-4">Customer</th>
                  <th className="text-right p-4">Amount</th>
                  <th className="text-left p-4">Mode</th>
                  <th className="text-left p-4">Proof</th>
                  <th className="text-left p-4">Payment</th>
                  <th className="text-left p-4">Confidence</th>
                  <th className="text-left p-4">Due</th>
                  <th className="text-left p-4">Timer</th>
                  <th className="text-left p-4">Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((item) => (
                  <tr key={item.id} className="align-top hover:bg-gray-50">
                    <td className="p-4 font-black font-mono text-gray-900">{item.invoice_no}</td>
                    <td className="p-4 font-bold text-gray-700">{item.customer_name || 'Not Recorded'}</td>
                    <td className="p-4 text-right font-black text-gray-900">{formatCurrency(item.amount)}</td>
                    <td className="p-4 font-bold text-gray-700">{item.payment_mode || 'Not Recorded'}</td>
                    <td className="p-4">
                      <span className="px-2 py-1 rounded bg-amber-50 text-amber-700 text-[11px] font-black uppercase">
                        {item.proof_status || 'UNKNOWN'}
                      </span>
                    </td>
                    <td className="p-4 font-black text-gray-800">{item.payment_status || 'UNKNOWN'}</td>
                    <td className="p-4 font-black text-gray-800">{item.confidence_level || 'UNKNOWN'}</td>
                    <td className="p-4 font-bold text-gray-700">{formatDueAt(item.due_at)}</td>
                    <td className="p-4 font-black text-gray-800">{formatRemaining(item.remaining_seconds)}</td>
                    <td className="p-4 text-gray-600 max-w-sm">{item.reason || 'Review required.'}</td>
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

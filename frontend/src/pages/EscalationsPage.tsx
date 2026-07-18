import { useEffect, useState } from 'react';
import { getOpenEscalations } from '../api/client';

const EscalationsPage = () => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOpenEscalations()
      .then(setItems)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-12 text-center text-gray-500 font-bold text-xl uppercase tracking-widest animate-pulse">Scanning for exceptions...</div>;
  if (error) return <div className="m-8 p-12 bg-red-50 border-2 border-red-200 rounded-3xl text-center"><h2 className="text-2xl font-black text-red-600 mb-2">Escalation Engine Offline</h2><p className="text-red-500 font-bold">{error}</p></div>;

  return (
    <div className="p-8 bg-gray-50 min-h-screen font-sans">
      <header className="mb-12">
        <h1 className="text-4xl font-black text-red-600 tracking-tight">Owner Escalations</h1>
        <p className="mt-2 text-lg text-gray-600">Live high-risk and exception cases from this business's tenant database.</p>
      </header>
      <div className="max-w-5xl space-y-6">
        {items.length === 0 ? (
          <div className="bg-white p-16 text-center rounded-3xl border border-gray-100 shadow-sm"><p className="text-green-600 text-2xl font-black mb-2">No open escalations</p><p className="text-gray-400 font-medium">No Red, Orange, or Purple invoice cases currently require owner action.</p></div>
        ) : items.map((item) => (
          <div key={item.id} className="bg-white p-8 rounded-2xl shadow-sm border-l-[12px] border-red-500 flex justify-between items-center">
            <div><h3 className="text-2xl font-black text-gray-900 font-mono">{item.invoice_no}</h3><p className="mt-2 text-xs font-black uppercase text-red-600">{item.reason}</p><p className="mt-3 text-sm text-gray-500">{item.customer_name}</p></div>
            <div className="text-right"><p className="text-[10px] font-black text-gray-400 uppercase mb-1">Invoice amount</p><p className="text-3xl font-black text-red-600">₹{Number(item.amount || 0).toLocaleString('en-IN')}</p></div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EscalationsPage;

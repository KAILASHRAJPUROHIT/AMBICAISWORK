import React, { useEffect, useState } from 'react';
import { getEscalationExceptions } from '../api/client';

interface EscalationException {
  id: string;
  bill_id: number;
  invoice_no: string;
  category: string;
  reason: string;
  amount: number;
  payment_mode: string;
  status: string;
  age_days: number;
}

const EscalationsPage: React.FC = () => {
  const [exceptions, setExceptions] = useState<EscalationException[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchExceptions = () => {
    setLoading(true);
    setError(null);
    getEscalationExceptions()
      .then((data: any) => setExceptions(data))
      .catch((err: any) => setError(err.message || 'Failed to load exceptions.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchExceptions();
  }, []);

  const exceptionsByCategory = exceptions.reduce((acc, current) => {
    if (!acc[current.category]) acc[current.category] = [];
    acc[current.category].push(current);
    return acc;
  }, {} as Record<string, EscalationException[]>);

  const formatCurrency = (value: number) => `₹${value.toLocaleString('en-IN')}`;

  if (error) return (
    <div className="m-8 p-12 bg-red-50 border-2 border-red-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-red-600 mb-2">Escalations Offline</h2>
      <p className="text-red-500 font-bold">{error}</p>
      <button type="button" onClick={fetchExceptions} className="mt-6 rounded-xl bg-red-600 px-5 py-3 text-sm font-black uppercase tracking-widest text-white hover:bg-red-700">
        Retry
      </button>
    </div>
  );

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10 text-center md:text-left">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Exception Dashboard</h1>
        <p className="mt-2 text-lg text-gray-600 font-medium">Critical system alerts and ageing payments.</p>
      </header>

      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-pulse uppercase tracking-widest">
          Loading Exceptions...
        </div>
      ) : exceptions.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl">
          No critical exceptions found.
        </div>
      ) : (
        <div className="space-y-12">
          {Object.entries(exceptionsByCategory).map(([category, items]) => (
            <section key={category}>
              <h2 className="text-2xl font-black text-gray-800 mb-6 border-b-2 border-gray-200 pb-2 inline-block">
                {category} <span className="ml-2 rounded-full bg-red-100 text-red-700 px-3 py-1 text-sm">{items.length}</span>
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {items.map(item => (
                  <div key={item.id} className="bg-white rounded-3xl p-6 shadow-sm border border-red-100 hover:shadow-md transition-shadow relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-2 h-full bg-red-500" />
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <p className="text-xs font-black uppercase tracking-widest text-gray-400">Bill No</p>
                        <p className="font-bold text-gray-900 text-lg">{item.invoice_no}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-black text-gray-900 text-lg">{formatCurrency(item.amount)}</p>
                        <p className="text-xs font-bold uppercase text-gray-400">{item.payment_mode}</p>
                      </div>
                    </div>
                    <p className="text-sm font-semibold text-red-700 bg-red-50 rounded-xl p-3 border border-red-100">
                      {item.reason}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
};

export default EscalationsPage;

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getBankActivity } from '../api/client';

interface Activity {
  id: number;
  bank_name: string;
  account: string;
  counterparty: string;
  amount: number;
  date: string;
  time: string;
  reference: string;
  mode: string;
}

interface BankActivityResponse {
  generated_at: string;
  credits: Activity[];
  debits: Activity[];
}

const money = (amount: number) => `₹${Number(amount || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

const ActivityTable = ({ type, records }: { type: 'credit' | 'debit'; records: Activity[] }) => {
  const credit = type === 'credit';
  const headers = credit
    ? ['Bank', 'Credited to', 'Customer / Remitter', 'Date', 'Time', 'Amount', 'Ref / UTR', 'Mode']
    : ['Bank', 'Debited from', 'Debited by / To', 'Date', 'Time', 'Amount', 'Ref / UTR', 'Mode'];
  return (
    <section className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div className={`px-6 py-5 flex items-center justify-between ${credit ? 'bg-emerald-50' : 'bg-rose-50'}`}>
        <div>
          <h2 className={`text-lg font-black ${credit ? 'text-emerald-900' : 'text-rose-900'}`}>{credit ? 'Credits' : 'Debits'}</h2>
          <p className="text-xs font-semibold text-gray-500">{records.length} recorded transaction{records.length === 1 ? '' : 's'}</p>
        </div>
      </div>
      {records.length === 0 ? <div className="p-10 text-center text-sm font-bold text-gray-400">No {type} transactions received yet.</div> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead><tr className="bg-gray-50 border-y border-gray-100">{headers.map(h => <th key={h} className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-gray-400 whitespace-nowrap">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-gray-100">{records.map(row => <tr key={row.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 text-sm font-bold text-gray-900 whitespace-nowrap">{row.bank_name}</td>
              <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">{row.account}</td>
              <td className="px-4 py-3 text-sm text-gray-700 max-w-56 truncate">{row.counterparty}</td>
              <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">{row.date}</td>
              <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">{row.time}</td>
              <td className={`px-4 py-3 text-sm font-black whitespace-nowrap ${credit ? 'text-emerald-700' : 'text-rose-700'}`}>{money(row.amount)}</td>
              <td className="px-4 py-3 text-xs font-mono text-gray-600 whitespace-nowrap">{row.reference}</td>
              <td className="px-4 py-3 text-xs font-black text-gray-600 whitespace-nowrap">{row.mode}</td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
};

const BankActivityPage: React.FC = () => {
  const [data, setData] = useState<BankActivityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const loadingRequest = useRef(false);
  const load = useCallback(async (manual = false) => {
    if (loadingRequest.current) return;
    loadingRequest.current = true;
    manual ? setRefreshing(true) : setLoading(true);
    try { setData(await getBankActivity() as BankActivityResponse); setError(null); }
    catch (err: any) { setError(err?.message || 'Could not load bank activity.'); }
    finally { loadingRequest.current = false; setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); const timer = window.setInterval(() => load(), 1000); return () => window.clearInterval(timer); }, [load]);
  if (loading) return <div className="p-20 text-center text-gray-400 font-black uppercase tracking-widest animate-pulse">Loading bank activity…</div>;
  return <div className="p-6 bg-gray-50 min-h-screen">
    <header className="mb-7 flex justify-between items-start"><div><h1 className="text-3xl font-black text-gray-900">Bank Activity</h1><p className="mt-1 text-sm text-gray-500">Live records from bank-alert SMS emails. Screen refreshes every second; raw SMS is never shown here.</p></div><button onClick={() => load(true)} disabled={refreshing} className="px-5 py-2.5 rounded-xl bg-white border border-gray-200 text-[10px] font-black uppercase tracking-widest text-gray-700 disabled:opacity-50">{refreshing ? 'Refreshing…' : 'Refresh'}</button></header>
    {error ? <div className="mb-6 p-5 rounded-2xl border border-red-200 bg-red-50 text-red-700 font-bold">{error}</div> : null}
    <div className="space-y-7"><ActivityTable type="credit" records={data?.credits || []} /><ActivityTable type="debit" records={data?.debits || []} /></div>
  </div>;
};

export default BankActivityPage;

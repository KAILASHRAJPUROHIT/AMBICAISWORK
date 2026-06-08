import React, { useState, useEffect } from 'react';
import StatCard from '../components/StatCard';
import AlertSoundSystem from '../api/AlertSoundSystem';
import { getDashboardToday } from '../api/client';
import type { DashboardTodayResponse } from '../types';
import '../Dashboard.css';

const DashboardPage: React.FC = () => {
  const [data, setData] = useState<DashboardTodayResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const response = await getDashboardToday();
      setData(response);
      setError(null);
    } catch (err: any) {
      console.error("Fetch error:", err);
      setError('Backend Unreachable');
      AlertSoundSystem.playCritical();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, []);

  const num = (v?: number | null) => Number(v ?? 0).toLocaleString("en-IN");
  const money = (v?: number | null) => `₹${Number(v ?? 0).toLocaleString("en-IN")}`;

  if (loading) return (
    <div className="p-8 bg-gray-50 min-h-screen">
       <div className="mb-12 h-10 w-64 bg-gray-200 rounded-lg animate-pulse"></div>
       <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-6 mb-16">
         {[1,2,3,4,5,6].map(i => (
           <div key={i} className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm animate-pulse">
             <div className="h-2 w-16 bg-gray-200 rounded mb-4"></div>
             <div className="h-6 w-24 bg-gray-300 rounded"></div>
           </div>
         ))}
       </div>
    </div>
  );

  if (error && !data) return (
    <div className="m-8 p-8 bg-red-50 border-2 border-red-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-red-600 mb-2">System Offline</h2>
      <p className="text-red-500 font-bold">{error}</p>
      <button 
        onClick={() => window.location.reload()}
        className="mt-6 bg-red-600 text-white px-8 py-3 rounded-xl font-black uppercase tracking-widest hover:bg-red-700 transition-colors"
      >
        Retry Connection
      </button>
    </div>
  );

  return (
    <div className="p-8 bg-gray-50 min-h-screen font-sans">
      <header className="mb-8">
        <h1 className="text-4xl font-black text-gray-900 tracking-tight mb-2">Today's Operational Pipeline</h1>
        <p className="text-lg text-gray-500 font-medium">Real-time payment and reconciliation activity</p>
      </header>
      
      <section className="mb-10">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-6">
            <StatCard label="Bills Created" value={num(data?.kpis.billsCreated)} />
            <StatCard label="Payments Received" value={num(data?.kpis.paymentsReceived)} />
            <StatCard label="Auto Verified" value={num(data?.kpis.autoVerified)} />
            <StatCard label="Awaiting Review" value={num(data?.kpis.awaitingReview)} />
            <StatCard label="Pending Bank Proof" value={num(data?.kpis.pendingProof)} />
            <StatCard label="Escalations Generated" value={num(data?.kpis.escalations)} />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Recent Payment Events (Today)</h2>
        <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider">Time</th>
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider">Invoice No</th>
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider">Customer</th>
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider text-right">Amount</th>
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider">Mode</th>
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider">Proof</th>
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider">Confidence</th>
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider">State</th>
              </tr>
            </thead>
            <tbody>
              {data?.recentEvents.map((event) => (
                <tr key={event.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors group">
                  <td className="p-5 text-sm text-gray-500 font-medium">{event.time}</td>
                  <td className="p-5 font-bold text-gray-900">{event.invoice_no}</td>
                  <td className="p-5 text-sm text-gray-600">{event.customer}</td>
                  <td className="p-5 font-black text-gray-900 text-right">{money(event.amount)}</td>
                  <td className="p-5 text-sm font-bold text-gray-700">{event.mode}</td>
                  <td className="p-5">
                    <span className={`text-[10px] font-bold px-2 py-1 rounded-md uppercase tracking-wide ${
                      ['present', 'matched'].includes(event.proof?.toLowerCase()) ? 'bg-green-100 text-green-700' :
                      ['partial', 'mismatch_proof'].includes(event.proof?.toLowerCase()) ? 'bg-yellow-100 text-yellow-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {event.proof || 'UNKNOWN'}
                    </span>
                  </td>
                  <td className="p-5">
                    <span className={`text-[10px] font-bold px-2 py-1 rounded-md uppercase tracking-wide ${
                      event.confidence === 'High' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                    }`}>
                      {event.confidence}
                    </span>
                  </td>
                  <td className="p-5">
                    <span className="text-xs font-bold text-gray-600 uppercase">
                      {event.state || 'PENDING'}
                    </span>
                  </td>
                </tr>
              ))}
              {(!data?.recentEvents || data.recentEvents.length === 0) && (
                <tr>
                  <td colSpan={8} className="p-12 text-center text-gray-400 font-medium italic">No payment events recorded today.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default DashboardPage;

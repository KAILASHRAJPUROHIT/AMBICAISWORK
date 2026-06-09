import React, { useState, useEffect } from 'react';
import StatCard from '../components/StatCard';
import AlertSoundSystem from '../api/AlertSoundSystem';
import { getDashboardToday, openAuthenticatedBlob } from '../api/client';
import type { DashboardTodayResponse } from '../types';
import '../Dashboard.css';
const allowedProofModes = ['UPI', 'IMPS', 'NEFT', 'RTGS', 'CARD', 'CHEQUE'];
const canOpenProof = (pb: any) => {
  const modeUpper = (pb.mode || '').toUpperCase();
  return (
    allowedProofModes.includes(modeUpper) &&
    pb.proof_url &&
    pb.proof_url.length > 0 &&
    pb.proof_exists === true
  );
};

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

  const getDynamicDate = () => {
    const d = new Date();
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const date = d.getDate();
    const nth = (day: number) => {
        if (day > 3 && day < 21) return 'th';
        switch (day % 10) {
            case 1:  return "st";
            case 2:  return "nd";
            case 3:  return "rd";
            default: return "th";
        }
    };
    return `${days[d.getDay()]} ${date}${nth(date)} ${months[d.getMonth()]} ${d.getFullYear()}`;
  };

  return (
    <div className="p-8 bg-gray-50 min-h-screen font-sans">
      <header className="mb-8">
        <h1 className="text-4xl font-black text-gray-900 tracking-tight mb-2">{getDynamicDate()}</h1>
        <p className="text-lg text-gray-500 font-bold uppercase tracking-widest">Today</p>
      </header>
      
      <section className="mb-10">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard label="Bills Created" value={num(data?.kpis.billsCreated)} />
            <StatCard label="Payments Received" value={num(data?.kpis.paymentsReceived)} />
            <StatCard label="Auto Verified" value={num(data?.kpis.autoVerified)} />
            <StatCard label="Pending Bank Proof" value={num(data?.kpis.pendingProof)} />
        </div>
      </section>

      {data?.kpis.paymentTotals && (
        <section className="mb-10">
            <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Payment Type Totals Today</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
                {Object.entries(data.kpis.paymentTotals).map(([mode, amount]) => (
                    <div key={mode} className="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm text-center">
                        <p className="text-xs font-black text-gray-400 uppercase tracking-wider mb-1">{mode}</p>
                        <p className="text-lg font-black text-gray-900">{money(amount)}</p>
                    </div>
                ))}
            </div>
        </section>
      )}

      <section>
        <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">SNAPSHOT — {getDynamicDate()}</h2>
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
                <th className="p-5 text-xs font-black text-gray-500 uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.recentEvents.map((event) => (
                <tr key={event.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors group">
                  <td className="p-5 text-sm text-gray-500 font-medium">{event.time}</td>
                  <td className="p-5 font-bold text-gray-900">
                    <div className="flex flex-col">
                        <span>{event.invoice_no}</span>
                        {event.pdfUrl && (
                            <button onClick={() => openAuthenticatedBlob(event.pdfUrl!)} className="text-xs text-blue-600 hover:text-blue-800 font-medium mt-1 inline-flex items-center gap-1">
                                View Invoice PDF
                            </button>
                        )}
                    </div>
                  </td>
                  <td className="p-5 text-sm text-gray-600">{event.customer}</td>
                  <td className="p-5 font-black text-gray-900 text-right">{money(event.amount)}</td>
                  <td className="p-5 text-sm font-bold text-gray-700">{event.mode}</td>
                  <td className="p-5">
                    <div className="flex flex-col gap-3">
                        <span className={`text-[10px] font-bold px-2 py-1 rounded-md uppercase tracking-wide w-max ${
                          ['present', 'matched', '2+ proofs for same transaction'].includes(event.unifiedProofLabel?.toLowerCase() || '') ? 'bg-green-100 text-green-700' :
                          ['partial', 'mismatch_proof', 'possible related proof - requires review'].includes(event.unifiedProofLabel?.toLowerCase() || '') ? 'bg-yellow-100 text-yellow-700' :
                          'bg-red-100 text-red-700'
                        }`}>
                          {event.unifiedProofLabel || event.proof || 'UNKNOWN'}
                        </span>
                        
                        {event.paymentBreakdown && event.paymentBreakdown.length > 0 && (
                          <div className="flex flex-col gap-2 mt-1">
                            {event.paymentBreakdown.map((pb, pidx) => (
                              <div key={pidx} className="border border-gray-100 rounded-md p-2 bg-gray-50">
                                <div className="flex justify-between items-center mb-1">
                                  <span className="text-[10px] font-bold text-gray-700">{pb.mode} • {money(pb.amount)}</span>
                                  {canOpenProof(pb) && (
                                    <button onClick={() => openAuthenticatedBlob(pb.proof_url!)} className="text-[10px] text-blue-600 hover:text-blue-800 font-bold">
                                      View Payment Proof
                                    </button>
                                  )}
                                </div>
                                {pb.sources && pb.sources.length > 0 && (
                                    <details className="text-xs relative">
                                        <summary className="cursor-pointer text-blue-600 hover:text-blue-800 font-medium text-[10px]">View sources</summary>
                                        <div className="absolute top-full left-0 mt-2 bg-white border border-gray-200 shadow-xl rounded-xl p-3 w-64 z-10">
                                            {pb.sources.map((src, idx) => (
                                                <div key={idx} className="mb-2 last:mb-0">
                                                    <p className="font-bold text-gray-800">{src.type}</p>
                                                    <p className="text-gray-600 text-[10px] leading-tight break-words">{src.details}</p>
                                                    <p className="text-[9px] font-black uppercase mt-1 text-purple-600">{src.status}</p>
                                                    {src.url && (
                                                      <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-[9px] text-blue-600 block mt-1 hover:underline">
                                                        Open Evidence
                                                      </a>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </details>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                    </div>
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
                    {event.integrity_status === 'CONTRADICTORY_STATE' && event.dashboard_warning_reason && (
                      <div className="mt-2 text-[10px] text-red-600 font-bold leading-tight max-w-[150px]">
                        ⚠️ {event.dashboard_warning_reason}
                      </div>
                    )}
                  </td>
                  <td className="p-5 text-right">
                  </td>
                </tr>
              ))}
              {(!data?.recentEvents || data.recentEvents.length === 0) && (
                <tr>
                  <td colSpan={9} className="p-12 text-center text-gray-400 font-medium italic">No payment events recorded today.</td>
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

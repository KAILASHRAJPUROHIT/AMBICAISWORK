import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import StatCard from '../components/StatCard';
import AlertSoundSystem from '../api/AlertSoundSystem';
import { getHeaders } from '../api/client';
import '../Dashboard.css';

interface DashboardStats {
  totalBillsToday: number;
  importedToday: number;
  pendingPreviousDays: number;
  verified: number;
  pendingReview: number;
  partialPaid: number;
  unverifiedAdvancesCount: number;
  unverifiedAdvancesAmount: number;
  totalCollection: number;
  cashCollection: number;
  bankCollection: number;
  smsConfirmed: number;
  emailConfirmed: number;
  chequeCollection: number;
  pdfCountInShare: number;
  matchAccuracy: number;
  is_owner?: boolean;
}

interface IngestionStatus {
  watcher_running: boolean;
  watch_path: string;
  path_exists: boolean;
  pdf_files_found: number;
  files_processed: number;
  invoices_inserted: number;
  skipped_duplicates: number;
  failed_files: number;
  last_file_seen: string | null;
  last_processed_time: string | null;
  last_error: string | null;
  cuda_active: boolean;
}

interface EmailStatus {
  last_sync: string | null;
  next_sync: number | null;
  events_found: number;
  last_error: string | null;
  is_running: boolean;
}

interface SMSStatus {
  last_sync: string | null;
  next_sync: number | null;
  events_found: number;
  last_error: string | null;
  is_running: boolean;
}

interface LiveInvoice {
  id: number;
  bill_number: string;
  invoice_date: string;
  invoice_time: string | null;
  invoice_generated_at: string | null;
  ingested_at: string | null;
  pipeline_delay_seconds: number;
  customer_name: string;
  invoice_total: number;
  cust_purc: number;
  advance: number;
  net_payable: number;
  paid_amount: number;
  remaining_amount: number;
  status: string;
  status_text: string;
  is_historical_claim: boolean;
  historical_payment_date: string | null;
  pdf_path: string | null;
  created_at: string;
}

interface LivePaymentEvent {
  id: string;
  source: string;
  bank: string;
  account?: string;
  amount: number;
  reference: string;
  timestamp: string;
  confidence: string;
  payer?: string;
  raw: string;
}

const initialStats: DashboardStats = {
  totalBillsToday: 0,
  importedToday: 0,
  pendingPreviousDays: 0,
  verified: 0,
  pendingReview: 0,
  partialPaid: 0,
  unverifiedAdvancesCount: 0,
  unverifiedAdvancesAmount: 0,
  totalCollection: 0,
  cashCollection: 0,
  bankCollection: 0,
  smsConfirmed: 0,
  emailConfirmed: 0,
  chequeCollection: 0,
  pdfCountInShare: 0,
  matchAccuracy: 0
};

const DashboardPage: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats>(initialStats);
  const [appVersion, setAppVersion] = useState<string>("v1.2.0");
  const [ingestionStatus, setIngestionStatus] = useState<IngestionStatus | null>(null);
  const [emailStatus, setEmailStatus] = useState<EmailStatus | null>(null);
  const [smsStatus, setSMSStatus] = useState<SMSStatus | null>(null);
  const [liveFeed, setLiveFeed] = useState<LiveInvoice[]>([]);
  const [paymentEvents, setPaymentEvents] = useState<LivePaymentEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState({ pdf: false, email: false, sms: false });
  const [selectedEvent, setSelectedEvent] = useState<LivePaymentEvent | null>(null);

  const API_BASE = window.location.origin;

  // SAFE FORMATTERS
  const money = (v?: number | null) => `₹${Number(v ?? 0).toLocaleString("en-IN")}`;
  const num = (v?: number | null) => Number(v ?? 0).toLocaleString("en-IN");

  const fetchData = async () => {
    const headers = getHeaders();

    try {
      const endpoints = [
        `${API_BASE}/api/dashboard/live`,
        `${API_BASE}/api/invoices/live-feed`,
        `${API_BASE}/api/admin/ingestion-status`,
        `${API_BASE}/api/admin/email-status`,
        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/live-payment-events`,
        `${API_BASE}/api/version`
      ];

      const responses = await Promise.all(endpoints.map(url => 
        fetch(url, { headers }).catch(() => null)
      ));

      const dashboardLive = responses[0] && responses[0].ok ? await responses[0].json() : null;
      if (dashboardLive) setStats(dashboardLive);

      const liveFeed = responses[1] && responses[1].ok ? await responses[1].json() : null;
      if (liveFeed) setLiveFeed(liveFeed);

      const ingestionStatus = responses[2] && responses[2].ok ? await responses[2].json() : null;
      if (ingestionStatus) setIngestionStatus(ingestionStatus);

      if (responses[3] && responses[3].ok) setEmailStatus(await (responses[3] as Response).json());
      if (responses[4] && responses[4].ok) setSMSStatus(await (responses[4] as Response).json());
      if (responses[5] && responses[5].ok) setPaymentEvents(await (responses[5] as Response).json());
      if (responses[6] && responses[6].ok) {
         const vData = await (responses[6] as Response).json();
         setAppVersion(vData.version);
      }

      // Check for auth failure
      if (responses[1] && responses[1].status === 401) {
          setError('Session Expired. Please Login.');
          return;
      }

      // Only show error if core stats or feed fail when NOT loading
      if ((!responses[0] || !responses[0].ok) && (!responses[1] || !responses[1].ok) && !loading) {
          setError('API Connection Lost');
          AlertSoundSystem.playCritical();
      } else {
          setError(null);
      }
      
    } catch (err: any) {
      console.error("Fetch error:", err);
      if (!loading) {
          setError('Backend Unreachable');
          AlertSoundSystem.playCritical();
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000); // 3 second polling
    return () => clearInterval(interval);
  }, []);

  const triggerSync = async (type: 'pdf' | 'email' | 'sms') => {
    setIsSyncing(prev => ({ ...prev, [type]: true }));
    const url = type === 'pdf' ? `${API_BASE}/api/scan-now` : 
                type === 'email' ? `${API_BASE}/api/email-sync-now` : 
                `${API_BASE}/api/sms-sync-now`;
    
    try {
      await fetch(url, { method: 'POST', headers: getHeaders() });
      setTimeout(fetchData, 1000); // Refresh after 1s
    } catch (e) {
      console.error(`Sync failed for ${type}:`, e);
    } finally {
      setTimeout(() => setIsSyncing(prev => ({ ...prev, [type]: false })), 2000);
    }
  };

  const openPDF = async (bill_id: number) => {
    try {
      const response = await fetch(`${API_BASE}/api/invoices/pdf/${bill_id}`, {
        headers: getHeaders()
      });
      if (!response.ok) {
        if (response.status === 401) {
          window.location.href = '/login';
        } else {
          throw new Error('Failed to load PDF');
        }
        return;
      }
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, '_blank');
    } catch (e) {
      console.error("Error opening PDF:", e);
      alert("Error opening PDF. It may not exist on the server.");
    }
  };

  // GROUPING LOGIC (Limit to 8 for dashboard compactness)
  const displayFeed = liveFeed.slice(0, 8);
  const groupedFeed = displayFeed.reduce((acc: { [key: string]: LiveInvoice[] }, inv) => {
    const date = inv.invoice_date || 'Unknown Date';
    if (!acc[date]) acc[date] = [];
    acc[date].push(inv);
    return acc;
  }, {});

  const sortedDates = Object.keys(groupedFeed).sort((a, b) => b.localeCompare(a));

  const formatDelay = (seconds: number) => {
    if (seconds < 0) return '---';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
  };

  const SkeletonCard = () => (
    <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm animate-pulse">
      <div className="h-2 w-16 bg-gray-200 rounded mb-4"></div>
      <div className="h-6 w-24 bg-gray-300 rounded"></div>
    </div>
  );

  const operatorLabel = (status_text: string) => {
      if (!status_text) return '';
      return status_text
          .replace('CASH_PLUS_BANK_CONFIRMED', 'Cash & Bank Cleared')
          .replace('LOW_CONFIDENCE_MATCH', 'Manual Review Needed')
          .replace('ADVANCE_PAYMENT_TYPE_UNKNOWN', 'Advance Unverified')
          .replace('AMBIGUOUS_AMOUNT_MATCH', 'Ambiguous Match')
          .replace('PARTIALLY_PAID', 'Partial Payment');
  };

  if (loading) return (
    <div className="p-8 bg-gray-50 min-h-screen">
       <div className="mb-12 h-10 w-64 bg-gray-200 rounded-lg animate-pulse"></div>
       <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-16">
         {[1,2,3,4].map(i => <SkeletonCard key={i} />)}
       </div>
       <div className="grid grid-cols-3 gap-8">
          <div className="col-span-1 space-y-4">
             {[1,2,3,4].map(i => <SkeletonCard key={i} />)}
          </div>
          <div className="col-span-2 bg-white rounded-2xl h-96 animate-pulse"></div>
       </div>
    </div>
  );

  if (error && !stats) return (
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
      {/* Pipeline Status Header */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
         {/* Invoice Watcher Status */}
         <div className={`p-4 rounded-xl border-2 transition-all ${ingestionStatus?.watcher_running ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-center justify-between mb-2">
               <span className="text-[10px] font-black uppercase tracking-widest text-gray-400">Invoice Watcher</span>
               <button 
                onClick={() => triggerSync('pdf')}
                disabled={isSyncing.pdf}
                className={`text-[9px] font-black px-2 py-1 rounded bg-white border border-gray-200 hover:bg-gray-50 uppercase ${isSyncing.pdf ? 'animate-spin' : ''}`}
               >
                 {isSyncing.pdf ? '...' : 'Sync Now'}
               </button>
            </div>
            <div className="flex items-center">
               <div className={`w-2 h-2 rounded-full mr-2 ${ingestionStatus?.watcher_running ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
               <span className="font-bold text-xs">{ingestionStatus?.watcher_running ? 'Realtime Online' : 'Offline'}</span>
               <span className="mx-2 text-gray-300 text-xs">|</span>
               <span className="text-xs font-medium text-gray-600">{ingestionStatus?.pdf_files_found || 0} PDFs In Share</span>
            </div>
         </div>

         {/* Email Poller Status */}
         <div className={`p-4 rounded-xl border-2 transition-all ${emailStatus?.is_running ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'}`}>
            <div className="flex items-center justify-between mb-2">
               <span className="text-[10px] font-black uppercase tracking-widest text-gray-400">Bank Email Poller</span>
               <button 
                onClick={() => triggerSync('email')}
                disabled={isSyncing.email}
                className="text-[9px] font-black px-2 py-1 rounded bg-white border border-gray-200 hover:bg-gray-50 uppercase"
               >
                 Sync
               </button>
            </div>
            <div className="flex items-center">
               <div className={`w-2 h-2 rounded-full mr-2 ${emailStatus?.is_running ? 'bg-blue-500 animate-spin' : 'bg-gray-400'}`}></div>
               <span className="font-bold text-xs">{emailStatus?.is_running ? 'Polling...' : 'Idle'}</span>
               <span className="mx-2 text-gray-300 text-xs">|</span>
               <span className="text-xs font-medium text-gray-600">Events: {emailStatus?.events_found || 0}</span>
            </div>
         </div>

         {/* SMS Gateway Status */}
         <div className={`p-4 rounded-xl border-2 transition-all ${smsStatus?.is_running ? 'bg-orange-50 border-orange-200' : 'bg-gray-50 border-gray-200'}`}>
            <div className="flex items-center justify-between mb-2">
               <span className="text-[10px] font-black uppercase tracking-widest text-gray-400">Android SMS Relay</span>
               <button 
                onClick={() => triggerSync('sms')}
                disabled={isSyncing.sms}
                className="text-[9px] font-black px-2 py-1 rounded bg-white border border-gray-200 hover:bg-gray-50 uppercase"
               >
                 Poll
               </button>
            </div>
            <div className="flex items-center">
               <div className={`w-2 h-2 rounded-full mr-2 ${smsStatus?.is_running ? 'bg-orange-500 animate-pulse' : 'bg-gray-400'}`}></div>
               <span className="font-bold text-xs">{smsStatus?.is_running ? 'Relaying...' : 'Online'}</span>
               <span className="mx-2 text-gray-300 text-xs">|</span>
               <span className="text-xs font-medium text-gray-600">Events: {smsStatus?.events_found || 0}</span>
            </div>
         </div>
      </div>

      <header className="mb-6 flex justify-between items-end">
        <div>
           <div className="flex items-center space-x-3 mb-1">
              <h1 className="text-4xl font-black text-gray-900 tracking-tight">Payment Auditor Live</h1>
              <span className="bg-gray-200 text-gray-500 text-[10px] font-black px-2 py-0.5 rounded-md uppercase tracking-widest">{appVersion}</span>
           </div>
           <p className="mt-2 text-lg text-gray-600 font-medium">Real-time Ingestion & Reconciliation Pipeline</p>
        </div>
        {ingestionStatus?.cuda_active && (
           <div className="bg-purple-100 text-purple-700 text-[10px] font-black px-4 py-2 rounded-xl flex items-center border border-purple-200">
              <span className="w-2 h-2 bg-purple-500 rounded-full mr-2 animate-pulse"></span>
              RTX 5070 CUDA ACCELERATION ACTIVE
           </div>
        )}
      </header>
      
      <section className="mb-6">
        <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-4 border-b border-gray-200 pb-2">Operational Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
            <StatCard label="Bills Dated Today" value={num(stats?.totalBillsToday)} />
            <StatCard label="Imported Today" value={num(stats?.importedToday)} />
            <StatCard label="Verified Cleared" value={num(stats?.verified)} />
            <StatCard label="Unverified Adv" value={num(stats?.unverifiedAdvancesCount)} />
            <StatCard label="Pending Previous" value={num(stats?.pendingPreviousDays)} />
            <StatCard label="Total Review" value={num(stats?.pendingReview)} />
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {stats?.is_owner && (
        <div className="lg:col-span-1">
          <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Financial Collection (Today)</h2>
          <div className="grid grid-cols-1 gap-4">
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
                 <p className="text-[10px] font-black text-gray-400 uppercase mb-2 tracking-tighter">Total Sale</p>
                 <p className="text-xl font-black text-gray-900">{money(stats?.totalCollection)}</p>
              </div>
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm border-l-4 border-l-green-500">
                 <p className="text-[10px] font-black text-green-500 uppercase mb-2 tracking-tighter">Cash In Hand (After opening)</p>
                 <p className="text-xl font-black text-gray-900">{money(stats?.cashCollection)}</p>
              </div>
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
                 <p className="text-[10px] font-black text-gray-400 uppercase mb-2 tracking-tighter">Bank Confirmed (Live)</p>
                 <div className="flex justify-between items-center">
                    <p className="text-xl font-black text-gray-900">{money(stats?.bankCollection)}</p>
                    <div className="text-[9px] text-gray-400 font-bold space-y-1">
                       <div>E: {money(stats?.emailConfirmed)}</div>
                       <div>S: {money(stats?.smsConfirmed)}</div>
                    </div>
                 </div>
              </div>
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm border-l-4 border-l-blue-500">
                 <p className="text-[10px] font-black text-blue-500 uppercase mb-2 tracking-tighter">Cheques Pending</p>
                 <p className="text-xl font-black text-gray-900">{money(stats?.chequeCollection)}</p>
              </div>
          </div>
        </div>
        )}

        <div className={stats?.is_owner ? "lg:col-span-2" : "lg:col-span-3"}>
          <div className="flex justify-between items-center mb-6 border-b border-gray-200 pb-2">
             <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest">Recent Pipeline Activity</h2>
             <Link to="/reconciliation" className="text-[10px] bg-black text-white px-4 py-2 rounded-lg uppercase font-black tracking-widest hover:bg-gray-800 transition-colors shadow-lg shadow-black/10">
                 Open Full Pipeline
             </Link>
          </div>
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            {sortedDates.length > 0 ? sortedDates.map(date => (
              <div key={date}>
                <div className="bg-black text-white px-4 py-2 text-[10px] font-black uppercase tracking-tighter">
                   {date}
                </div>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="p-4 text-[10px] font-black text-gray-400 uppercase">PDF</th>
                      <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Bill No / Time</th>
                      <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Customer</th>
                      <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Net Pay</th>
                      <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Delay</th>
                      <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupedFeed[date].map((inv) => (
                      <tr key={inv.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                        <td className="p-4">
                          {inv.pdf_path ? (
                            <button 
                              onClick={() => openPDF(inv.id)}
                              className="w-8 h-8 flex items-center justify-center rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                              </svg>
                            </button>
                          ) : (
                            <span className="text-[8px] text-gray-300 font-bold uppercase">No PDF</span>
                          )}
                        </td>
                        <td className="p-4">
                           <div className="font-black text-gray-900 leading-none">{inv.bill_number}</div>
                           <div className="text-[9px] text-gray-400 font-bold mt-1 uppercase">Gen: {inv.invoice_date} {inv.invoice_time || ''}</div>
                           {inv.is_historical_claim && (
                             <div className="mt-1 flex items-center text-[8px] font-black text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-100 uppercase tracking-tighter animate-pulse">
                                ⚠ Historical Claim
                             </div>
                           )}
                        </td>
                        <td className="p-4 text-sm text-gray-600 truncate max-w-[100px] font-medium">{inv.customer_name}</td>
                        <td className="p-4 font-black text-gray-900 text-right">{money(inv.net_payable)}</td>
                        <td className="p-4 text-right">
                           <span className={`text-[9px] font-black px-2 py-0.5 rounded ${inv.pipeline_delay_seconds > 600 ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-500'}`}>
                             {formatDelay(inv.pipeline_delay_seconds || 0)}
                           </span>
                        </td>
                        <td className="p-4">
                          <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase ${
                            inv.status === 'Green' ? 'bg-green-100 text-green-700' : 
                            inv.status === 'Yellow' ? 'bg-yellow-100 text-yellow-700' :
                            inv.status === 'Blue' ? 'bg-blue-100 text-blue-700' :
                            inv.status === 'Purple' ? 'bg-purple-100 text-purple-700' :
                            'bg-red-100 text-red-700'
                          }`}>
                            {operatorLabel(inv.status_text || inv.status)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )) : (
              <div className="p-12 text-center text-gray-400 italic">
                {error === 'Session Expired. Please Login.' ? (
                    <span className="text-red-500 font-bold">Authentication Required to View Feed</span>
                ) : (stats?.pdfCountInShare || 0) > 0 || stats?.totalBillsToday ? (
                    <span className="text-orange-500 font-bold uppercase tracking-widest text-xs animate-pulse">Feed Sync Error: Invoices exist but are not loading. Check Session.</span>
                ) : (
                    'No invoices ingested yet. Waiting for PDFs...'
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-6">
        <div className="lg:col-span-3">
          <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Recent Payment Events</h2>
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Source</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Bank/Account</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Amount</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Reference</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Timestamp</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Confidence</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {paymentEvents.slice(0, 5).map((event) => (
                  <tr key={event.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="p-4 font-bold text-gray-900">[{event.source}]</td>
                    <td className="p-4 text-sm text-gray-600">
                      {event.bank} {event.account ? `(${event.account})` : ''}
                    </td>
                    <td className="p-4 font-black text-gray-900">{money(event.amount)}</td>
                    <td className="p-4 text-sm font-mono">{event.reference || 'N/A'}</td>
                    <td className="p-4 text-xs text-gray-500">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="p-4">
                      <span className={`text-[9px] font-black px-2 py-1 rounded-full uppercase ${
                        event.confidence === 'HIGH' ? 'bg-green-100 text-green-700' : 
                        event.confidence === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {event.confidence}
                      </span>
                    </td>
                    <td className="p-4">
                      <button 
                        onClick={() => setSelectedEvent(event)}
                        className="text-[10px] font-black text-blue-600 uppercase hover:underline"
                      >
                        Show Evidence
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {paymentEvents.length === 0 && (
              <div className="p-12 text-center text-gray-400 italic">No payment events detected yet.</div>
            )}
          </div>
        </div>
      </div>

      {/* Evidence Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-8 z-50">
          <div className="bg-white rounded-3xl p-8 max-w-2xl w-full shadow-2xl">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h3 className="text-xl font-black text-gray-900 uppercase">Payment Evidence</h3>
                <p className="text-sm text-gray-500">{selectedEvent.bank} | {selectedEvent.timestamp}</p>
              </div>
              <button onClick={() => setSelectedEvent(null)} className="text-gray-400 hover:text-gray-900 font-bold">Close</button>
            </div>
            <div className="bg-gray-50 p-6 rounded-2xl border border-gray-100 font-mono text-xs whitespace-pre-wrap max-h-96 overflow-y-auto">
              {selectedEvent.raw}
            </div>
            <div className="mt-8 pt-6 border-t border-gray-100 flex justify-end">
               <button onClick={() => setSelectedEvent(null)} className="bg-gray-900 text-white px-8 py-3 rounded-xl font-black uppercase tracking-widest hover:bg-black transition-colors">
                  Got it
               </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardPage;

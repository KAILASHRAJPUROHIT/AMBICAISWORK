import React, { useState, useEffect } from 'react';
import StatCard from '../components/StatCard';
import AlertSoundSystem from '../api/AlertSoundSystem';
import { getSessionToken } from '../api/client';
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
  totalSaleToday: number | null;
  cashInHandToday: number | null;
  bankConfirmedToday: number | null;
  chequesPendingToday: number | null;
  totalReview: number;
  financialDataAvailable: boolean;
  latestOperationalDate: string | null;
  operationalDate?: string | null;
  isShowingToday?: boolean;
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
  active_watch_path?: string;
  path_exists: boolean;
  observer_started?: boolean;
  watcher_mode?: string;
  observer_error?: string | null;
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


interface TodayBill {
  id: number;
  bill_number: string;
  customer_name: string;
  amount: number;
  payment_mode: string;
  status: string;
  invoice_date: string | null;
}

interface TodayPayment {
  id: number;
  invoice_number: string;
  customer_name: string;
  amount_received: number;
  payment_mode: string;
  utr_reference: string;
  payment_date: string | null;
  status: string;
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
  totalSaleToday: null,
  cashInHandToday: null,
  bankConfirmedToday: null,
  chequesPendingToday: null,
  totalReview: 0,
  financialDataAvailable: false,
  latestOperationalDate: null,
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
  const [todayBills, setTodayBills] = useState<TodayBill[]>([]);
  const [todayPayments, setTodayPayments] = useState<TodayPayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dashboardApiAvailable, setDashboardApiAvailable] = useState(false);
  const [isSyncing, setIsSyncing] = useState({ pdf: false, email: false, sms: false });
    
  const API_BASE = window.location.origin;

  // SAFE FORMATTERS
  const money = (v?: number | null) => `₹${Number(v ?? 0).toLocaleString("en-IN")}`;
  const moneyOrUnavailable = (...values: Array<number | null | undefined>) => {
    if (!dashboardApiAvailable) return 'Data unavailable';
    const value = values.find(v => v !== null && v !== undefined);
    return money(value ?? 0);
  };
  const num = (v?: number | null) => Number(v ?? 0).toLocaleString("en-IN");
  const fmtDay = (iso?: string | null) => {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d.getTime())
      ? iso
      : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  };
  const showingToday = stats?.isShowingToday !== false;
  const periodLabel = showingToday ? 'Today' : fmtDay(stats?.operationalDate || stats?.latestOperationalDate);

    const fetchData = async () => {
    const token = getSessionToken();
    const headers = {
      'X-Session-Token': token || ''
    };

    try {
      const endpoints = [
        `${API_BASE}/api/dashboard/live`,
        `${API_BASE}/api/admin/ingestion-status`,
        `${API_BASE}/api/admin/email-status`,
        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/version`
      ];

      const responses = await Promise.all(endpoints.map(url => 
        fetch(url, { headers }).catch(() => null)
      ));

      const dashboardLive = responses[0] && responses[0].ok ? await responses[0].json() : null;
      console.log("DASHBOARD_LIVE_RESPONSE:", dashboardLive);
      setDashboardApiAvailable(!!dashboardLive);
      if (dashboardLive) setStats(dashboardLive);

      const ingestionStatus = responses[1] && responses[1].ok ? await responses[1].json() : null;
      console.log("INGESTION_STATUS_RESPONSE:", ingestionStatus);
      if (ingestionStatus) setIngestionStatus(ingestionStatus);

      if (responses[2] && responses[2].ok) setEmailStatus(await (responses[2] as Response).json());
      if (responses[3] && responses[3].ok) setSMSStatus(await (responses[3] as Response).json());
      if (responses[4] && responses[4].ok) {
         const vData = await (responses[4] as Response).json();
         setAppVersion(vData.version);
      }

      // Fetch new dashboard split feeds independently
      const [billsRes, paymentsRes] = await Promise.all([
        fetch(`${API_BASE}/api/dashboard/today-bills`, { headers }).catch(() => null),
        fetch(`${API_BASE}/api/dashboard/today-payments`, { headers }).catch(() => null)
      ]);
      
      if (billsRes && billsRes.ok) {
        const billsData = await billsRes.json();
        setTodayBills(Array.isArray(billsData) ? billsData : []);
      } else {
        setTodayBills([]);
      }

      if (paymentsRes && paymentsRes.ok) {
        const paymentsData = await paymentsRes.json();
        setTodayPayments(Array.isArray(paymentsData) ? paymentsData : []);
      } else {
        setTodayPayments([]);
      }

      // Check for auth failure
      if (responses[0] && responses[0].status === 401) {
          setError('Session Expired. Please Login.');
          return;
      }

      // Only show error if core stats or feed fail when NOT loading
      if ((!responses[0] || !responses[0].ok) && !loading) {
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
      await fetch(url, { method: 'POST' });
      setTimeout(fetchData, 1000); // Refresh after 1s
    } catch (e) {
      console.error(`Sync failed for ${type}:`, e);
    } finally {
      setTimeout(() => setIsSyncing(prev => ({ ...prev, [type]: false })), 2000);
    }
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

  const pipelineStatusClass = (status: string, statusText: string | null) => {
    const normalized = `${status || ''} ${statusText || ''}`.toUpperCase();
    if (['CLEARED', 'VERIFIED', 'PAID'].some(s => normalized.includes(s)) || normalized.includes('GREEN')) {
      return 'bg-green-100 text-green-700 border-green-200';
    }
    if (['PENDING', 'INITIATED', 'AWAITING_CONFIRMATION'].some(s => normalized.includes(s)) || normalized.includes('YELLOW')) {
      return 'bg-yellow-100 text-yellow-700 border-yellow-200';
    }
    if (['DELIVERY_APPROVED_BEFORE_PAYMENT', 'APPROVAL_DELIVERY'].some(s => normalized.includes(s)) || normalized.includes('PURPLE')) {
      return 'bg-orange-100 text-orange-700 border-orange-200';
    }
    if (['MISMATCH', 'ERROR', 'PAYMENT_TOTAL_MISMATCH', 'FRAUD_RISK'].some(s => normalized.includes(s)) || normalized.includes('RED')) {
      return 'bg-red-100 text-red-700 border-red-200';
    }
    if (['CHEQUE_DEPOSITED', 'CHEQUE_CLEARING', 'REALIZING_CHEQUE'].some(s => normalized.includes(s)) || normalized.includes('BLUE')) {
      return 'bg-blue-100 text-blue-700 border-blue-200';
    }
    if (['ARCHIVED', 'CLOSED'].some(s => normalized.includes(s))) {
      return 'bg-gray-100 text-gray-700 border-gray-200';
    }
    return 'bg-gray-100 text-gray-700 border-gray-200';
  };

  const watcher = (() => {
    if (!ingestionStatus) {
      return {
        label: 'Checking',
        cardClass: 'bg-gray-50 border-gray-200',
        dotClass: 'bg-gray-400',
      };
    }
    if (ingestionStatus.watcher_running) {
      return {
        label: ingestionStatus.watcher_mode === 'polling' ? 'Online (Polling)' : 'Online',
        cardClass: 'bg-green-50 border-green-200',
        dotClass: 'bg-green-500 animate-pulse',
      };
    }
    if (!ingestionStatus.path_exists) {
      return {
        label: 'Offline',
        cardClass: 'bg-red-50 border-red-200',
        dotClass: 'bg-red-500',
      };
    }
    return {
      label: 'Share Reachable, Watcher Paused',
      cardClass: 'bg-yellow-50 border-yellow-200',
      dotClass: 'bg-yellow-500',
    };
  })();

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
         <div className={`p-4 rounded-xl border-2 transition-all ${watcher.cardClass}`}>
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
            <div className="flex items-center flex-wrap gap-y-1">
               <div className={`w-2 h-2 rounded-full mr-2 ${watcher.dotClass}`}></div>
               <span className="font-bold text-xs">{watcher.label}</span>
               <span className="mx-2 text-gray-300 text-xs">|</span>
               <span className="text-xs font-medium text-gray-600">{ingestionStatus?.pdf_files_found || 0} PDFs In Share</span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-[9px] font-bold uppercase tracking-tighter text-gray-500">
               <div>Last Scan: <span className="text-gray-800">{ingestionStatus?.last_processed_time || 'Never'}</span></div>
               <div>Processed: <span className="text-gray-800">{num(ingestionStatus?.files_processed)}</span></div>
               <div>Failed: <span className={ingestionStatus?.failed_files ? 'text-red-600' : 'text-gray-800'}>{num(ingestionStatus?.failed_files)}</span></div>
            </div>
            {ingestionStatus?.last_error && (
              <div className="mt-2 text-[9px] font-bold text-red-600 truncate">Error: {ingestionStatus.last_error}</div>
            )}
            {ingestionStatus?.observer_error && (
              <div className="mt-1 text-[9px] font-bold text-yellow-700 truncate">Observer: {ingestionStatus.observer_error}</div>
            )}
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
              <h1 className="text-4xl font-black text-gray-900 tracking-tight">Aradhana Auditor Live</h1>
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
            <StatCard label={showingToday ? 'Bills Dated Today' : `Bills (${periodLabel})`} value={num(stats?.totalBillsToday)} />
            <StatCard label="Imported Today" value={num(stats?.importedToday)} />
            <StatCard label={showingToday ? 'Verified Cleared' : `Verified (${periodLabel})`} value={num(stats?.verified)} />
            <StatCard label="Advance Verification Queue" value={num(stats?.unverifiedAdvancesCount)} />
            <StatCard label="Pending Previous Days" value={num(stats?.pendingPreviousDays)} />
            <StatCard label="Review Queue" value={num(stats?.totalReview ?? stats?.pendingReview)} />
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {stats?.is_owner && (
        <div className="lg:col-span-1">
          <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-2 border-b border-gray-200 pb-2">Financial Collection ({periodLabel})</h2>
          {!showingToday && (
            <p className="mb-4 text-[10px] font-bold text-amber-600 uppercase tracking-wide bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              Showing latest business day — no billing activity dated today yet.
            </p>
          )}
          <div className="grid grid-cols-1 gap-4">
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
                 <p className="text-[10px] font-black text-gray-400 uppercase mb-2 tracking-tighter">Total Sale</p>
                 <p className="text-xl font-black text-gray-900">{moneyOrUnavailable(stats?.totalSaleToday, stats?.totalCollection)}</p>
              </div>
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm border-l-4 border-l-green-500">
                 <p className="text-[10px] font-black text-green-500 uppercase mb-2 tracking-tighter">Cash In Hand (After opening)</p>
                 <p className="text-xl font-black text-gray-900">{moneyOrUnavailable(stats?.cashInHandToday, stats?.cashCollection)}</p>
              </div>
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
                 <p className="text-[10px] font-black text-gray-400 uppercase mb-2 tracking-tighter">Bank Confirmed (Live)</p>
                 <div className="flex justify-between items-center">
                    <p className="text-xl font-black text-gray-900">{moneyOrUnavailable(stats?.bankConfirmedToday, stats?.bankCollection)}</p>
                    <div className="text-[9px] text-gray-400 font-bold space-y-1">
                       <div>E: {money(stats?.emailConfirmed)}</div>
                       <div>S: {money(stats?.smsConfirmed)}</div>
                    </div>
                 </div>
              </div>
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm border-l-4 border-l-blue-500">
                 <p className="text-[10px] font-black text-blue-500 uppercase mb-2 tracking-tighter">Cheques Pending</p>
                 <p className="text-xl font-black text-gray-900">{moneyOrUnavailable(stats?.chequesPendingToday, stats?.chequeCollection)}</p>
              </div>
          </div>
        </div>
        )}

        <div className={stats?.is_owner ? "lg:col-span-2" : "lg:col-span-3"}>
          <div className="flex flex-col gap-8">
            {/* SECTION A - TODAY'S BILLS */}
            <div>
              <div className="flex justify-between items-center mb-4 border-b border-gray-200 pb-2">
                <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest">Section A — Bills ({periodLabel})</h2>
              </div>
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="sticky top-0 bg-gray-50 z-10 shadow-sm border-b border-gray-100">
                      <tr>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Invoice Number</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Customer Name</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Amount</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Mode</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Invoice Date</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {todayBills.length > 0 ? todayBills.map((bill) => (
                        <tr key={bill.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                          <td className="p-4 font-black text-gray-900">{bill.bill_number}</td>
                          <td className="p-4 text-sm text-gray-600 font-medium">{bill.customer_name}</td>
                          <td className="p-4 font-black text-gray-900 text-right">{money(bill.amount)}</td>
                          <td className="p-4 text-xs font-bold text-gray-600">{bill.payment_mode}</td>
                          <td className="p-4 text-xs text-gray-500">{bill.invoice_date ? new Date(bill.invoice_date).toLocaleString() : 'N/A'}</td>
                          <td className="p-4">
                            <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase border ${pipelineStatusClass(bill.status, null)}`}>
                              {operatorLabel(bill.status)}
                            </span>
                          </td>
                        </tr>
                      )) : (
                        <tr><td colSpan={6} className="p-8 text-center text-gray-400 italic font-medium">No bills recorded for {periodLabel}.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* SECTION B - TODAY'S PAYMENTS */}
            <div>
              <div className="flex justify-between items-center mb-4 border-b border-gray-200 pb-2">
                <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest">Section B — Payments ({periodLabel})</h2>
              </div>
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="sticky top-0 bg-gray-50 z-10 shadow-sm border-b border-gray-100">
                      <tr>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Invoice Number</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Customer Name</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Amount Received</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Mode</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">UTR / Reference</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Date</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {todayPayments.length > 0 ? todayPayments.map((payment) => (
                        <tr key={payment.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                          <td className="p-4 font-black text-gray-900">{payment.invoice_number}</td>
                          <td className="p-4 text-sm text-gray-600 font-medium">{payment.customer_name}</td>
                          <td className="p-4 font-black text-gray-900 text-right">{money(payment.amount_received)}</td>
                          <td className="p-4 text-xs font-bold text-gray-600">{payment.payment_mode}</td>
                          <td className="p-4 text-xs font-mono">{payment.utr_reference}</td>
                          <td className="p-4 text-xs text-gray-500">{payment.payment_date ? new Date(payment.payment_date).toLocaleString() : 'N/A'}</td>
                          <td className="p-4">
                            <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase border ${pipelineStatusClass(payment.status, null)}`}>
                              {operatorLabel(payment.status)}
                            </span>
                          </td>
                        </tr>
                      )) : (
                        <tr><td colSpan={7} className="p-8 text-center text-gray-400 italic font-medium">No payments recorded for {periodLabel}.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;

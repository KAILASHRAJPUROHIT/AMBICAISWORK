import { useEffect, useState } from 'react';
import ReportSummaryCard from '../components/ReportSummaryCard';
import { getOwnerReport, getHeaders } from '../api/client';
import ConfirmationDialog from '../components/ConfirmationDialog';
import AlertSoundSystem from '../api/AlertSoundSystem';

interface PaymentBifurcation {
  mode: string;
  total: number;
  verified: number;
  unverified: number;
  count: number;
}

const ReportsPage = () => {
  const [reports, setReports] = useState<any[]>([]);
  const [bifurcation, setBifurcation] = useState<PaymentBifurcation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportConfirmOpen, setExportConfirmOpen] = useState(false);
  const [exportType, setExportType] = useState('');

  // Filters State
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [paymentMode, setPaymentMode] = useState('All');
  const [status, setStatus] = useState('All');
  const [customerSearch, setCustomerSearch] = useState('');
  const [billNumberSearch, setBillNumberSearch] = useState('');
  const [minAmount, setMinAmount] = useState<number | ''>('');
  const [maxAmount, setMaxAmount] = useState<number | ''>('');
  const [verificationState, setVerificationState] = useState('All'); // Verified / Pending / Risk

  const API_BASE = window.location.origin;

  const money = (v: number) => `₹${Number(v).toLocaleString('en-IN')}`;

  const handleExport = (type: string) => {
    setExportType(type);
    setExportConfirmOpen(true);
    AlertSoundSystem.playWarning();
  };

  const executeExport = () => {
    console.log(`Exporting as ${exportType} with current filters...`);
    setExportConfirmOpen(false);
    // Real export logic here
  };

  const clearFilters = () => {
    setStartDate('');
    setEndDate('');
    setPaymentMode('All');
    setStatus('All');
    setCustomerSearch('');
    setBillNumberSearch('');
    setMinAmount('');
    setMaxAmount('');
    setVerificationState('All');
  };

  const fetchReports = async () => {
    try {
      setLoading(true);

      // Build query string
      const params = new URLSearchParams();
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);
      if (status !== 'All') params.append('status', status);
      if (customerSearch) params.append('customer', customerSearch);
      if (billNumberSearch) params.append('bill_number', billNumberSearch);
      if (minAmount !== '') params.append('min_amount', minAmount.toString());
      if (maxAmount !== '') params.append('max_amount', maxAmount.toString());

      const [liveReport, bifData] = await Promise.all([
        getOwnerReport(),
        fetch(`${API_BASE}/api/reports/payment-bifurcation?${params.toString()}`, { headers: getHeaders() }).then(res => {
          if (!res.ok) throw new Error("Failed to fetch bifurcation data");
          return res.json();
        })
      ]);
      
      const summary = liveReport.daily_summary;
      
      // Filter bifurcation on client-side for modes that are purely aggregated
      let filteredBifData = bifData;
      if (paymentMode !== 'All') {
          filteredBifData = filteredBifData.filter((b: PaymentBifurcation) => b.mode.toUpperCase() === paymentMode.toUpperCase());
      }
      
      if (verificationState !== 'All') {
          filteredBifData = filteredBifData.map((b: PaymentBifurcation) => {
              if (verificationState === 'Verified') {
                  return { ...b, unverified: 0, total: b.verified };
              } else if (verificationState === 'Pending') {
                  return { ...b, verified: 0, total: b.unverified };
              } else if (verificationState === 'Risk') {
                   // Just an example, assuming risk is unverified for now
                  return { ...b, verified: 0, total: b.unverified };
              }
              return b;
          }).filter((b: PaymentBifurcation) => b.total > 0);
      }

      if (summary && summary.processed_count > 0) {
          const mappedReport = {
            id: `R-LIVE-${summary.generated_at.split('T')[0]}`,
            title: `Daily Summary - ${summary.generated_at.split('T')[0]}`,
            date: summary.generated_at.split('T')[0],
            totalTransactions: summary.processed_count,
            totalAmount: filteredBifData.reduce((acc: number, curr: any) => acc + curr.total, 0),
            reconciliationRate: summary.processed_count > 0 
              ? `${((summary.resolved_reviews / summary.processed_count) * 100).toFixed(1)}%`
              : '0%'
          };
          setReports([mappedReport]);
      } else {
          setReports([]);
      }
      setBifurcation(filteredBifData);
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch reports:', err);
      setError(err.message || 'API connection failed');
    } finally {
      setLoading(false);
    }
  };

  // Debounce fetching to avoid excessive API calls while typing
  useEffect(() => {
    const handler = setTimeout(() => {
      fetchReports();
    }, 500);
    return () => clearTimeout(handler);
  }, [startDate, endDate, status, customerSearch, billNumberSearch, minAmount, maxAmount, paymentMode, verificationState]);

  if (error) return (
    <div className="m-8 p-12 bg-red-50 border-2 border-red-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-red-600 mb-2">Reports Engine Offline</h2>
      <p className="text-red-500 font-bold">{error}</p>
    </div>
  );

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10 flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Audit Reports</h1>
          <p className="mt-2 text-lg text-gray-600 font-medium">Payment-wise bifurcation and operational summaries.</p>
        </div>
        <div className="flex space-x-4">
           <button 
             onClick={() => handleExport('PDF')}
             className="px-6 py-2 bg-white border border-gray-200 rounded-xl font-bold text-xs uppercase hover:bg-gray-50 transition-colors"
           >
             Export PDF
           </button>
           <button 
             onClick={() => handleExport('EXCEL')}
             className="px-6 py-2 bg-white border border-gray-200 rounded-xl font-bold text-xs uppercase hover:bg-gray-50 transition-colors"
           >
             Export Excel
           </button>
        </div>
      </header>

      {/* Filters Bar */}
      <div className="mb-8 bg-white p-6 rounded-3xl shadow-xl border border-gray-100 grid grid-cols-1 md:grid-cols-4 lg:grid-cols-5 gap-4 items-end">
         <div>
            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Date Range</label>
            <div className="flex gap-2">
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-2 py-2 font-bold text-xs outline-none" />
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-2 py-2 font-bold text-xs outline-none" />
            </div>
         </div>
         
         <div>
            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Payment Mode</label>
            <select value={paymentMode} onChange={(e) => setPaymentMode(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-xs outline-none">
                {['All', 'Cash', 'UPI', 'IMPS', 'NEFT', 'RTGS', 'Cheque', 'Card', 'Advance'].map(m => <option key={m} value={m}>{m}</option>)}
            </select>
         </div>

         <div>
            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-xs outline-none">
                {['All', 'Green', 'Yellow', 'Orange', 'Red', 'Blue', 'Grey'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
         </div>

         <div>
            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Customer Search</label>
            <input type="text" placeholder="Name..." value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-xs outline-none" />
         </div>

         <div>
            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Bill Number</label>
            <input type="text" placeholder="Bill No..." value={billNumberSearch} onChange={(e) => setBillNumberSearch(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-xs outline-none" />
         </div>

         <div className="flex gap-2">
            <div className="w-1/2">
                <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Min Amt</label>
                <input type="number" placeholder="0" value={minAmount} onChange={(e) => setMinAmount(e.target.value === '' ? '' : Number(e.target.value))} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-2 py-2 font-bold text-xs outline-none" />
            </div>
            <div className="w-1/2">
                <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Max Amt</label>
                <input type="number" placeholder="∞" value={maxAmount} onChange={(e) => setMaxAmount(e.target.value === '' ? '' : Number(e.target.value))} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-2 py-2 font-bold text-xs outline-none" />
            </div>
         </div>

         <div>
            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Verification</label>
            <select value={verificationState} onChange={(e) => setVerificationState(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-xs outline-none">
                {['All', 'Verified', 'Pending', 'Risk'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
         </div>

         <div className="md:col-span-2 lg:col-span-1">
             <button onClick={clearFilters} className="w-full bg-gray-100 hover:bg-gray-200 text-gray-600 font-black py-2 rounded-xl text-xs uppercase tracking-widest transition-all">
                Clear Filters
             </button>
         </div>
      </div>
      
      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-pulse uppercase">
          Generating Reports...
        </div>
      ) : reports.length === 0 && bifurcation.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl uppercase tracking-tighter">
          No reports match current filters.
        </div>
      ) : (
        <div className="space-y-12">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {reports.map((report) => (
              <ReportSummaryCard key={report.id} report={report} />
            ))}
          </div>

          <section>
             <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Payment Mode Bifurcation</h2>
             <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden">
                <table className="w-full text-left border-collapse whitespace-nowrap">
                   <thead>
                      <tr className="bg-gray-50 border-b border-gray-100">
                         <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Mode</th>
                         <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Invoice Count</th>
                         <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Total Amount</th>
                         <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Verified</th>
                         <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Pending/Unverified</th>
                      </tr>
                   </thead>
                   <tbody>
                      {bifurcation.map((item) => (
                         <tr key={item.mode} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                            <td className="p-4 text-xs font-black text-gray-900">{item.mode}</td>
                            <td className="p-4 text-xs font-bold text-gray-500 text-right">{item.count}</td>
                            <td className="p-4 text-xs font-black text-gray-900 text-right">{money(item.total)}</td>
                            <td className="p-4 text-xs font-bold text-green-600 text-right">{money(item.verified)}</td>
                            <td className="p-4 text-xs font-bold text-orange-600 text-right">{money(item.unverified)}</td>
                         </tr>
                      ))}
                      {/* Totals Row */}
                      <tr className="bg-gray-50/50">
                          <td className="p-4 text-xs font-black text-gray-900 uppercase">Totals</td>
                          <td className="p-4 text-xs font-black text-gray-900 text-right">{bifurcation.reduce((a, b) => a + b.count, 0)}</td>
                          <td className="p-4 text-xs font-black text-gray-900 text-right">{money(bifurcation.reduce((a, b) => a + b.total, 0))}</td>
                          <td className="p-4 text-xs font-black text-green-700 text-right">{money(bifurcation.reduce((a, b) => a + b.verified, 0))}</td>
                          <td className="p-4 text-xs font-black text-orange-700 text-right">{money(bifurcation.reduce((a, b) => a + b.unverified, 0))}</td>
                      </tr>
                   </tbody>
                </table>
             </div>
          </section>
        </div>
      )}
      
      {exportConfirmOpen && (
        <ConfirmationDialog 
          isOpen={exportConfirmOpen}
          title={`Export ${exportType}`}
          message={`You are about to export financial data as ${exportType}. All exports are audited. Proceed?`}
          confirmLabel="Approve & Export"
          onConfirm={executeExport}
          onCancel={() => setExportConfirmOpen(false)}
          type="WARNING"
        />
      )}
    </div>
  );
};

export default ReportsPage;

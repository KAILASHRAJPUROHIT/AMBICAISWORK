import { useEffect, useState } from 'react';
import ReportSummaryCard from '../components/ReportSummaryCard';
import { getOwnerReport } from '../api/client';
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

  const API_BASE = window.location.origin;

  const money = (v: number) => `₹${Number(v).toLocaleString('en-IN')}`;

  const handleExport = (type: string) => {
    setExportType(type);
    setExportConfirmOpen(true);
    AlertSoundSystem.playWarning();
  };

  const executeExport = () => {
    console.log(`Exporting as ${exportType}...`);
    setExportConfirmOpen(false);
    // Real export logic here
  };

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [liveReport, bifData] = await Promise.all([
          getOwnerReport(),
          fetch(`${API_BASE}/api/reports/payment-bifurcation`).then(res => res.json())
        ]);
        
        const summary = liveReport.daily_summary || liveReport;
        if (summary.processed_count > 0) {
            const mappedReport = {
              id: `R-LIVE-${summary.generated_at.split('T')[0]}`,
              title: `Daily Summary - ${summary.generated_at.split('T')[0]}`,
              date: summary.generated_at.split('T')[0],
              totalTransactions: summary.processed_count,
              totalAmount: bifData.reduce((acc: number, curr: any) => acc + curr.total, 0),
              reconciliationRate: summary.processed_count > 0 
                ? `${(((summary.resolved_reviews ?? (summary.processed_count - summary.open_reviews)) / summary.processed_count) * 100).toFixed(1)}%`
                : '0%'
            };
            setReports([mappedReport]);
        }
        setBifurcation(bifData);
        setError(null);
      } catch (err: any) {
        console.error('Failed to fetch reports:', err);
        setError(err.message || 'API connection failed');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

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
      
      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-pulse uppercase">
          Generating Reports...
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
                <table className="w-full text-left border-collapse">
                   <thead>
                      <tr className="bg-gray-50 border-b border-gray-100">
                         <th className="p-6 text-[10px] font-black text-gray-400 uppercase">Payment Mode</th>
                         <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-right">Invoice Count</th>
                         <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-right">Total Amount</th>
                         <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-right">Verified</th>
                         <th className="p-6 text-[10px] font-black text-gray-400 uppercase text-right">Pending/Unverified</th>
                      </tr>
                   </thead>
                   <tbody>
                      {bifurcation.map((item) => (
                         <tr key={item.mode} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                            <td className="p-6 font-black text-gray-900">{item.mode}</td>
                            <td className="p-6 font-bold text-gray-500 text-right">{item.count}</td>
                            <td className="p-6 font-black text-gray-900 text-right">{money(item.total)}</td>
                            <td className="p-6 font-bold text-green-600 text-right">{money(item.verified)}</td>
                            <td className="p-6 font-bold text-orange-600 text-right">{money(item.unverified)}</td>
                         </tr>
                      ))}
                   </tbody>
                </table>
             </div>
          </section>
        </div>
      )}

      <ConfirmationDialog 
        isOpen={exportConfirmOpen}
        title="Owner Approval Required"
        message={`This action will generate a detailed ${exportType} report containing sensitive financial data. All export actions are audited. Proceed?`}
        confirmLabel="Approve & Export"
        onConfirm={executeExport}
        onCancel={() => setExportConfirmOpen(false)}
        type="WARNING"
      />
    </div>
  );
};

export default ReportsPage;

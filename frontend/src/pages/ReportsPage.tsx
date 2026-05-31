import { useEffect, useState } from 'react';
import ReportSummaryCard from '../components/ReportSummaryCard';
import { getOwnerReport } from '../api/client';

const ReportsPage = () => {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const liveReport = await getOwnerReport();
        
        const summary = liveReport.daily_summary;
        if (summary.processed_count > 0) {
            const mappedReport = {
              id: `R-LIVE-${summary.generated_at.split('T')[0]}`,
              title: `Daily Summary - ${summary.generated_at.split('T')[0]}`,
              date: summary.generated_at.split('T')[0],
              totalTransactions: summary.processed_count,
              totalAmount: 0, // Could be enhanced to show total sale
              reconciliationRate: summary.processed_count > 0 
                ? `${((summary.resolved_reviews / summary.processed_count) * 100).toFixed(1)}%`
                : '0%'
            };
            setReports([mappedReport]);
        } else {
            setReports([]);
        }
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
      <header className="mb-10">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Audit Reports</h1>
        <p className="mt-2 text-lg text-gray-600 font-medium">Daily generated summaries from Prime and Bank data.</p>
      </header>
      
      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-pulse uppercase">
          Generating Reports...
        </div>
      ) : reports.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl">
          No reports generated for current period.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {reports.map((report) => (
            <ReportSummaryCard key={report.id} report={report} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ReportsPage;

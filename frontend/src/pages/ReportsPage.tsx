import { useEffect, useState } from 'react';
import ReportSummaryCard from '../components/ReportSummaryCard';
import { mockReports } from '../mockApi';
import { getOwnerReport } from '../api/client';
import type { ReportSummary } from '../mockApi';

const ReportsPage = () => {
  const [reports, setReports] = useState<ReportSummary[]>(mockReports);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const liveReport = await getOwnerReport();
        
        // Map backend report to frontend ReportSummary
        // The backend returns an OwnerReport object with daily_summary and escalations
        const summary = liveReport.daily_summary;
        const mappedReport: ReportSummary = {
          id: `R-LIVE-${summary.generated_at.split('T')[0]}`,
          title: `Daily Summary - ${summary.generated_at.split('T')[0]} (Live)`,
          date: summary.generated_at.split('T')[0],
          totalTransactions: summary.processed_count,
          totalAmount: 0, // Backend daily summary doesn't have total amount yet
          reconciliationRate: `${((summary.resolved_reviews / summary.processed_count) * 100).toFixed(1)}%`
        };

        if (mappedReport) setReports([mappedReport, ...mockReports]);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch reports:', err);
        setError('Using mock data: Backend API unreachable');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  return (
    <div className="reports-page">
      <h1>Daily Audit Reports</h1>
      
      {loading && <div className="loading-indicator">Loading live reports...</div>}
      {error && <div className="error-message">{error}</div>}

      <div className="reports-grid">
        {reports.map((report) => (
          <ReportSummaryCard key={report.id} report={report} />
        ))}
      </div>
    </div>
  );
};

export default ReportsPage;

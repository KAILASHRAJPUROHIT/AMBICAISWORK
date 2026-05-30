import ReportSummaryCard from '../components/ReportSummaryCard';
import { mockReports } from '../mockApi';

const ReportsPage = () => {
  return (
    <div className="reports-page">
      <h1>Daily Audit Reports</h1>
      <div className="reports-grid">
        {mockReports.map((report) => (
          <ReportSummaryCard key={report.id} report={report} />
        ))}
      </div>
    </div>
  );
};

export default ReportsPage;

import type { ReportSummary } from '../mockApi';

interface ReportSummaryCardProps {
  report: ReportSummary;
}

const ReportSummaryCard = ({ report }: ReportSummaryCardProps) => {
  return (
    <div className="report-card">
      <h3>{report.title}</h3>
      <p>Date: {report.date}</p>
      <div className="report-details">
        <div>
          <span>Transactions:</span>
          <strong>{report.totalTransactions}</strong>
        </div>
        <div>
          <span>Total Amount:</span>
          <strong>₹{report.totalAmount.toLocaleString()}</strong>
        </div>
        <div>
          <span>Accuracy:</span>
          <strong>{report.reconciliationRate}</strong>
        </div>
      </div>
    </div>
  );
};

export default ReportSummaryCard;

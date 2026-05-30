import StatCard from '../components/StatCard';
import ReviewTable from '../components/ReviewTable';
import EscalationTable from '../components/EscalationTable';
import { mockStats, mockReviews, mockEscalations } from '../mockApi';

const DashboardPage = () => {
  return (
    <div className="dashboard-page">
      <h1>Payment Auditor Dashboard</h1>
      
      <div className="stats-grid">
        {mockStats.map((stat, index) => (
          <StatCard key={index} {...stat} />
        ))}
      </div>

      <section>
        <h2>Recent Reviews</h2>
        <ReviewTable items={mockReviews.slice(0, 3)} />
      </section>

      <section>
        <h2>Recent Escalations</h2>
        <EscalationTable items={mockEscalations.slice(0, 2)} />
      </section>
    </div>
  );
};

export default DashboardPage;

import { useEffect, useState } from 'react';
import StatCard from '../components/StatCard';
import ReviewTable from '../components/ReviewTable';
import EscalationTable from '../components/EscalationTable';
import { mockStats, mockReviews, mockEscalations } from '../mockApi';
import { getOpenReviews, getOpenEscalations } from '../api/client';
import type { ReviewItem, EscalationItem } from '../mockApi';

const DashboardPage = () => {
  const [reviews, setReviews] = useState<ReviewItem[]>(mockReviews);
  const [escalations, setEscalations] = useState<EscalationItem[]>(mockEscalations);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [liveReviews, liveEscalations] = await Promise.all([
          getOpenReviews(),
          getOpenEscalations()
        ]);

        // Map backend reviews to frontend ReviewItem
        const mappedReviews: ReviewItem[] = liveReviews.map((r: any) => ({
          id: r.review_id,
          date: r.created_at.split('T')[0],
          amount: 0, // Backend summary doesn't have amount yet
          source: r.entity_type,
          reason: r.reason,
          status: r.status === 'OPEN' ? 'Pending' : 'Flagged'
        }));

        // Map backend escalations to frontend EscalationItem
        const mappedEscalations: EscalationItem[] = liveEscalations.map((e: any) => ({
          id: e.escalation_id,
          date: e.created_at.split('T')[0],
          amount: 0, // Backend summary doesn't have amount yet
          source: 'System',
          urgency: e.severity === 'critical' ? 'High' : e.severity === 'high' ? 'Medium' : 'Low',
          reason: e.escalation_reason
        }));

        if (mappedReviews.length > 0) setReviews(mappedReviews);
        if (mappedEscalations.length > 0) setEscalations(mappedEscalations);
        
        setError(null);
      } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
        setError('Using mock data: Backend API unreachable');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  return (
    <div className="dashboard-page">
      <h1>Payment Auditor Dashboard</h1>
      
      {loading && <div className="loading-indicator">Loading live data...</div>}
      {error && <div className="error-message">{error}</div>}

      <div className="stats-grid">
        {mockStats.map((stat, index) => (
          <StatCard key={index} {...stat} />
        ))}
      </div>

      <section>
        <h2>Recent Reviews</h2>
        <ReviewTable items={reviews.slice(0, 3)} />
      </section>

      <section>
        <h2>Recent Escalations</h2>
        <EscalationTable items={escalations.slice(0, 2)} />
      </section>
    </div>
  );
};

export default DashboardPage;

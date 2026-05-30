import { useEffect, useState } from 'react';
import EscalationTable from '../components/EscalationTable';
import { mockEscalations } from '../mockApi';
import { getOpenEscalations } from '../api/client';
import type { EscalationItem } from '../mockApi';

const EscalationsPage = () => {
  const [escalations, setEscalations] = useState<EscalationItem[]>(mockEscalations);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const liveEscalations = await getOpenEscalations();
        const mappedEscalations: EscalationItem[] = liveEscalations.map((e: any) => ({
          id: e.escalation_id,
          date: e.created_at.split('T')[0],
          amount: 0,
          source: 'System',
          urgency: e.severity === 'critical' ? 'High' : e.severity === 'high' ? 'Medium' : 'Low',
          reason: e.escalation_reason
        }));

        setEscalations(mappedEscalations);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch escalations:', err);
        setError('Using mock data: Backend API unreachable');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  return (
    <div className="escalations-page">
      <h1>Escalations</h1>
      <p>High-priority mismatches and issues requiring immediate attention.</p>
      
      {loading && <div className="loading-indicator">Loading live escalations...</div>}
      {error && <div className="error-message">{error}</div>}

      <EscalationTable items={escalations} />
    </div>
  );
};

export default EscalationsPage;

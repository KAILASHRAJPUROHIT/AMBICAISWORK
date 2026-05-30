import EscalationTable from '../components/EscalationTable';
import { mockEscalations } from '../mockApi';

const EscalationsPage = () => {
  return (
    <div className="escalations-page">
      <h1>Escalations</h1>
      <p>High-priority mismatches and issues requiring immediate attention.</p>
      <EscalationTable items={mockEscalations} />
    </div>
  );
};

export default EscalationsPage;

import type { EscalationItem } from '../mockApi';

interface EscalationTableProps {
  items: EscalationItem[];
}

const EscalationTable = ({ items }: EscalationTableProps) => {
  return (
    <div className="table-container">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Amount</th>
            <th>Source</th>
            <th>Urgency</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.date}</td>
              <td>₹{item.amount.toLocaleString()}</td>
              <td>{item.source}</td>
              <td>
                <span className={`urgency-badge ${item.urgency.toLowerCase()}`}>
                  {item.urgency}
                </span>
              </td>
              <td>{item.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default EscalationTable;

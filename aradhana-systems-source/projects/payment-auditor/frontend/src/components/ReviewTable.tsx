import type { ReviewItem } from '../mockApi';

interface ReviewTableProps {
  items: ReviewItem[];
}

const ReviewTable = ({ items }: ReviewTableProps) => {
  return (
    <div className="table-container">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Amount</th>
            <th>Source</th>
            <th>Reason</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.date}</td>
              <td>₹{item.amount.toLocaleString()}</td>
              <td>{item.source}</td>
              <td>{item.reason}</td>
              <td>
                <span className={`status-badge ${item.status.toLowerCase()}`}>
                  {item.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ReviewTable;

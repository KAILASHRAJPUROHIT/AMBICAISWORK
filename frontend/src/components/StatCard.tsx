interface StatCardProps {
  label: string;
  value: string | number;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
}

const StatCard = ({ label, value, change, trend }: StatCardProps) => {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {change && (
        <div className={`stat-change ${trend}`}>
          {change} {trend === 'up' ? '↑' : trend === 'down' ? '↓' : ''}
        </div>
      )}
    </div>
  );
};

export default StatCard;

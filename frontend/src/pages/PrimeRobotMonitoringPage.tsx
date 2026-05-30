import React, { useState, useEffect } from 'react';
import PrimeRobotStatusCard from '../components/PrimeRobotStatusCard';
import { mockPrimeRobotStatus, mockPrimeRobotStatusFailed } from '../mockPrimeRobotData';
import type { PrimeRobotStatus } from '../mockPrimeRobotData';
import '../Reconciliation.css'; // Import shared styles

const PrimeRobotMonitoringPage: React.FC = () => {
  const [robotStatus, setRobotStatus] = useState<PrimeRobotStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Simulate fetching data
    const fetchData = async () => {
      setLoading(true);
      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Simulate success or failure
      const isFailed = Math.random() > 0.5; // 50% chance to show a failed status
      if (isFailed) {
        setRobotStatus(mockPrimeRobotStatusFailed);
        setError('Simulated error: Robot encountered an issue during last run.');
      } else {
        setRobotStatus(mockPrimeRobotStatus);
        setError(null);
      }
      setLoading(false);
    };

    fetchData();
    // Refresh status every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="prime-robot-monitoring-page">
      <h1>Prime ERP Robot Monitoring</h1>
      <p>Real-time status and activity of the Prime ERP data extraction robot.</p>
      <div className="status-cards-container">
        <PrimeRobotStatusCard status={robotStatus} loading={loading} error={error} />
        {/* Potentially add more PrimeRobotStatusCard components for multiple robots or different aspects */}
      </div>
    </div>
  );
};

export default PrimeRobotMonitoringPage;

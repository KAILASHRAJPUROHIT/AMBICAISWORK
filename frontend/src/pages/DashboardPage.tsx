import React from 'react';
import StatCard from '../components/StatCard';
import { mockDashboardStats } from '../mockDashboardData';
import type { DashboardStats } from '../mockDashboardData';
import '../Dashboard.css';

const DashboardPage: React.FC = () => {
  const statsData: DashboardStats = mockDashboardStats;

  // Helper function to format currency
  const formatCurrency = (amount: number) => {
    return `₹${amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  // Helper function to format percentage
  const formatPercentage = (value: number) => {
    return `${value.toFixed(1)}%`;
  };

  const statCards = [
    { label: 'Total Bills Today', value: statsData.totalBillsToday },
    { label: 'Verified', value: statsData.verified },
    { label: 'Pending Review', value: statsData.pendingReview },
    { label: 'Delivered Before Payment', value: statsData.deliveredBeforePayment },
    { label: 'Cheque Pending', value: statsData.chequePending },
    { label: 'Escalated', value: statsData.escalated },
    { label: 'Total Collection', value: formatCurrency(statsData.totalCollection) },
    { label: 'Match Accuracy', value: formatPercentage(statsData.matchAccuracy) },
  ];

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Dashboard Overview</h1>
        <p className="mt-2 text-lg text-gray-600">Real-time status of payment reconciliation and audit tasks.</p>
      </header>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {statCards.map((stat, index) => (
          <StatCard key={index} label={stat.label} value={stat.value} />
        ))}
      </div>

      {/* Main Stats Summary Section can go here */}
    </div>
  );
};

export default DashboardPage;

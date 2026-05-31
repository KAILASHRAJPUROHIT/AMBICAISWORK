import React, { useState, useEffect } from 'react';
import StatCard from '../components/StatCard';
import '../Dashboard.css';

interface DashboardStats {
  totalBillsToday: number;
  verified: number;
  pendingReview: number;
  totalCollection: number;
  cashCollection: number;
  bankCollection: number;
  cardCollection: number;
  advanceCollection: number;
  matchAccuracy: number;
}

const DashboardPage: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/prime/dashboard/stats')
      .then(res => res.json())
      .then(setStats)
      .catch(err => console.error("Stats fetch error:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-12 text-center text-gray-500 font-bold text-xl">Loading live dashboard metrics...</div>;
  if (!stats) return <div className="p-12 text-center text-red-500 font-bold text-xl">Failed to load dashboard data. Ensure backend is running and reports are imported.</div>;

  const summaryCards = [
    { label: "Total Bills Today", value: stats.totalBillsToday },
    { label: "Verified", value: stats.verified },
    { label: "Pending Review", value: stats.pendingReview },
    { label: "Collection Accuracy", value: `${stats.matchAccuracy}%` },
  ];

  const collectionCards = [
    { label: "Total Sale", value: `₹${stats.totalCollection.toLocaleString()}` },
    { label: "Cash", value: `₹${stats.cashCollection.toLocaleString()}` },
    { label: "Bank", value: `₹${stats.bankCollection.toLocaleString()}` },
    { label: "Card", value: `₹${stats.cardCollection.toLocaleString()}` },
    { label: "Advance", value: `₹${stats.advanceCollection.toLocaleString()}` },
  ];

  return (
    <div className="p-8 bg-gray-50 min-h-screen font-sans">
      <header className="mb-12">
        <h1 className="text-4xl font-black text-gray-900 tracking-tight">Prime Operations Live</h1>
        <p className="mt-2 text-lg text-gray-600">Real-time status of payment reconciliation from imported reports.</p>
      </header>
      
      <section className="mb-16">
        <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Execution Summary</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {summaryCards.map((stat, index) => (
            <StatCard key={index} label={stat.label} value={stat.value} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">Collection Breakdown</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {collectionCards.map((stat, index) => (
            <div key={index} className="bg-white p-8 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-all duration-300">
               <p className="text-[10px] font-black text-gray-400 uppercase mb-3 tracking-tighter">{stat.label}</p>
               <p className="text-2xl font-black text-gray-900">{stat.value}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default DashboardPage;

import React from 'react';

interface StatCardProps {
  label: string;
  value: string | number;
}

const StatCard: React.FC<StatCardProps> = ({ label, value }) => {
  return (
    <div className="bg-white p-8 rounded-2xl shadow-sm border border-gray-100 flex flex-col items-start space-y-4 hover:shadow-md transition-shadow duration-300">
      <div className="text-xs font-bold text-gray-400 uppercase tracking-widest">{label}</div>
      <div className="text-4xl font-black text-gray-900">{value}</div>
    </div>
  );
};

export default StatCard;

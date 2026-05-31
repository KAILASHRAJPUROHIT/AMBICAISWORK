import React, { useState, useEffect } from 'react';
import '../Reconciliation.css'; 

const PrimeRobotMonitoringPage: React.FC = () => {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Prime Robot automation is currently disabled in favor of manual reports.
    setLoading(false);
  }, []);

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Robot Monitoring</h1>
        <p className="mt-2 text-lg text-gray-600 font-medium">Status of background Prime automation tasks.</p>
      </header>
      
      <div className="bg-white p-20 text-center rounded-3xl border border-gray-100 shadow-sm">
        <p className="text-orange-600 text-2xl font-black mb-2 tracking-tight uppercase">Robotic Extraction Paused</p>
        <p className="text-gray-400 font-medium max-w-lg mx-auto">
          The system is currently operating in <b>Manual Report Mode</b>. Automatic bill-by-bill extraction is inactive.
          Please use the <i>Prime Extraction Review</i> section to monitor imported data.
        </p>
      </div>
    </div>
  );
};

export default PrimeRobotMonitoringPage;

import React, { useState, useEffect } from 'react';
import { getHeaders } from '../api/client';

interface HealthData {
  status: string;
  database: string;
  services: {
    email_poller: any;
    sms_poller: any;
    pdf_ingestion: any;
  };
  timestamp: string;
}

const SystemHealthPage: React.FC = () => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = () => {
    setLoading(true);
    fetch(`${window.location.origin}/api/system/health`, { headers: getHeaders() })
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch system health');
        return res.json();
      })
      .then(setHealth)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000); // Auto refresh every 30s
    return () => clearInterval(interval);
  }, []);

  if (loading && !health) return <div className="p-20 text-center font-black animate-pulse">DIAGNOSING SYSTEM...</div>;
  if (error) return <div className="p-20 text-center text-red-600 font-black">OFFLINE: {error}</div>;

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10 flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-black text-gray-900 tracking-tight">SYSTEM HEALTH</h1>
          <p className="text-gray-500 font-bold uppercase tracking-widest text-xs">Live Infrastructure Diagnostics</p>
        </div>
        <div className={`px-6 py-2 rounded-full font-black text-white ${health?.status === 'online' ? 'bg-green-600' : 'bg-red-600'}`}>
          {health?.status.toUpperCase()}
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {/* Database Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border-2 border-gray-100">
          <h2 className="text-xl font-black mb-4 flex items-center">
            <span className="mr-2">🗄️</span> DATABASE
          </h2>
          <div className="flex justify-between items-center">
            <span className="text-gray-500 font-bold">Connectivity</span>
            <span className={`font-black ${health?.database === 'connected' ? 'text-green-600' : 'text-red-600'}`}>
              {health?.database.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Email Poller Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border-2 border-gray-100">
          <h2 className="text-xl font-black mb-4 flex items-center">
            <span className="mr-2">📧</span> EMAIL POLLER
          </h2>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-gray-500 font-bold">Status</span>
              <span className={`font-black ${health?.services.email_poller.is_running ? 'text-green-600' : 'text-red-600'}`}>
                {health?.services.email_poller.is_running ? 'RUNNING' : 'STOPPED'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 font-bold">Last Sync</span>
              <span className="font-mono text-sm">{health?.services.email_poller.last_sync || 'Never'}</span>
            </div>
          </div>
        </div>

        {/* SMS Poller Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border-2 border-gray-100">
          <h2 className="text-xl font-black mb-4 flex items-center">
            <span className="mr-2">📱</span> SMS RELAY
          </h2>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-gray-500 font-bold">Status</span>
              <span className={`font-black ${health?.services.sms_poller.is_running ? 'text-green-600' : 'text-red-600'}`}>
                {health?.services.sms_poller.is_running ? 'ACTIVE' : 'INACTIVE'}
              </span>
            </div>
          </div>
        </div>

        {/* PDF Ingestion Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border-2 border-gray-100">
          <h2 className="text-xl font-black mb-4 flex items-center">
            <span className="mr-2">📄</span> PDF INGESTION
          </h2>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-gray-500 font-bold">Watcher</span>
              <span className={`font-black ${health?.services.pdf_ingestion.is_running ? 'text-green-600' : 'text-red-600'}`}>
                {health?.services.pdf_ingestion.is_running ? 'LISTENING' : 'OFFLINE'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 font-bold">Queue</span>
              <span className="font-black text-blue-600">{health?.services.pdf_ingestion.queue_size || 0} ITEMS</span>
            </div>
          </div>
        </div>
      </div>

      <footer className="mt-12 text-center text-gray-400 font-medium text-xs uppercase tracking-widest">
        Last Refreshed: {new Date(health?.timestamp || '').toLocaleString()}
      </footer>
    </div>
  );
};

export default SystemHealthPage;

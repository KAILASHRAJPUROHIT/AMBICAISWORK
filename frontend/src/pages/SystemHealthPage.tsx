import React, { useState, useEffect } from 'react';
import { getHeaders } from '../api/client';

interface ServiceStatus {
  status: string;
  last_polled_at: string | null;
  event_count: number;
  error: string | null;
}

interface HealthData {
  status: string;
  database: string;
  services: {
    invoice_watcher: ServiceStatus;
    bank_email_poller: ServiceStatus;
    android_sms_relay: ServiceStatus;
  };
  timestamp: string;
}

const formatRelativeTime = (isoString: string | null) => {
  if (!isoString) return 'Never';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);

  if (diffSec < 60) return 'Just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHr < 24) return `${diffHr} hr ago`;
  return date.toLocaleDateString();
};

const SystemHealthPage: React.FC = () => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = () => {
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

  if (loading && !health) return <div className="p-20 text-center font-black animate-pulse uppercase tracking-widest text-gray-400">Diagnosing System Infrastructure...</div>;
  if (error) return <div className="p-20 text-center text-red-600 font-black uppercase tracking-tighter">Diagnostic Link Offline: {error}</div>;

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10 flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-black text-gray-900 tracking-tight">SYSTEM HEALTH</h1>
          <p className="text-gray-500 font-bold uppercase tracking-widest text-xs">Live Infrastructure Diagnostics</p>
        </div>
        <div className={`px-6 py-2 rounded-full font-black text-white shadow-lg ${health?.status === 'online' ? 'bg-green-600' : 'bg-red-600'}`}>
          {health?.status.toUpperCase()}
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {/* Database Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border border-gray-100">
          <h2 className="text-xl font-black mb-6 flex items-center">
            <span className="mr-3 text-2xl">🗄️</span> DATABASE
          </h2>
          <div className="flex justify-between items-center">
            <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Connectivity</span>
            <span className={`font-black ${health?.database === 'connected' ? 'text-green-600' : 'text-red-600'}`}>
              {health?.database.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Invoice Watcher Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border border-gray-100">
          <h2 className="text-xl font-black mb-6 flex items-center">
            <span className="mr-3 text-2xl">📄</span> INVOICE WATCHER
          </h2>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Status</span>
              <span className={`font-black ${health?.services.invoice_watcher.status === 'RUNNING' ? 'text-green-600' : 'text-red-600'}`}>
                {health?.services.invoice_watcher.status}
              </span>
            </div>
            <div className="flex justify-between items-center" title={health?.services.invoice_watcher.last_polled_at || 'Never'}>
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Last Polled</span>
              <span className="font-bold text-gray-900">{formatRelativeTime(health?.services.invoice_watcher.last_polled_at || null)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Processed</span>
              <span className="font-bold text-blue-600">{health?.services.invoice_watcher.event_count} FILES</span>
            </div>
          </div>
        </div>

        {/* Email Poller Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border border-gray-100">
          <h2 className="text-xl font-black mb-6 flex items-center">
            <span className="mr-3 text-2xl">📧</span> EMAIL POLLER
          </h2>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Status</span>
              <span className={`font-black ${health?.services.bank_email_poller.status === 'RUNNING' ? 'text-green-600' : 'text-red-600'}`}>
                {health?.services.bank_email_poller.status}
              </span>
            </div>
            <div className="flex justify-between items-center" title={health?.services.bank_email_poller.last_polled_at || 'Never'}>
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Last Polled</span>
              <span className="font-bold text-gray-900">{formatRelativeTime(health?.services.bank_email_poller.last_polled_at || null)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Events Found</span>
              <span className="font-bold text-blue-600">{health?.services.bank_email_poller.event_count} ALERTS</span>
            </div>
          </div>
        </div>

        {/* SMS Relay Card */}
        <div className="bg-white p-8 rounded-3xl shadow-xl border border-gray-100">
          <h2 className="text-xl font-black mb-6 flex items-center">
            <span className="mr-3 text-2xl">📱</span> SMS RELAY
          </h2>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Status</span>
              <span className={`font-black ${health?.services.android_sms_relay.status === 'ACTIVE' ? 'text-green-600' : 'text-red-600'}`}>
                {health?.services.android_sms_relay.status}
              </span>
            </div>
            <div className="flex justify-between items-center" title={health?.services.android_sms_relay.last_polled_at || 'Never'}>
              <span className="text-gray-400 font-black text-[10px] uppercase tracking-widest">Last Polled</span>
              <span className="font-bold text-gray-900">{formatRelativeTime(health?.services.android_sms_relay.last_polled_at || null)}</span>
            </div>
          </div>
        </div>
      </div>

      <footer className="mt-12 text-center text-gray-400 font-medium text-[10px] uppercase tracking-widest">
        Last Full Refresh: {new Date(health?.timestamp || '').toLocaleString()}
      </footer>
    </div>
  );
};

export default SystemHealthPage;

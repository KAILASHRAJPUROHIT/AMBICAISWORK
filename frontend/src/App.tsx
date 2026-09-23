import React, { useState } from 'react';
import BankActivityPage from './pages/BankActivityPage';
import { getNotifierToken, setNotifierToken } from './api/client';

// This dashboard used to trust anyone on the LAN implicitly. Now that it's
// public on the internet, a one-time token entry (stored in localStorage,
// same token the desktop popup uses) replaces that - not a real login
// system, just enough to keep it out of search engines and casual access.
const TokenGate: React.FC<{ onUnlock: () => void }> = ({ onUnlock }) => {
  const [value, setValue] = useState('');
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <form
        onSubmit={(e) => { e.preventDefault(); if (value.trim()) { setNotifierToken(value.trim()); onUnlock(); } }}
        className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-8 shadow-sm"
      >
        <h1 className="mb-1 text-xl font-black text-gray-900">AMBIC DIGITAL Payment Notifier</h1>
        <p className="mb-6 text-sm text-gray-500">Enter the notifier token to continue.</p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Notifier token"
          autoFocus
          className="mb-4 w-full rounded-xl border border-gray-300 px-4 py-3 text-sm"
        />
        <button type="submit" className="w-full rounded-xl bg-blue-700 px-4 py-3 text-sm font-black uppercase text-white">
          Continue
        </button>
      </form>
    </div>
  );
};

const App: React.FC = () => {
  const [unlocked, setUnlocked] = useState(() => Boolean(getNotifierToken()));
  if (!unlocked) return <TokenGate onUnlock={() => setUnlocked(true)} />;
  return <BankActivityPage />;
};

export default App;

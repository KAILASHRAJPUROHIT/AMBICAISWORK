import React, { useEffect, useState } from 'react';
import { 
  getAccountantVerificationQueue, 
  approveAccountantVerification, 
  rejectAccountantVerification, 
  furtherReviewAccountantVerification 
} from '../api/client';

interface AccountantQueueItem {
  id: number;
  invoice_no: string;
  customer_name?: string;
  amount?: number;
  payment_mode?: string;
  proof_status?: string;
  payment_status?: string;
  confidence_level?: string;
  due_at?: string;
  remaining_seconds?: number;
  reason?: string;
  queue_status?: string;
}

const formatCurrency = (value?: number) => {
  if (value === undefined || value === null) return '₹0';
  return `₹${value.toLocaleString('en-IN')}`;
};

const formatDueAt = (value?: string) => {
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatRemaining = (seconds?: number) => {
  if (seconds === undefined || seconds === null) return 'Not Recorded';
  const overdue = seconds < 0;
  const absolute = Math.abs(seconds);
  const hours = Math.floor(absolute / 3600);
  const minutes = Math.floor((absolute % 3600) / 60);
  const label = `${hours}h ${minutes}m`;
  return overdue ? `${label} overdue` : `${label} left`;
};

const EscalationsPage: React.FC = () => {
  const [items, setItems] = useState<AccountantQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [showNoteModal, setShowNoteModal] = useState<{ id: number; type: 'APPROVE' | 'REJECT' | 'FURTHER_REVIEW' } | null>(null);
  const [actionNote, setActionNote] = useState('');

  const fetchQueue = () => {
    setLoading(true);
    getAccountantVerificationQueue()
      .then((data) => {
        setItems(Array.isArray(data) ? data : []);
        setError(null);
      })
      .catch((err) => {
        console.error('Accountant verification queue fetch error:', err);
        setError(err.message || 'Unable to load accountant verification queue.');
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  const handleAction = async () => {
    if (!showNoteModal) return;
    const { id, type } = showNoteModal;
    
    if ((type === 'REJECT' || type === 'FURTHER_REVIEW') && !actionNote.trim()) {
      alert('Action note is required for rejection or further review.');
      return;
    }

    setActionLoading(id);
    try {
      if (type === 'APPROVE') {
        await approveAccountantVerification(id, actionNote);
      } else if (type === 'REJECT') {
        await rejectAccountantVerification(id, actionNote);
      } else if (type === 'FURTHER_REVIEW') {
        await furtherReviewAccountantVerification(id, actionNote);
      }
      setShowNoteModal(null);
      setActionNote('');
      fetchQueue();
    } catch (err: any) {
      alert(`Action failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading && items.length === 0) {
    return (
      <div className="p-12 text-center text-gray-500 font-bold text-xl uppercase tracking-widest animate-pulse">
        Loading accountant verification queue...
      </div>
    );
  }

  return (
    <div className="p-8 bg-gray-50 min-h-screen font-sans">
      <header className="mb-8 flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-black text-red-600 tracking-tight">Accountant Escalations</h1>
          <p className="mt-2 text-lg text-gray-600">Payments requiring accountant verification before closure.</p>
        </div>
        <button 
          onClick={fetchQueue}
          className="bg-white border border-gray-200 px-6 py-2 rounded-xl font-black text-gray-600 hover:bg-gray-100 transition-colors shadow-sm"
        >
          Refresh Queue
        </button>
      </header>

      {error && (
        <div className="mb-8 p-6 bg-red-50 border border-red-200 rounded-2xl">
          <p className="text-red-500 font-bold">{error}</p>
        </div>
      )}

      {items.length === 0 ? (
        <div className="bg-white p-12 text-center rounded-2xl border border-gray-100 shadow-sm">
          <p className="text-green-600 text-2xl font-black mb-2">No accountant verification items.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <p className="text-xs font-black uppercase tracking-widest text-gray-500">Open Queue</p>
            <p className="text-sm font-black text-gray-900">{items.length} items</p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-100 text-gray-500 uppercase text-[11px] tracking-widest">
                <tr>
                  <th className="text-left p-4">Invoice</th>
                  <th className="text-left p-4">Customer</th>
                  <th className="text-right p-4">Amount</th>
                  <th className="text-left p-4">Mode</th>
                  <th className="text-left p-4">Proof</th>
                  <th className="text-left p-4">Payment</th>
                  <th className="text-left p-4">Confidence</th>
                  <th className="text-left p-4">Due</th>
                  <th className="text-left p-4">Timer</th>
                  <th className="text-left p-4">Reason</th>
                  <th className="text-center p-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((item) => (
                  <tr key={item.id} className="align-top hover:bg-gray-50">
                    <td className="p-4 font-black font-mono text-gray-900">{item.invoice_no}</td>
                    <td className="p-4 font-bold text-gray-700">{item.customer_name || 'Not Recorded'}</td>
                    <td className="p-4 text-right font-black text-gray-900">{formatCurrency(item.amount)}</td>
                    <td className="p-4 font-bold text-gray-700">{item.payment_mode || 'Not Recorded'}</td>
                    <td className="p-4">
                      <span className="px-2 py-1 rounded bg-amber-50 text-amber-700 text-[11px] font-black uppercase">
                        {item.proof_status || 'UNKNOWN'}
                      </span>
                    </td>
                    <td className="p-4 font-black text-gray-800">{item.payment_status || 'UNKNOWN'}</td>
                    <td className="p-4 font-black text-gray-800">{item.confidence_level || 'UNKNOWN'}</td>
                    <td className="p-4 font-bold text-gray-700">{formatDueAt(item.due_at)}</td>
                    <td className="p-4 font-black text-gray-800">{formatRemaining(item.remaining_seconds)}</td>
                    <td className="p-4 text-gray-600 max-w-sm">
                      <div className="mb-2">{item.reason || 'Review required.'}</div>
                      {item.queue_status && item.queue_status !== 'OPEN' && (
                        <div className="text-[10px] font-black uppercase bg-gray-100 px-2 py-1 rounded inline-block">
                          Status: {item.queue_status}
                        </div>
                      )}
                    </td>
                    <td className="p-4">
                      {item.queue_status === 'OPEN' ? (
                        <div className="flex flex-col gap-2">
                          <button
                            disabled={actionLoading !== null}
                            onClick={() => setShowNoteModal({ id: item.id, type: 'APPROVE' })}
                            className="bg-green-600 text-white text-[10px] font-black uppercase py-1.5 px-3 rounded-lg hover:bg-green-700 disabled:opacity-50"
                          >
                            Approve
                          </button>
                          <button
                            disabled={actionLoading !== null}
                            onClick={() => setShowNoteModal({ id: item.id, type: 'REJECT' })}
                            className="bg-red-600 text-white text-[10px] font-black uppercase py-1.5 px-3 rounded-lg hover:bg-red-700 disabled:opacity-50"
                          >
                            Reject
                          </button>
                          <button
                            disabled={actionLoading !== null}
                            onClick={() => setShowNoteModal({ id: item.id, type: 'FURTHER_REVIEW' })}
                            className="bg-amber-500 text-white text-[10px] font-black uppercase py-1.5 px-3 rounded-lg hover:bg-amber-600 disabled:opacity-50"
                          >
                            Further Review
                          </button>
                        </div>
                      ) : (
                        <span className="text-gray-400 font-bold text-[10px] uppercase">No Actions</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Note Modal */}
      {showNoteModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
          <div className="bg-white rounded-3xl p-8 max-w-md w-full shadow-2xl">
            <h2 className="text-2xl font-black mb-4">
              {showNoteModal.type === 'APPROVE' && 'Approve Payment'}
              {showNoteModal.type === 'REJECT' && 'Reject Payment'}
              {showNoteModal.type === 'FURTHER_REVIEW' && 'Request Further Review'}
            </h2>
            <p className="text-gray-600 mb-6 font-bold">
              {showNoteModal.type === 'APPROVE' ? 'Optional: Add a note for this approval.' : 'Please provide a reason/note for this action.'}
            </p>
            <textarea
              className="w-full border-2 border-gray-100 rounded-2xl p-4 h-32 focus:border-red-500 outline-none font-bold text-gray-700"
              placeholder="Enter note here..."
              value={actionNote}
              onChange={(e) => setActionNote(e.target.value)}
            />
            <div className="flex gap-4 mt-8">
              <button
                onClick={() => {
                  setShowNoteModal(null);
                  setActionNote('');
                }}
                className="flex-1 bg-gray-100 text-gray-600 font-black py-4 rounded-2xl hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAction}
                className={`flex-1 text-white font-black py-4 rounded-2xl transition-colors ${
                  showNoteModal.type === 'APPROVE' ? 'bg-green-600 hover:bg-green-700' :
                  showNoteModal.type === 'REJECT' ? 'bg-red-600 hover:bg-red-700' : 'bg-amber-500 hover:bg-amber-600'
                }`}
              >
                {actionLoading ? 'Processing...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EscalationsPage;


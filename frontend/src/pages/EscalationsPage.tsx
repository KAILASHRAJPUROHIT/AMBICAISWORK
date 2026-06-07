import React, { useEffect, useState } from 'react';
import { 
  getAccountantVerificationQueue, 
  approveAccountantVerification, 
  rejectAccountantVerification, 
  furtherReviewAccountantVerification,
  openInvoicePdf,
  fetchProofPreview,
  getReconciliationDetail
} from '../api/client';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer';
import type { ReconciliationItem, ReconciliationPaymentEvidence } from '../types';

interface AccountantQueueItem {
  id: number;
  bill_id: number;
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

  // New state for detailed view
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);
  const [detailLoading, setDetailLoading] = useState<number | null>(null);
  const [proofModal, setProofModal] = useState<{ item: ReconciliationItem; payment: ReconciliationPaymentEvidence; rawText: string } | null>(null);

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

  const handleOpenDetail = async (billId: number) => {
    setDetailLoading(billId);
    try {
      const detail = await getReconciliationDetail(billId);
      setSelectedItem(detail);
    } catch (err: any) {
      alert(`Failed to load details: ${err.message}`);
    } finally {
      setDetailLoading(null);
    }
  };

  const handleViewInvoice = (billId: number) => {
    openInvoicePdf(billId).catch(err => {
      console.error('Error opening invoice PDF:', err);
      alert('Error opening PDF. It may not exist on the server.');
    });
  };

  const handleViewProof = (payment: ReconciliationPaymentEvidence) => {
    if (!payment.proofUrl || !selectedItem) {
      alert('Payment proof not recorded.');
      return;
    }
    fetchProofPreview(payment.proofUrl).then(rawText => {
      setProofModal({ item: selectedItem, payment, rawText: rawText || '' });
    }).catch(err => {
      console.error('Error fetching proof preview:', err);
      alert('Error loading proof preview.');
    });
  };

  const handleCopyProof = () => {
    if (!proofModal) return;
    navigator.clipboard.writeText(proofModal.rawText).then(() => {
      alert('Proof text copied to clipboard.');
    });
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
                  <tr key={item.id} className="align-top hover:bg-gray-50 cursor-pointer" onClick={() => handleOpenDetail(item.bill_id)}>
                    <td className="p-4">
                      <div className="font-black font-mono text-gray-900">{item.invoice_no}</div>
                      <button 
                        type="button"
                        onClick={(e) => { e.stopPropagation(); handleViewInvoice(item.bill_id); }}
                        className="text-[10px] font-bold text-blue-600 hover:underline"
                      >
                        View PDF
                      </button>
                    </td>
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
                      {detailLoading === item.bill_id && (
                        <div className="text-[10px] text-blue-500 font-bold animate-pulse">Loading details...</div>
                      )}
                    </td>
                    <td className="p-4" onClick={(e) => e.stopPropagation()}>
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

      {/* Invoice Detail Drawer */}
      {selectedItem && (
        <InvoiceDetailDrawer
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onViewInvoice={() => handleViewInvoice(selectedItem.billId!)}
          onViewProof={handleViewProof}
        />
      )}

      {/* Proof Modal */}
      {proofModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-8 z-[60]" onClick={() => setProofModal(null)}>
          <div className="bg-white rounded-3xl p-8 max-w-3xl w-full shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex justify-between items-start gap-6 mb-6">
              <div>
                <h3 className="text-xl font-black text-gray-900 uppercase">{proofModal.payment.proofLabel || 'Payment Proof'}</h3>
                <p className="text-sm text-gray-500">
                  {proofModal.payment.source || 'Not Recorded'} | {proofModal.payment.timestamp || 'Not Recorded'}
                </p>
              </div>
              <button type="button" onClick={() => setProofModal(null)} className="text-gray-400 hover:text-gray-900 font-bold text-2xl">&times;</button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6 text-sm">
              <div className="rounded-2xl bg-gray-50 p-4 border border-gray-100">
                <p className="text-[10px] font-black uppercase text-gray-400">Source Type</p>
                <p className="font-bold text-gray-900">{proofModal.payment.source || 'Not Recorded'}</p>
              </div>
              <div className="rounded-2xl bg-gray-50 p-4 border border-gray-100">
                <p className="text-[10px] font-black uppercase text-gray-400">Timestamp</p>
                <p className="font-bold text-gray-900">{proofModal.payment.timestamp || 'Not Recorded'}</p>
              </div>
              <div className="rounded-2xl bg-gray-50 p-4 border border-gray-100">
                <p className="text-[10px] font-black uppercase text-gray-400">UTR / Reference</p>
                <p className="font-bold text-gray-900">{proofModal.payment.utrReference || proofModal.payment.reference || 'Not Recorded'}</p>
              </div>
              <div className="rounded-2xl bg-gray-50 p-4 border border-gray-100">
                <p className="text-[10px] font-black uppercase text-gray-400">Amount</p>
                <p className="font-bold text-gray-900">₹{proofModal.payment.amount.toLocaleString('en-IN')}</p>
              </div>
              <div className="rounded-2xl bg-gray-50 p-4 border border-gray-100">
                <p className="text-[10px] font-black uppercase text-gray-400">Linked Bill</p>
                <p className="font-bold text-gray-900">{proofModal.item.billNo}</p>
              </div>
              <div className="rounded-2xl bg-gray-50 p-4 border border-gray-100">
                <p className="text-[10px] font-black uppercase text-gray-400">Linked Customer</p>
                <p className="font-bold text-gray-900">{proofModal.item.customer}</p>
              </div>
            </div>

            <div className="bg-gray-50 p-6 rounded-2xl border border-gray-100 font-mono text-xs whitespace-pre-wrap max-h-96 overflow-y-auto">
              {proofModal.rawText || 'Payment proof not recorded.'}
            </div>
            <div className="mt-8 pt-6 border-t border-gray-100 flex justify-end gap-3">
              <button type="button" onClick={handleCopyProof} className="bg-white border border-gray-200 text-gray-700 px-6 py-3 rounded-xl font-black uppercase tracking-widest hover:bg-gray-50 transition-colors">
                Copy
              </button>
              <button type="button" onClick={() => setProofModal(null)} className="bg-gray-900 text-white px-8 py-3 rounded-xl font-black uppercase tracking-widest hover:bg-black transition-colors">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EscalationsPage;


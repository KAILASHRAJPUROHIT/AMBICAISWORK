import React, { useState } from 'react';
import type { ReconciliationItem, ReconciliationPaymentEvidence } from '../types';
import { approveAccountantVerification, rejectAccountantVerification, furtherReviewAccountantVerification } from '../api/client';
import '../Reconciliation.css';

interface InvoiceDetailDrawerProps {
  item: ReconciliationItem;
  onClose: () => void;
  onViewInvoice: (item: ReconciliationItem) => void;
  onViewProof: (payment: ReconciliationPaymentEvidence) => void;
}

const formatDateTime = (value?: string | null) => {
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  return date.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const missing = (value?: string | null) => value || 'Not Recorded';

const formatInvoiceTimestamp = (item: ReconciliationItem) => {
  const value = item.invoiceTimestamp || item.invoiceGeneratedAt || item.invoiceDate;
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  const dateText = date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  if (!item.invoiceTimeRecorded) return `${dateText}, Time Not Recorded`;
  return formatDateTime(value);
};

const InvoiceDetailDrawer: React.FC<InvoiceDetailDrawerProps> = ({ item, onClose, onViewInvoice, onViewProof }) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionNote, setActionNote] = useState('');
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const needsAccountantReview = item.hasSpecialPaymentFlag || (item.status && typeof item.status === 'string' && item.status.toUpperCase().includes('ACCOUNTANT'));

  const handleAction = async (actionType: 'approve' | 'reject' | 'furtherReview') => {
    if ((actionType === 'reject' || actionType === 'furtherReview') && !actionNote.trim()) {
      setActionError('Action note is required for Reject and Further Review.');
      setActionMessage(null);
      return;
    }
    
    if (!item.billId) {
      setActionError('Cannot perform action: Bill ID is missing.');
      return;
    }

    setIsSubmitting(true);
    setActionError(null);
    setActionMessage(null);

    try {
      if (actionType === 'approve') {
        await approveAccountantVerification(item.billId, actionNote);
        setActionMessage('Item approved successfully.');
      } else if (actionType === 'reject') {
        await rejectAccountantVerification(item.billId, actionNote);
        setActionMessage('Item rejected successfully.');
      } else if (actionType === 'furtherReview') {
        await furtherReviewAccountantVerification(item.billId, actionNote);
        setActionMessage('Item flagged for further review.');
      }
      setActionNote('');
    } catch (error: any) {
      setActionError(error.message || 'An error occurred while performing the action.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>Reconciliation Audit: {item.billNo}</h2>
          <button className="drawer-close-button" onClick={onClose}>
            &times;
          </button>
        </div>
        <div className="drawer-body">
          <section className="drawer-section">
            <h3>Invoice Record</h3>
            <div className="detail-item">
              <span className="detail-label">Bill No:</span>
              <span className="detail-value font-mono font-bold">{item.billNo}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Customer:</span>
              <span className="detail-value">{item.customer}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Date:</span>
              <span className="detail-value pl-2">{item.invoiceDate ? new Date(item.invoiceDate).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : 'Not Recorded'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Timestamp:</span>
              <span className="detail-value pl-2">{formatInvoiceTimestamp(item)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Amount:</span>
              <span className="detail-value font-bold">₹{item.invoiceAmount.toLocaleString('en-IN')}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Proof:</span>
              <span className="detail-value">
                {item.invoicePdfAvailable && item.invoiceProofUrl && item.billId ? (
                  <button type="button" className="font-bold text-blue-700 underline" onClick={() => onViewInvoice(item)}>
                    View Invoice PDF
                  </button>
                ) : 'Invoice proof not recorded.'}
              </span>
            </div>
          </section>

          <section className="drawer-section">
            <h3>Payment Proof Timeline</h3>
            {item.paymentBreakdown.length === 0 ? (
              <div className="p-4 rounded-2xl bg-gray-50 text-gray-500 font-bold text-sm">
                Payment proof not recorded.
              </div>
            ) : (
              <div className="space-y-3">
                {item.paymentBreakdown.map((payment, index) => (
                  <div key={`${payment.reference || payment.utrReference || payment.mode}-${index}`} className="p-4 rounded-2xl border border-gray-100 bg-gray-50">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-black text-gray-900">₹{payment.amount.toLocaleString('en-IN')}</span>
                      <span className="text-xs font-black uppercase text-gray-400">{payment.mode}</span>
                    </div>
                    <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-gray-600">
                      <span>Timestamp: <b>{formatDateTime(payment.timestamp)}</b></span>
                      <span>UTR/Reference: <b>{missing(payment.utrReference || payment.reference)}</b></span>
                      <span>Evidence Source: <b>{missing(payment.source)}</b></span>
                      <span>
                        Proof:{' '}
                        {payment.proofUrl ? (
                          <button type="button" className="font-bold text-blue-700 underline" onClick={() => onViewProof(payment)}>
                            {payment.proofLabel || 'View Proof'}
                          </button>
                        ) : <b>Payment proof not recorded</b>}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="drawer-section">
            <h3>System Decision</h3>
            <div className="detail-item">
              <span className="detail-label">Matched Amount:</span>
              <span className="detail-value font-bold">₹{item.bankAmount.toLocaleString('en-IN')}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Discrepancy:</span>
              <span className={`detail-value font-bold ${item.difference !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                ₹{item.difference.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Payment Mode:</span>
              <span className="detail-value uppercase">{item.paymentMode}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Status:</span>
              <span className="detail-value font-bold">{item.status}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Confidence:</span>
              <span className="detail-value">{item.matchConfidence}</span>
            </div>
            {item.hasSpecialPaymentFlag && (
              <p className="mt-3 rounded-2xl border border-purple-100 bg-purple-50 p-4 text-sm font-semibold text-purple-800">
                Old gold, advance, customer purchase, or buyback payment requires accountant approval even when amounts match.
              </p>
            )}
          </section>

          {needsAccountantReview && (
            <section className="drawer-section border-t-2 border-dashed border-gray-200 pt-4 mt-4">
              <h3 className="text-lg font-bold text-gray-800 mb-3">Accountant Review Actions</h3>
              
              {actionError && (
                <div className="mb-3 p-3 bg-red-50 text-red-700 rounded border border-red-200 text-sm font-semibold">
                  {actionError}
                </div>
              )}
              {actionMessage && (
                <div className="mb-3 p-3 bg-green-50 text-green-700 rounded border border-green-200 text-sm font-semibold">
                  {actionMessage}
                </div>
              )}

              <div className="mb-4">
                <label htmlFor="actionNote" className="block text-sm font-medium text-gray-700 mb-1">
                  Action Note (Required for Reject / Further Review)
                </label>
                <textarea
                  id="actionNote"
                  rows={2}
                  className="w-full p-2 border border-gray-300 rounded focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Enter reason or comments here..."
                  value={actionNote}
                  onChange={(e) => setActionNote(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => handleAction('approve')}
                  disabled={isSubmitting}
                  className="flex-1 bg-green-600 text-white font-bold py-2 px-4 rounded hover:bg-green-700 disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => handleAction('reject')}
                  disabled={isSubmitting}
                  className="flex-1 bg-red-600 text-white font-bold py-2 px-4 rounded hover:bg-red-700 disabled:opacity-50"
                >
                  Reject
                </button>
                <button
                  type="button"
                  onClick={() => handleAction('furtherReview')}
                  disabled={isSubmitting}
                  className="flex-1 bg-yellow-500 text-white font-bold py-2 px-4 rounded hover:bg-yellow-600 disabled:opacity-50"
                >
                  Further Review
                </button>
              </div>
            </section>
          )}

        </div>
      </div>
    </div>
  );
};

export default InvoiceDetailDrawer;

import React from 'react';
import type { ReconciliationItem, ReconciliationPaymentEvidence } from '../types';
import '../Reconciliation.css';

interface InvoiceDetailDrawerProps {
  item: ReconciliationItem;
  onClose: () => void;
  onViewInvoice: (item: ReconciliationItem) => void;
  onViewProof: (payment: ReconciliationPaymentEvidence) => void;
  showIncorrectDetailsFeedback?: boolean;
  systemReason?: string;
  onAction?: (action: 'APPROVE' | 'REJECT' | 'FURTHER_REVIEW', queueId: number | string) => void;
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

const InvoiceDetailDrawer: React.FC<InvoiceDetailDrawerProps> = ({ item, onClose, onViewInvoice, onViewProof, showIncorrectDetailsFeedback = false, systemReason, onAction }) => {
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
                        {['UPI', 'IMPS', 'NEFT', 'RTGS', 'CARD', 'CHEQUE'].includes((payment.mode || '').toUpperCase()) && payment.proofUrl && payment.proofExists ? (
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
            {systemReason && (
              <div className="detail-item mt-2">
                <span className="detail-label">System Detail:</span>
                <span className="detail-value text-xs text-gray-500 font-mono break-words">{systemReason}</span>
              </div>
            )}
            {item.hasSpecialPaymentFlag && (
              <p className="mt-3 rounded-2xl border border-purple-100 bg-purple-50 p-4 text-sm font-semibold text-purple-800">
                Old gold, advance, customer purchase, or buyback payment requires accountant approval even when amounts match.
              </p>
            )}
          </section>

          {item.queueId != null && item.queueStatus === 'OPEN' && onAction && (
            <section className="drawer-section border-t-4 border-orange-200 pt-6 mt-6">
              <h3 className="text-orange-800 font-black mb-4">Accountant Review Required</h3>
              <div className="flex flex-col gap-3">
                <button
                  type="button"
                  onClick={() => onAction('APPROVE', item.queueId!)}
                  className="rounded-xl bg-green-600 px-5 py-3 text-sm font-black uppercase tracking-widest text-white hover:bg-green-700 w-full"
                >
                  Approve
                </button>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => onAction('REJECT', item.queueId!)}
                    className="rounded-xl bg-red-100 px-5 py-3 text-sm font-black uppercase tracking-widest text-red-700 hover:bg-red-200 flex-1"
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    onClick={() => onAction('FURTHER_REVIEW', item.queueId!)}
                    className="rounded-xl bg-orange-100 px-5 py-3 text-sm font-black uppercase tracking-widest text-orange-700 hover:bg-orange-200 flex-1"
                  >
                    Further Review
                  </button>
                </div>
              </div>
            </section>
          )}

          {showIncorrectDetailsFeedback && (
            <section className="drawer-section">
              <h3>Report Incorrect Details</h3>
              <p className="mb-4 text-sm font-semibold text-gray-600">
                Flag display or evidence issues for software review. This does not edit payment, bill, UTR, date, or reconciliation status.
              </p>
              <div className="space-y-3">
                <label className="block">
                  <span className="detail-label block mb-2">Issue Type</span>
                  <select className="w-full rounded-xl border border-gray-200 bg-white p-3 text-sm font-bold text-gray-700">
                    <option>Wrong UTR shown</option>
                    <option>Wrong timestamp</option>
                    <option>Wrong proof status</option>
                    <option>Wrong payment mode</option>
                    <option>Missing PDF</option>
                    <option>Other</option>
                  </select>
                </label>
                <label className="block">
                  <span className="detail-label block mb-2">Note</span>
                  <textarea
                    className="h-24 w-full rounded-xl border border-gray-200 bg-white p-3 text-sm font-semibold text-gray-700"
                    placeholder="Describe what looks incorrect for software review."
                  />
                </label>
                <button
                  type="button"
                  disabled
                  className="rounded-xl bg-gray-200 px-4 py-3 text-xs font-black uppercase tracking-widest text-gray-500"
                >
                  Feedback capture endpoint pending
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

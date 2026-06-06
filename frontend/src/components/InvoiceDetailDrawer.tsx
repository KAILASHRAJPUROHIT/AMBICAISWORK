import React from 'react';
import type { ReconciliationItem, ReconciliationPaymentEvidence } from '../types';
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

const proofFallbackText = (payment: ReconciliationPaymentEvidence) => {
  if (payment.proofStatus === 'NO_DIGITAL_PROOF') return 'No digital proof / manual cash entry';
  if (payment.proofStatus === 'MISMATCH') return 'Proof amount mismatch';
  if (payment.proofStatus === 'PARTIAL_PROOF') return 'Partial proof';
  return 'Payment proof not recorded';
};

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
                        ) : <b>{proofFallbackText(payment)}</b>}
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
        </div>
      </div>
    </div>
  );
};

export default InvoiceDetailDrawer;

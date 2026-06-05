import React from 'react';
import type { ReconciliationItem } from '../types';
import '../Reconciliation.css';

interface InvoiceDetailDrawerProps {
  item: ReconciliationItem;
  onClose: () => void;
}

const formatMoney = (value: number) => `₹${value.toLocaleString('en-IN')}`;

const formatDateTime = (value?: string | null) => {
  if (!value) return 'Not Recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not Recorded';
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};

const textOrMissing = (value?: string | null) => value || 'Not Recorded';

const InvoiceDetailDrawer: React.FC<InvoiceDetailDrawerProps> = ({ item, onClose }) => {
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
              <span className="detail-value">{formatDateTime(item.invoiceDate)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Time:</span>
              <span className="detail-value">{formatDateTime(item.invoiceGeneratedAt)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Amount:</span>
              <span className="detail-value font-bold">{formatMoney(item.invoiceAmount)}</span>
            </div>
          </section>

          <section className="drawer-section">
            <h3>Payment Timeline</h3>
            {item.paymentBreakdown.length === 0 ? (
              <div className="p-4 rounded-2xl bg-gray-50 text-gray-500 font-bold text-sm">
                No evidence recorded
              </div>
            ) : (
              <div className="space-y-3">
                {item.paymentBreakdown.map((payment, index) => (
                  <div key={`${payment.reference || payment.utrReference || payment.mode}-${index}`} className="p-4 rounded-2xl border border-gray-100 bg-gray-50">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-black text-gray-900">{formatMoney(payment.amount)}</span>
                      <span className="text-xs font-black uppercase text-gray-400">{payment.mode}</span>
                    </div>
                    <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-gray-600">
                      <span>Timestamp: <b>{formatDateTime(payment.timestamp)}</b></span>
                      <span>Reference: <b>{textOrMissing(payment.utrReference || payment.reference)}</b></span>
                      <span>Source: <b>{textOrMissing(payment.source)}</b></span>
                      <span>Evidence: <b>{payment.evidenceLink ? 'Linked' : payment.evidenceAvailable ? 'Recorded' : 'No evidence recorded'}</b></span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="drawer-section">
            <h3>Running Total</h3>
            <div className="detail-item">
              <span className="detail-label">Invoice Amount:</span>
              <span className="detail-value font-bold">{formatMoney(item.invoiceAmount)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Total Received:</span>
              <span className="detail-value font-bold">{formatMoney(item.totalReceived)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Outstanding:</span>
              <span className={`detail-value font-bold ${item.outstanding > 0 ? 'text-red-600' : 'text-green-600'}`}>
                {formatMoney(item.outstanding)}
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Overpaid:</span>
              <span className={`detail-value font-bold ${item.overpaid > 0 ? 'text-orange-600' : 'text-green-600'}`}>
                {formatMoney(item.overpaid)}
              </span>
            </div>
          </section>

          <section className="drawer-section">
            <h3>Status Explanation</h3>
            <div className="detail-item">
              <span className="detail-label">Status:</span>
              <span className="detail-value font-bold">{item.status}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Confidence:</span>
              <span className="detail-value">{item.matchConfidence}</span>
            </div>
            <p className="mt-3 rounded-2xl bg-blue-50 border border-blue-100 p-4 text-sm text-blue-800 font-semibold">
              {item.statusExplanation || 'Review required.'}
            </p>
          </section>

          <section className="drawer-section">
            <h3>Audit Metadata</h3>
            <div className="detail-item">
              <span className="detail-label">Created:</span>
              <span className="detail-value">{formatDateTime(item.createdAt)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Updated:</span>
              <span className="detail-value">{formatDateTime(item.updatedAt)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Verified At:</span>
              <span className="detail-value">{formatDateTime(item.verifiedAt)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Verified By:</span>
              <span className="detail-value">{textOrMissing(item.verifiedBy)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Source System:</span>
              <span className="detail-value">{textOrMissing(item.sourceSystem)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Review Age:</span>
              <span className="detail-value">{textOrMissing(item.reviewAge)}</span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default InvoiceDetailDrawer;

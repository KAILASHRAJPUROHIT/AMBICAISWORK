import React from 'react';
import type { ReconciliationItem } from '../types';
import '../Reconciliation.css'; 

interface InvoiceDetailDrawerProps {
  item: ReconciliationItem;
  onClose: () => void;
}

const InvoiceDetailDrawer: React.FC<InvoiceDetailDrawerProps> = ({ item, onClose }) => {
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>Reconciliation Summary: {item.billNo}</h2>
          <button className="drawer-close-button" onClick={onClose}>
            &times;
          </button>
        </div>
        <div className="drawer-body">
          <section className="drawer-section">
            <h3>Prime Record</h3>
            <div className="detail-item">
              <span className="detail-label">Voucher No:</span>
              <span className="detail-value font-mono font-bold">{item.billNo}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Customer:</span>
              <span className="detail-value">{item.customer}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Invoice Amount:</span>
              <span className="detail-value font-bold">₹{item.invoiceAmount.toLocaleString()}</span>
            </div>
          </section>

          <section className="drawer-section">
            <h3>Bank Evidence</h3>
            <div className="detail-item">
              <span className="detail-label">Matched Amount:</span>
              <span className="detail-value font-bold">₹{item.bankAmount.toLocaleString()}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Discrepancy:</span>
              <span className={`detail-value font-bold ${item.difference !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                ₹{item.difference.toLocaleString()}
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Payment Mode:</span>
              <span className="detail-value uppercase">{item.paymentMode}</span>
            </div>
          </section>

          <section className="drawer-section">
            <h3>System Decision</h3>
            <div className="detail-item">
              <span className="detail-label">Status:</span>
              <span className="detail-value font-bold">{item.status}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Confidence:</span>
              <span className="detail-value">{item.matchConfidence}</span>
            </div>
          </section>
          
          <div className="mt-8 p-6 bg-blue-50 rounded-2xl border border-blue-100">
             <p className="text-sm text-blue-700 leading-relaxed text-center italic">
               Deep-dive view for individual product lines is currently only available via the <b>Prime Extraction Review</b> evidence portal.
             </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InvoiceDetailDrawer;

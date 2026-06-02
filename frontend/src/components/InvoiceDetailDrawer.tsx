import React, { useState } from 'react';
import type { ReconciliationItem } from '../types';
import ConfirmationDialog from './ConfirmationDialog';
import AlertSoundSystem from '../api/AlertSoundSystem';
import '../Reconciliation.css'; 

interface InvoiceDetailDrawerProps {
  item: ReconciliationItem;
  onClose: () => void;
}

const InvoiceDetailDrawer: React.FC<InvoiceDetailDrawerProps> = ({ item, onClose }) => {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmType, setConfirmType] = useState<'VERIFY' | 'REJECT'>('VERIFY');

  const handleAction = (type: 'VERIFY' | 'REJECT') => {
    setConfirmType(type);
    setConfirmOpen(true);
    if (type === 'REJECT') {
        AlertSoundSystem.playWarning();
    }
  };

  const executeAction = async () => {
    // API call would go here
    console.log(`Executing ${confirmType} for ${item.billNo}`);
    setConfirmOpen(false);
    onClose();
  };

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
          
          <div className="mt-8 grid grid-cols-2 gap-4">
             <button 
                onClick={() => handleAction('REJECT')}
                className="p-5 rounded-2xl bg-red-50 text-red-600 font-black uppercase text-xs tracking-widest hover:bg-red-100 transition-all border-2 border-red-100"
             >
                Reject / Escalate
             </button>
             <button 
                onClick={() => handleAction('VERIFY')}
                className="p-5 rounded-2xl bg-green-600 text-white font-black uppercase text-xs tracking-widest hover:bg-green-700 transition-all shadow-lg shadow-green-200"
             >
                Verify & Clear
             </button>
          </div>

          <div className="mt-8 p-6 bg-blue-50 rounded-2xl border border-blue-100">
             <p className="text-sm text-blue-700 leading-relaxed text-center italic">
               Deep-dive view for individual product lines is currently only available via the <b>Prime Extraction Review</b> evidence portal.
             </p>
          </div>
        </div>
      </div>

      <ConfirmationDialog 
        isOpen={confirmOpen}
        title={confirmType === 'VERIFY' ? 'Confirm Clearance' : 'Flag for Review'}
        message={confirmType === 'VERIFY' 
            ? `Are you sure you want to verify and clear Voucher ${item.billNo} for ₹${item.invoiceAmount.toLocaleString()}? This action is immutable.`
            : `Are you sure you want to reject the match for Voucher ${item.billNo}? This will escalate the item to the owner report.`
        }
        confirmLabel={confirmType === 'VERIFY' ? 'Yes, Clear it' : 'Flag Item'}
        onConfirm={executeAction}
        onCancel={() => setConfirmOpen(false)}
        type={confirmType === 'VERIFY' ? 'NORMAL' : 'CRITICAL'}
      />
    </div>
  );
};

export default InvoiceDetailDrawer;

import React, { useState, useEffect } from 'react';
import ReconciliationTable from '../components/ReconciliationTable';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer';
import { getOpenReviews } from '../api/client';
import type { ReconciliationItem } from '../types';

const FORBIDDEN_CONTRACT_VALUES = ['---', 'Review Item', 'REVIEW', 'mock_review_1', 'pay_001', 'bill_002'];

const toAmount = (value: unknown): number => {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : 0;
};

const toConfidence = (value: unknown): ReconciliationItem['matchConfidence'] => {
  const confidence = String(value || '').toLowerCase();
  if (confidence === 'high') return 'High';
  if (confidence === 'low') return 'Low';
  return 'Medium';
};

const toStatus = (value: unknown): ReconciliationItem['status'] => {
  const status = String(value || '').toUpperCase();
  if (['CLEARED', 'VERIFIED', 'PAID', 'GREEN'].includes(status) || value === 'Verified') return 'Verified';
  if (['DELIVERY_APPROVED_BEFORE_PAYMENT', 'APPROVAL_DELIVERY', 'ORANGE'].includes(status) || value === 'Delivered Before Payment') return 'Delivered Before Payment';
  if (['MISMATCH', 'ERROR', 'PAYMENT_TOTAL_MISMATCH', 'FRAUD_RISK', 'RED'].includes(status) || value === 'Risk / Mismatch') return 'Risk / Mismatch';
  if (['CHEQUE_DEPOSITED', 'CHEQUE_CLEARING', 'REALIZING_CHEQUE', 'BLUE'].includes(status) || value === 'Realizing Cheque') return 'Realizing Cheque';
  if (['ADVANCE_PENDING', 'PURPLE'].includes(status) || value === 'Advance Pending') return 'Advance Pending';
  if (['ARCHIVED', 'CLOSED'].includes(status) || value === 'Archived') return 'Archived';
  return 'Pending';
};

const assertRealReviewRow = (row: any) => {
  const serialized = JSON.stringify(row);
  const forbidden = FORBIDDEN_CONTRACT_VALUES.find(value => serialized.includes(value));
  if (forbidden) {
    throw new Error(`Reconciliation contract rejected placeholder/mock value: ${forbidden}`);
  }
  if (!row.bill_no || String(row.bill_no).trim() === '') {
    throw new Error('Reconciliation contract rejected row without bill_no');
  }
};

const normalizeReview = (row: any, idx: number): ReconciliationItem => {
  assertRealReviewRow(row);
  return {
    id: String(row.bill_no || `REC_${idx}`),
    billNo: String(row.bill_no),
    customer: row.customer_name || 'Unknown Customer',
    invoiceAmount: toAmount(row.invoice_amount),
    bankAmount: toAmount(row.bank_amount),
    difference: toAmount(row.difference),
    paymentMode: row.payment_mode || 'UNKNOWN',
    matchConfidence: toConfidence(row.confidence),
    status: toStatus(row.status),
  };
};

const ReconciliationQueuePage: React.FC = () => {
  const [items, setItems] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);

  useEffect(() => {
    getOpenReviews()
      .then(data => {
        setItems(data.map(normalizeReview));
      })
      .catch(err => {
        console.error('Reconciliation fetch error:', err);
        setError(err.message || 'Unable to load reconciliation data.');
      })
      .finally(() => setLoading(false));
  }, []);

  const handleRowClick = (item: ReconciliationItem) => {
    setSelectedItem(item);
  };

  const handleCloseDrawer = () => {
    setSelectedItem(null);
  };

  if (error) return (
    <div className="m-8 p-12 bg-orange-50 border-2 border-orange-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-orange-600 mb-2">Reconciliation Offline</h2>
      <p className="text-orange-500 font-bold">{error}</p>
    </div>
  );

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10 text-center md:text-left">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Live Reconciliation Queue</h1>
        <p className="mt-2 text-lg text-gray-600 font-medium">Direct synchronization with Prime accounting records.</p>
      </header>

      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-bounce uppercase tracking-widest">
          Syncing Records...
        </div>
      ) : items.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl">
          No open reconciliation items
        </div>
      ) : (
        <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
          <ReconciliationTable items={items} onRowClick={handleRowClick} />
        </div>
      )}

      {selectedItem && (
        <InvoiceDetailDrawer item={selectedItem} onClose={handleCloseDrawer} />
      )}
    </div>
  );
};

export default ReconciliationQueuePage;

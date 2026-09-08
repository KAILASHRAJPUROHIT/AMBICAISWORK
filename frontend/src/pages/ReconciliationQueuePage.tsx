import React, { useState, useEffect, useMemo, useCallback } from 'react';
import ReconciliationTable from '../components/ReconciliationTable';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer';
import { getOpenReviewsWithTimeout, openInvoicePdf, fetchProofPreview } from '../api/client';
import type { ReconciliationItem, ReconciliationPaymentEvidence } from '../types';

const FORBIDDEN_CONTRACT_VALUES = ['---', 'Review Item', 'REVIEW', 'mock_review_1', 'pay_001', 'bill_002'];
const SPECIAL_PAYMENT_TOKENS = ['ADVANCE', 'OLD_GOLD_EXCHANGE', 'OLD GOLD', 'CUSTOMER PURCHASE', 'BUYBACK'];

export type ReconciliationSortKey = 'billNo' | 'customer' | 'invoiceDate' | 'invoiceAmount' | 'bankAmount' | 'difference' | 'paymentMode' | 'matchConfidence' | 'status';
export type ReconciliationSortDirection = 'asc' | 'desc';

type DifferenceFilter = '' | 'clear' | 'partial' | 'overpaid' | 'pending';
type SpecialPaymentFilter = '' | 'special' | 'standard';

interface ReconciliationFilters {
  billNo: string;
  customer: string;
  dateFrom: string;
  dateTo: string;
  invoiceMin: string;
  invoiceMax: string;
  bankMin: string;
  bankMax: string;
  differenceType: DifferenceFilter;
  paymentMode: string;
  confidence: string;
  status: string;
  specialFlag: SpecialPaymentFilter;
}

interface ProofModalState {
  item: ReconciliationItem;
  payment: ReconciliationPaymentEvidence;
  rawText: string;
}

const defaultFilters: ReconciliationFilters = {
  billNo: '',
  customer: '',
  dateFrom: '',
  dateTo: '',
  invoiceMin: '',
  invoiceMax: '',
  bankMin: '',
  bankMax: '',
  differenceType: '',
  paymentMode: '',
  confidence: '',
  status: '',
  specialFlag: '',
};

const toAmount = (value: unknown): number => {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : 0;
};

const hasSpecialPaymentMode = (paymentMode: unknown): boolean => {
  const mode = String(paymentMode || '').toUpperCase();
  return SPECIAL_PAYMENT_TOKENS.some(token => mode.includes(token));
};

const toConfidence = (value: unknown, paymentMode: unknown): ReconciliationItem['matchConfidence'] => {
  if (hasSpecialPaymentMode(paymentMode)) return 'Medium';
  const confidence = String(value || '').toLowerCase();
  if (confidence === 'high') return 'High';
  if (confidence === 'low') return 'Low';
  return 'Medium';
};

const toStatus = (value: unknown, paymentMode: unknown): ReconciliationItem['status'] => {
  if (hasSpecialPaymentMode(paymentMode)) return 'ACCOUNTANT APPROVAL REQUIRED';
  const status = String(value || '').toUpperCase();
  if (status === 'ACCOUNTANT APPROVAL REQUIRED') return 'ACCOUNTANT APPROVAL REQUIRED';
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

const normalizePaymentBreakdown = (value: unknown): ReconciliationPaymentEvidence[] => {
  if (!Array.isArray(value)) return [];
  return value.map((payment: any) => ({
    amount: toAmount(payment.amount),
    mode: String(payment.mode || payment.payment_type || 'UNKNOWN'),
    timestamp: payment.timestamp || payment.payment_date || payment.created_at || null,
    utrReference: payment.utr_reference || payment.utrReference || null,
    reference: payment.reference || payment.ref || null,
    source: payment.source || payment.evidence_source || null,
    proofUrl: payment.proof_url || payment.proofUrl || null,
    proofLabel: payment.proof_label || payment.proofLabel || null,
  })).filter(payment => payment.amount > 0 || payment.mode !== 'UNKNOWN' || Boolean(payment.reference || payment.utrReference));
};

const normalizeReview = (row: any, idx: number): ReconciliationItem => {
  assertRealReviewRow(row);
  const paymentMode = row.payment_mode || 'UNKNOWN';
  const specialPayment = Boolean(row.has_special_payment_flag) || hasSpecialPaymentMode(paymentMode);
  return {
    id: String(row.bill_id || row.bill_no || `REC_${idx}`),
    billId: row.bill_id ?? null,
    billNo: String(row.bill_no),
    customer: row.customer_name || 'Unknown Customer',
    invoiceAmount: toAmount(row.invoice_amount),
    bankAmount: toAmount(row.bank_amount),
    difference: toAmount(row.difference),
    paymentMode,
    matchConfidence: toConfidence(row.confidence, paymentMode),
    status: toStatus(row.status, paymentMode),
    invoiceDate: row.invoice_date || null,
    invoiceGeneratedAt: row.invoice_generated_at || null,
    invoiceTimestamp: row.invoice_timestamp || row.invoice_generated_at || row.pdf_mtime || row.file_created_at || row.created_at || row.invoice_date || null,
    invoiceTimestampSource: row.invoice_timestamp_source || null,
    invoiceTimeRecorded: Boolean(row.invoice_time_recorded),
    invoiceProofUrl: row.invoice_pdf_url || row.invoiceProofUrl || null,
    invoicePdfAvailable: Boolean(row.invoice_pdf_available || row.invoice_pdf_url),
    hasSpecialPaymentFlag: specialPayment,
    paymentBreakdown: normalizePaymentBreakdown(row.payment_breakdown),
  };
};

const toDateValue = (value?: string | null): number => {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
};

const getDifferenceType = (item: ReconciliationItem): DifferenceFilter => {
  if (item.bankAmount <= 0) return 'pending';
  if (item.difference < -0.01) return 'overpaid';
  if (Math.abs(item.difference) < 0.01) return 'clear';
  return 'partial';
};

const getComparableValue = (item: ReconciliationItem, key: ReconciliationSortKey): string | number => {
  switch (key) {
    case 'invoiceAmount': return item.invoiceAmount;
    case 'bankAmount': return item.bankAmount;
    case 'difference': return item.difference;
    case 'invoiceDate': return toDateValue(item.invoiceTimestamp || item.invoiceGeneratedAt || item.invoiceDate);
    case 'billNo': return item.billNo;
    case 'customer': return item.customer;
    case 'paymentMode': return item.paymentMode;
    case 'matchConfidence': return item.matchConfidence;
    case 'status': return item.status;
    default: return '';
  }
};

const ReconciliationQueuePage: React.FC = () => {
  const [items, setItems] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);
  const [filters, setFilters] = useState<ReconciliationFilters>(defaultFilters);
  const [sortKey, setSortKey] = useState<ReconciliationSortKey>('invoiceDate');
  const [sortDirection, setSortDirection] = useState<ReconciliationSortDirection>('desc');
  const [proofModal, setProofModal] = useState<ProofModalState | null>(null);

  const fetchReviews = useCallback(() => {
    setLoading(true);
    setError(null);
    getOpenReviewsWithTimeout()
      .then(data => {
        setItems(data.map(normalizeReview));
      })
      .catch(err => {
        console.error('Reconciliation fetch error:', err);
        setError(err.message || 'Unable to load reconciliation data.');
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  const handleRowClick = (item: ReconciliationItem) => {
    setSelectedItem(item);
  };

  const handleViewInvoice = (item: ReconciliationItem) => {
    if (!item.invoiceProofUrl || !item.billId) {
      window.alert('Invoice proof not recorded.');
      return;
    }
    openInvoicePdf(item.billId).catch(err => {
      console.error('Error opening reconciliation invoice PDF:', err);
      window.alert('Error opening PDF. It may not exist on the server.');
    });
  };

  const handleViewProof = (payment: ReconciliationPaymentEvidence) => {
    if (!payment.proofUrl || !selectedItem) {
      window.alert('Payment proof not recorded.');
      return;
    }
    const proofUrl: string = payment.proofUrl;
    const item = selectedItem;
    fetchProofPreview(proofUrl).then(rawText => {
      setProofModal({ item, payment, rawText: rawText || '' });
    }).catch(err => {
      console.error('Error opening reconciliation proof:', err);
      window.alert('Error opening payment proof. It may not exist on the server.');
    });
  };

  const handleCopyProof = () => {
    if (!proofModal) return;
    const text = [
      `Source: ${proofModal.payment.source || 'Not Recorded'}`,
      `Timestamp: ${proofModal.payment.timestamp || 'Not Recorded'}`,
      `UTR/Reference: ${proofModal.payment.utrReference || proofModal.payment.reference || 'Not Recorded'}`,
      `Amount: ${proofModal.payment.amount}`,
      `Linked Bill: ${proofModal.item.billNo}`,
      '',
      proofModal.rawText,
    ].join('\n');
    navigator.clipboard?.writeText(text).catch(err => {
      console.error('Unable to copy proof text:', err);
    });
  };

  const handleCloseDrawer = () => {
    setSelectedItem(null);
  };

  const updateFilter = (key: keyof ReconciliationFilters, value: string) => {
    setFilters(current => ({ ...current, [key]: value }));
  };

  const handleSort = (key: ReconciliationSortKey) => {
    if (sortKey === key) {
      setSortDirection(current => (current === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDirection('asc');
  };

  const paymentModeOptions = useMemo(() => Array.from(new Set(items.map(item => item.paymentMode).filter(Boolean))).sort(), [items]);
  const statusOptions = useMemo(() => Array.from(new Set(items.map(item => item.status).filter(Boolean))).sort(), [items]);
  const activeFilterCount = useMemo(() => Object.values(filters).filter(Boolean).length, [filters]);

  const visibleItems = useMemo(() => {
    const billNeedle = filters.billNo.trim().toLowerCase();
    const customerNeedle = filters.customer.trim().toLowerCase();
    const invoiceMin = filters.invoiceMin === '' ? null : Number(filters.invoiceMin);
    const invoiceMax = filters.invoiceMax === '' ? null : Number(filters.invoiceMax);
    const bankMin = filters.bankMin === '' ? null : Number(filters.bankMin);
    const bankMax = filters.bankMax === '' ? null : Number(filters.bankMax);
    const fromDate = filters.dateFrom ? new Date(`${filters.dateFrom}T00:00:00`).getTime() : null;
    const toDate = filters.dateTo ? new Date(`${filters.dateTo}T23:59:59`).getTime() : null;

    return [...items]
      .filter(item => {
        const itemDate = toDateValue(item.invoiceTimestamp || item.invoiceGeneratedAt || item.invoiceDate);
        if (billNeedle && !item.billNo.toLowerCase().includes(billNeedle)) return false;
        if (customerNeedle && !item.customer.toLowerCase().includes(customerNeedle)) return false;
        if (fromDate !== null && itemDate < fromDate) return false;
        if (toDate !== null && itemDate > toDate) return false;
        if (invoiceMin !== null && Number.isFinite(invoiceMin) && item.invoiceAmount < invoiceMin) return false;
        if (invoiceMax !== null && Number.isFinite(invoiceMax) && item.invoiceAmount > invoiceMax) return false;
        if (bankMin !== null && Number.isFinite(bankMin) && item.bankAmount < bankMin) return false;
        if (bankMax !== null && Number.isFinite(bankMax) && item.bankAmount > bankMax) return false;
        if (filters.differenceType && getDifferenceType(item) !== filters.differenceType) return false;
        if (filters.paymentMode && item.paymentMode !== filters.paymentMode) return false;
        if (filters.confidence && item.matchConfidence !== filters.confidence) return false;
        if (filters.status && item.status !== filters.status) return false;
        if (filters.specialFlag === 'special' && !item.hasSpecialPaymentFlag) return false;
        if (filters.specialFlag === 'standard' && item.hasSpecialPaymentFlag) return false;
        return true;
      })
      .sort((left, right) => {
        const leftValue = getComparableValue(left, sortKey);
        const rightValue = getComparableValue(right, sortKey);
        const direction = sortDirection === 'asc' ? 1 : -1;
        if (typeof leftValue === 'number' && typeof rightValue === 'number') {
          if (leftValue === rightValue) return right.billNo.localeCompare(left.billNo);
          return (leftValue - rightValue) * direction;
        }
        const comparison = String(leftValue).localeCompare(String(rightValue), 'en-IN', { numeric: true, sensitivity: 'base' });
        return comparison * direction;
      });
  }, [filters, items, sortDirection, sortKey]);

  if (error) return (
    <div className="m-8 p-12 bg-orange-50 border-2 border-orange-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-orange-600 mb-2">Reconciliation Offline</h2>
      <p className="text-orange-500 font-bold">{error}</p>
      <button type="button" onClick={fetchReviews} className="mt-6 rounded-xl bg-orange-600 px-5 py-3 text-sm font-black uppercase tracking-widest text-white hover:bg-orange-700">
        Retry
      </button>
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
        <>
          <section className="mb-6 rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <input value={filters.billNo} onChange={(event) => updateFilter('billNo', event.target.value)} placeholder="Bill no" className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <input value={filters.customer} onChange={(event) => updateFilter('customer', event.target.value)} placeholder="Customer" className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <input type="date" value={filters.dateFrom} onChange={(event) => updateFilter('dateFrom', event.target.value)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <input type="date" value={filters.dateTo} onChange={(event) => updateFilter('dateTo', event.target.value)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <input type="number" value={filters.invoiceMin} onChange={(event) => updateFilter('invoiceMin', event.target.value)} placeholder="Invoice min" className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <input type="number" value={filters.invoiceMax} onChange={(event) => updateFilter('invoiceMax', event.target.value)} placeholder="Invoice max" className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <input type="number" value={filters.bankMin} onChange={(event) => updateFilter('bankMin', event.target.value)} placeholder="Bank min" className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <input type="number" value={filters.bankMax} onChange={(event) => updateFilter('bankMax', event.target.value)} placeholder="Bank max" className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300" />
              <select value={filters.differenceType} onChange={(event) => updateFilter('differenceType', event.target.value)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300">
                <option value="">All difference types</option>
                <option value="clear">Clear</option>
                <option value="partial">Partial</option>
                <option value="overpaid">Overpaid</option>
                <option value="pending">Pending</option>
              </select>
              <select value={filters.paymentMode} onChange={(event) => updateFilter('paymentMode', event.target.value)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300">
                <option value="">All payment modes</option>
                {paymentModeOptions.map(mode => <option key={mode} value={mode}>{mode}</option>)}
              </select>
              <select value={filters.confidence} onChange={(event) => updateFilter('confidence', event.target.value)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300">
                <option value="">All confidence</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
              </select>
              <select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300">
                <option value="">All statuses</option>
                {statusOptions.map(status => <option key={status} value={status}>{status}</option>)}
              </select>
              <select value={filters.specialFlag} onChange={(event) => updateFilter('specialFlag', event.target.value)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold outline-none focus:border-blue-300">
                <option value="">All payment flags</option>
                <option value="special">Advance / old gold / purchase</option>
                <option value="standard">Standard payments</option>
              </select>
              <button type="button" onClick={() => setFilters(defaultFilters)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-black text-gray-600 hover:bg-gray-50">
                Clear Filters
              </button>
            </div>
            <p className="mt-4 text-xs font-bold uppercase tracking-widest text-gray-400">
              Showing {visibleItems.length} of {items.length} open reconciliation items
              {activeFilterCount > 0 ? ` · ${activeFilterCount} active filters` : ''}
            </p>
          </section>

          <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
            <ReconciliationTable
              items={visibleItems}
              onRowClick={handleRowClick}
              onViewInvoice={handleViewInvoice}
              sortKey={sortKey}
              sortDirection={sortDirection}
              onSort={handleSort}
            />
          </div>
        </>
      )}

      {selectedItem && (
        <InvoiceDetailDrawer
          item={selectedItem}
          onClose={handleCloseDrawer}
          onViewInvoice={handleViewInvoice}
          onViewProof={handleViewProof}
        />
      )}

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
              <button type="button" onClick={() => setProofModal(null)} className="text-gray-400 hover:text-gray-900 font-bold">Close</button>
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

export default ReconciliationQueuePage;

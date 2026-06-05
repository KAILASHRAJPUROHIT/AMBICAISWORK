import React, { useEffect, useMemo, useState } from 'react';
import ReconciliationTable from '../components/ReconciliationTable';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer';
import { getOpenReviews } from '../api/client';
import type { ReconciliationItem, ReconciliationPaymentEvidence } from '../types';

export type ReconciliationSortKey =
  | 'billNo'
  | 'customer'
  | 'invoiceDate'
  | 'invoiceAmount'
  | 'bankAmount'
  | 'difference'
  | 'paymentMode'
  | 'matchConfidence'
  | 'status';

export type ReconciliationSortDirection = 'asc' | 'desc';

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
  if (['CLEAR', 'CLEARED', 'VERIFIED', 'PAID', 'GREEN'].includes(status)) return 'CLEAR';
  if (['PARTIAL PAYMENT', 'PARTIAL_PAYMENT', 'PARTIAL'].includes(status)) return 'PARTIAL PAYMENT';
  if (['PENDING BANK', 'PENDING_BANK', 'PENDING'].includes(status)) return 'PENDING BANK';
  if (['REALIZING CHEQUE', 'REALIZING_CHEQUE', 'CHEQUE_DEPOSITED', 'CHEQUE_CLEARING', 'BLUE'].includes(status)) return 'REALIZING CHEQUE';
  if (['ADVANCE PENDING', 'ADVANCE_PENDING', 'PURPLE'].includes(status)) return 'ADVANCE PENDING';
  if (['ACCOUNTANT APPROVAL REQUIRED', 'ACCOUNTANT_APPROVAL_REQUIRED'].includes(status)) return 'ACCOUNTANT APPROVAL REQUIRED';
  return 'RISK / MISMATCH';
};

const toStatusColor = (value: unknown): ReconciliationItem['statusColor'] => {
  const color = String(value || '').toUpperCase();
  if (['GREEN', 'BLUE', 'YELLOW', 'RED', 'PURPLE'].includes(color)) {
    return color as ReconciliationItem['statusColor'];
  }
  return undefined;
};

const toDifferenceType = (value: unknown, difference: number): ReconciliationItem['differenceType'] => {
  const type = String(value || '').toLowerCase();
  if (['zero', 'outstanding', 'overpaid', 'mismatch'].includes(type)) {
    return type as ReconciliationItem['differenceType'];
  }
  if (Math.abs(difference) < 0.01) return 'zero';
  return difference > 0 ? 'outstanding' : 'overpaid';
};

const getDateTime = (item: ReconciliationItem) => {
  const raw = item.invoiceGeneratedAt || item.invoiceDate || '';
  const time = raw ? new Date(raw).getTime() : 0;
  return Number.isNaN(time) ? 0 : time;
};

const normalizePaymentBreakdown = (rows: any[]): ReconciliationPaymentEvidence[] => (
  Array.isArray(rows) ? rows.map((payment) => ({
    amount: toAmount(payment.amount),
    mode: String(payment.mode || 'UNKNOWN'),
    timestamp: payment.timestamp || null,
    utrReference: payment.utr_reference || payment.utrReference || null,
    reference: payment.reference || null,
    source: payment.source || null,
    evidenceLink: payment.evidence_link || payment.evidenceLink || null,
    evidenceAvailable: Boolean(payment.evidence_available ?? payment.evidenceAvailable)
  })) : []
);

const normalizeReview = (row: any, idx: number): ReconciliationItem => {
  const difference = toAmount(row.difference);
  return {
    id: row.bill_no || `REC_${idx}`,
    billNo: String(row.bill_no || '---'),
    customer: row.customer_name || 'Unknown Customer',
    invoiceAmount: toAmount(row.invoice_amount),
    bankAmount: toAmount(row.bank_amount),
    totalReceived: toAmount(row.total_received ?? row.bank_amount),
    difference,
    outstanding: toAmount(row.outstanding),
    overpaid: toAmount(row.overpaid),
    differenceType: toDifferenceType(row.difference_type, difference),
    paymentMode: row.payment_mode || 'UNKNOWN',
    matchConfidence: toConfidence(row.confidence),
    status: toStatus(row.status),
    statusColor: toStatusColor(row.status_color),
    reviewRequired: Boolean(row.review_required),
    statusExplanation: row.status_explanation || null,
    invoiceDate: row.invoice_date || null,
    invoiceGeneratedAt: row.invoice_generated_at || null,
    bankTime: row.bank_time || null,
    verifiedAt: row.verified_at || null,
    verifiedBy: row.verified_by || null,
    utrReference: row.utr_reference || null,
    reviewAge: row.review_age || null,
    sourceSystem: row.source_system || null,
    createdAt: row.created_at || null,
    updatedAt: row.updated_at || null,
    paymentBreakdown: normalizePaymentBreakdown(row.payment_breakdown)
  };
};

const compareValues = (a: string | number, b: string | number, direction: ReconciliationSortDirection) => {
  const result = typeof a === 'number' && typeof b === 'number'
    ? a - b
    : String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
  return direction === 'asc' ? result : -result;
};

const sortValue = (item: ReconciliationItem, key: ReconciliationSortKey): string | number => {
  switch (key) {
    case 'invoiceDate':
      return getDateTime(item);
    case 'invoiceAmount':
      return item.invoiceAmount;
    case 'bankAmount':
      return item.bankAmount;
    case 'difference':
      return item.difference;
    case 'customer':
      return item.customer;
    case 'paymentMode':
      return item.paymentMode;
    case 'matchConfidence':
      return item.matchConfidence;
    case 'status':
      return item.status;
    case 'billNo':
    default:
      return item.billNo;
  }
};

const ReconciliationQueuePage: React.FC = () => {
  const [items, setItems] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);
  const [sortKey, setSortKey] = useState<ReconciliationSortKey>('invoiceDate');
  const [sortDirection, setSortDirection] = useState<ReconciliationSortDirection>('desc');
  const [filters, setFilters] = useState({
    dateFrom: '',
    dateTo: '',
    billNo: '',
    customer: '',
    amountMin: '',
    amountMax: '',
    paymentMode: '',
    status: '',
    confidence: '',
    differenceType: ''
  });

  useEffect(() => {
    getOpenReviews()
      .then(data => {
        setItems(data.map(normalizeReview));
      })
      .catch(err => {
        console.error('Reconciliation fetch error:', err);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, []);

  const filterOptions = useMemo(() => ({
    paymentModes: Array.from(new Set(items.map(item => item.paymentMode).filter(Boolean))).sort(),
    statuses: Array.from(new Set(items.map(item => item.status))).sort(),
    confidences: ['High', 'Medium', 'Low']
  }), [items]);

  const visibleItems = useMemo(() => {
    const amountMin = filters.amountMin === '' ? null : Number(filters.amountMin);
    const amountMax = filters.amountMax === '' ? null : Number(filters.amountMax);
    const dateFrom = filters.dateFrom ? new Date(`${filters.dateFrom}T00:00:00`).getTime() : null;
    const dateTo = filters.dateTo ? new Date(`${filters.dateTo}T23:59:59`).getTime() : null;

    const filtered = items.filter(item => {
      const invoiceTime = getDateTime(item);
      if (dateFrom !== null && invoiceTime < dateFrom) return false;
      if (dateTo !== null && invoiceTime > dateTo) return false;
      if (filters.billNo && !item.billNo.toLowerCase().includes(filters.billNo.toLowerCase())) return false;
      if (filters.customer && !item.customer.toLowerCase().includes(filters.customer.toLowerCase())) return false;
      if (amountMin !== null && item.invoiceAmount < amountMin) return false;
      if (amountMax !== null && item.invoiceAmount > amountMax) return false;
      if (filters.paymentMode && item.paymentMode !== filters.paymentMode) return false;
      if (filters.status && item.status !== filters.status) return false;
      if (filters.confidence && item.matchConfidence !== filters.confidence) return false;
      if (filters.differenceType && item.differenceType !== filters.differenceType) return false;
      return true;
    });

    return filtered.sort((a, b) => {
      const primary = compareValues(sortValue(a, sortKey), sortValue(b, sortKey), sortDirection);
      if (primary !== 0) return primary;
      const byGeneratedAt = compareValues(getDateTime(a), getDateTime(b), 'desc');
      if (byGeneratedAt !== 0) return byGeneratedAt;
      return compareValues(a.billNo, b.billNo, 'desc');
    });
  }, [filters, items, sortDirection, sortKey]);

  const handleSort = (key: ReconciliationSortKey) => {
    if (key === sortKey) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
      return;
    }
    setSortKey(key);
    setSortDirection(key === 'invoiceDate' ? 'desc' : 'asc');
  };

  const updateFilter = (key: keyof typeof filters, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  if (error) return (
    <div className="m-8 p-12 bg-orange-50 border-2 border-orange-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-orange-600 mb-2">Reconciliation Offline</h2>
      <p className="text-orange-500 font-bold">{error}</p>
    </div>
  );

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-8 text-center md:text-left">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Live Reconciliation Queue</h1>
        <p className="mt-2 text-lg text-gray-600 font-medium">Direct synchronization with Prime accounting records.</p>
      </header>

      <section className="mb-5 grid grid-cols-1 md:grid-cols-4 xl:grid-cols-8 gap-3">
        <input className="rounded-xl border border-gray-200 px-3 py-2 text-sm" type="date" value={filters.dateFrom} onChange={e => updateFilter('dateFrom', e.target.value)} />
        <input className="rounded-xl border border-gray-200 px-3 py-2 text-sm" type="date" value={filters.dateTo} onChange={e => updateFilter('dateTo', e.target.value)} />
        <input className="rounded-xl border border-gray-200 px-3 py-2 text-sm" placeholder="Bill no" value={filters.billNo} onChange={e => updateFilter('billNo', e.target.value)} />
        <input className="rounded-xl border border-gray-200 px-3 py-2 text-sm" placeholder="Customer" value={filters.customer} onChange={e => updateFilter('customer', e.target.value)} />
        <input className="rounded-xl border border-gray-200 px-3 py-2 text-sm" type="number" placeholder="Min amount" value={filters.amountMin} onChange={e => updateFilter('amountMin', e.target.value)} />
        <input className="rounded-xl border border-gray-200 px-3 py-2 text-sm" type="number" placeholder="Max amount" value={filters.amountMax} onChange={e => updateFilter('amountMax', e.target.value)} />
        <select className="rounded-xl border border-gray-200 px-3 py-2 text-sm" value={filters.paymentMode} onChange={e => updateFilter('paymentMode', e.target.value)}>
          <option value="">All modes</option>
          {filterOptions.paymentModes.map(mode => <option key={mode} value={mode}>{mode}</option>)}
        </select>
        <select className="rounded-xl border border-gray-200 px-3 py-2 text-sm" value={filters.status} onChange={e => updateFilter('status', e.target.value)}>
          <option value="">All statuses</option>
          {filterOptions.statuses.map(status => <option key={status} value={status}>{status}</option>)}
        </select>
        <select className="rounded-xl border border-gray-200 px-3 py-2 text-sm" value={filters.confidence} onChange={e => updateFilter('confidence', e.target.value)}>
          <option value="">All confidence</option>
          {filterOptions.confidences.map(confidence => <option key={confidence} value={confidence}>{confidence}</option>)}
        </select>
        <select className="rounded-xl border border-gray-200 px-3 py-2 text-sm" value={filters.differenceType} onChange={e => updateFilter('differenceType', e.target.value)}>
          <option value="">All differences</option>
          <option value="zero">Zero</option>
          <option value="outstanding">Outstanding</option>
          <option value="overpaid">Overpaid</option>
          <option value="mismatch">Mismatch</option>
        </select>
        <button className="rounded-xl border border-gray-200 px-3 py-2 text-sm font-bold text-gray-600 hover:bg-white" onClick={() => setFilters({ dateFrom: '', dateTo: '', billNo: '', customer: '', amountMin: '', amountMax: '', paymentMode: '', status: '', confidence: '', differenceType: '' })}>
          Clear
        </button>
        <div className="rounded-xl border border-gray-200 px-3 py-2 text-sm font-bold text-gray-500 bg-white">
          {visibleItems.length} shown
        </div>
      </section>

      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-bounce uppercase tracking-widest">
          Syncing Records...
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl">
          No open reconciliation items
        </div>
      ) : (
        <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
          <ReconciliationTable
            items={visibleItems}
            onRowClick={setSelectedItem}
            sortKey={sortKey}
            sortDirection={sortDirection}
            onSort={handleSort}
          />
        </div>
      )}

      {selectedItem && (
        <InvoiceDetailDrawer item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}
    </div>
  );
};

export default ReconciliationQueuePage;

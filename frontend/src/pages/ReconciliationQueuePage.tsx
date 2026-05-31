import React, { useState, useEffect } from 'react';
import ReconciliationTable from '../components/ReconciliationTable';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer';
import type { ReconciliationItem } from '../mockReconciliationData';

const ReconciliationQueuePage: React.FC = () => {
  const [items, setItems] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);

  useEffect(() => {
    fetch('/api/prime/manual-report-import/latest')
      .then(res => res.json())
      .then(data => {
        const records = data.records || [];
        const transformed: ReconciliationItem[] = records.map((r: any, idx: number) => ({
          id: r.invoice_no || `REC_${idx}`,
          billNo: r.invoice_no || '---',
          customer: r.customer_name || 'UNKNOWN CUSTOMER',
          invoiceAmount: r.sale_amount || 0.0,
          bankAmount: r.bank_amount || 0.0,
          difference: (r.sale_amount || 0.0) - (r.bank_amount || 0.0),
          paymentMode: r.payment_rows?.[0]?.payment_mode || 'MULTI',
          matchConfidence: r.validation_status === 'GREEN' ? 'High' : 'Low',
          status: r.validation_status === 'GREEN' ? 'Verified' : 'Risk / Mismatch'
        }));
        setItems(transformed);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleRowClick = (item: ReconciliationItem) => {
    setSelectedItem(item);
  };

  const handleCloseDrawer = () => {
    setSelectedItem(null);
  };

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Reconciliation Queue</h1>
        <p className="mt-2 text-lg text-gray-600">Manage and review all pending and verified reconciliation items from Prime.</p>
      </header>

      {loading && <div className="p-12 text-center text-blue-600 font-bold">Loading live reconciliation data...</div>}
      {error && <div className="p-12 text-center text-red-500 font-bold">Error: {error}</div>}

      {!loading && !error && items.length === 0 && (
        <div className="p-12 text-center bg-white rounded-2xl shadow-sm border border-gray-100 text-gray-500">
          No reconciliation items to display.
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
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


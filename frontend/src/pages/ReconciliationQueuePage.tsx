import React, { useState, useEffect } from 'react';
import ReconciliationTable from '../components/ReconciliationTable';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer';
import { getHeaders } from '../api/client';
import type { ReconciliationItem } from '../types';

const ReconciliationQueuePage: React.FC = () => {
  const [items, setItems] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);

  useEffect(() => {
    fetch(`${window.location.origin}/reviews/open`, { headers: getHeaders() })
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch live reconciliation data.');
        return res.json();
      })
      .then(data => {
        const transformed: ReconciliationItem[] = data.map((r: any, idx: number) => ({
          id: r.review_id || `REC_${idx}`,
          billNo: String(r.entity_id || '---'),
          customer: r.entity_type || 'Review Item',
          invoiceAmount: 0.0,
          bankAmount: 0.0,
          difference: 0.0,
          paymentMode: r.queue_type || 'Review',
          matchConfidence: r.escalation_required ? 'Low' : 'Medium',
          status: r.escalation_required ? 'Risk / Mismatch' : 'Pending'
        }));
        setItems(transformed);
      })
      .catch(err => {
        console.error("Reconciliation fetch error:", err);
        setError(err.message);
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
          Zero pending items found.
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

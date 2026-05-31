import { useState } from 'react';
import ReconciliationTable from '../components/ReconciliationTable';
import { mockReconciliationData } from '../mockReconciliationData';
import type { ReconciliationItem } from '../mockReconciliationData';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer'; 

const ReconciliationQueuePage = () => {
  const loading = false; // Hardcoded to false as per instructions to not use backend useEffect
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);

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
        <p className="mt-2 text-lg text-gray-600">Manage and review all pending and verified reconciliation items.</p>
      </header>
      
      {loading && <div className="p-12 text-center text-blue-600 font-bold">Loading reconciliation data...</div>}
      {!loading && mockReconciliationData.length === 0 && (
        <div className="p-12 text-center bg-white rounded-2xl shadow-sm border border-gray-100 text-gray-500">
          No reconciliation items to display.
        </div>
      )}

      {!loading && mockReconciliationData.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <ReconciliationTable items={mockReconciliationData} onRowClick={handleRowClick} />
        </div>
      )}

      {selectedItem && (
        <InvoiceDetailDrawer item={selectedItem} onClose={handleCloseDrawer} />
      )}
    </div>
  );
};

export default ReconciliationQueuePage;

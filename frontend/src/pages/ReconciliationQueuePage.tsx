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
    <div className="reconciliation-queue-page">
      <h1>Reconciliation Queue</h1>
      <p>Manage and review all reconciliation items.</p>
      
      {loading && <div className="loading-indicator">Loading reconciliation data...</div>}
      {!loading && mockReconciliationData.length === 0 && (
        <div className="empty-state">No reconciliation items to display.</div>
      )}

      {!loading && mockReconciliationData.length > 0 && (
        <ReconciliationTable items={mockReconciliationData} onRowClick={handleRowClick} />
      )}

      {selectedItem && (
        <InvoiceDetailDrawer item={selectedItem} onClose={handleCloseDrawer} />
      )}
    </div>
  );
};

export default ReconciliationQueuePage;

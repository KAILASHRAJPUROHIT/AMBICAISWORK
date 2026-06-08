import React, { useEffect, useState } from 'react';
import { getEscalationExceptions, postAskExplanation, approveAccountantVerification, rejectAccountantVerification } from '../api/client';

interface EscalationException {
  id: string;
  bill_id: number;
  invoice_no: string;
  category: string;
  reason: string;
  amount: number;
  payment_mode: string;
  status: string;
  age_days: number;
}

const EscalationsPage: React.FC = () => {
  const [exceptions, setExceptions] = useState<EscalationException[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [actionLoading, setActionLoading] = useState(false);
  const [explanationMessage, setExplanationMessage] = useState("");

  const fetchExceptions = () => {
    setLoading(true);
    setError(null);
    getEscalationExceptions()
      .then((data: any) => setExceptions(data))
      .catch((err: any) => setError(err.message || 'Failed to load exceptions.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchExceptions();
  }, []);

  const exceptionsByCategory = exceptions.reduce((acc, current) => {
    if (!acc[current.category]) acc[current.category] = [];
    acc[current.category].push(current);
    return acc;
  }, {} as Record<string, EscalationException[]>);

  const formatCurrency = (value: number) => `₹${value.toLocaleString('en-IN')}`;

  const handleSelectAll = (category: string) => {
    const categoryItems = exceptionsByCategory[category] || [];
    const allSelected = categoryItems.every(item => selectedIds.has(item.id));
    
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allSelected) {
        categoryItems.forEach(item => next.delete(item.id));
      } else {
        categoryItems.forEach(item => {
          if (item.id.startsWith('queue_')) next.add(item.id);
        });
      }
      return next;
    });
  };

  const toggleSelect = (id: string) => {
    if (!id.startsWith('queue_')) return; // Only allow selecting queue items
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const getSelectedQueueIds = () => {
    return Array.from(selectedIds)
      .filter(id => id.startsWith('queue_'))
      .map(id => parseInt(id.split('_')[1]));
  };

  const handleBulkAction = async (action: 'approve' | 'reject' | 'explain') => {
    const queueIds = getSelectedQueueIds();
    if (queueIds.length === 0) return;

    setActionLoading(true);
    try {
      if (action === 'explain') {
        await postAskExplanation(queueIds, explanationMessage);
        alert(`Explanation request sent for ${queueIds.length} items.`);
        setExplanationMessage("");
      } else if (action === 'approve') {
        for (const qid of queueIds) {
          await approveAccountantVerification(qid, "Bulk approved from escalations dashboard");
        }
        alert(`Approved ${queueIds.length} items.`);
      } else if (action === 'reject') {
        for (const qid of queueIds) {
          await rejectAccountantVerification(qid, "Bulk rejected from escalations dashboard");
        }
        alert(`Rejected ${queueIds.length} items.`);
      }
      setSelectedIds(new Set());
      fetchExceptions();
    } catch (err: any) {
      alert(err.message || 'Action failed.');
    } finally {
      setActionLoading(false);
    }
  };

  if (error) return (
    <div className="m-8 p-12 bg-red-50 border-2 border-red-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-red-600 mb-2">Escalations Offline</h2>
      <p className="text-red-500 font-bold">{error}</p>
      <button type="button" onClick={fetchExceptions} className="mt-6 rounded-xl bg-red-600 px-5 py-3 text-sm font-black uppercase tracking-widest text-white hover:bg-red-700">
        Retry
      </button>
    </div>
  );

  const selectedCount = selectedIds.size;

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-10 text-center md:text-left">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Exception Dashboard</h1>
        <p className="mt-2 text-lg text-gray-600 font-medium">Critical system alerts and ageing payments.</p>
      </header>

      {selectedCount > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4 shadow-2xl z-50 flex flex-col md:flex-row items-center justify-between px-8">
          <div className="font-bold text-gray-700 mb-4 md:mb-0">
            <span className="bg-orange-100 text-orange-700 px-3 py-1 rounded-full mr-3">{selectedCount} Selected</span>
            Queue Items
          </div>
          
          <div className="flex flex-col md:flex-row gap-4 items-center">
             <input 
                type="text" 
                placeholder="Message for accountant (optional)..." 
                className="text-sm border border-gray-300 rounded-lg px-4 py-2 w-64 focus:outline-none focus:border-orange-500"
                value={explanationMessage}
                onChange={e => setExplanationMessage(e.target.value)}
                disabled={actionLoading}
             />
             <div className="flex gap-2">
                <button 
                  onClick={() => handleBulkAction('explain')} 
                  disabled={actionLoading}
                  className="bg-orange-600 text-white font-bold py-2 px-6 rounded-xl hover:bg-orange-700 transition-colors disabled:opacity-50"
                >
                  {actionLoading ? 'Processing...' : 'Ask Explanation'}
                </button>
                <button 
                  onClick={() => handleBulkAction('approve')} 
                  disabled={actionLoading}
                  className="bg-green-600 text-white font-bold py-2 px-6 rounded-xl hover:bg-green-700 transition-colors disabled:opacity-50"
                >
                  Approve
                </button>
                <button 
                  onClick={() => handleBulkAction('reject')} 
                  disabled={actionLoading}
                  className="bg-red-600 text-white font-bold py-2 px-6 rounded-xl hover:bg-red-700 transition-colors disabled:opacity-50"
                >
                  Reject
                </button>
             </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-pulse uppercase tracking-widest">
          Loading Exceptions...
        </div>
      ) : exceptions.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl">
          No critical exceptions found.
        </div>
      ) : (
        <div className="space-y-12 pb-32">
          {Object.entries(exceptionsByCategory).map(([category, items]) => {
            const hasQueueItems = items.some(i => i.id.startsWith('queue_'));
            return (
              <section key={category}>
                <div className="flex items-center mb-6 border-b-2 border-gray-200 pb-2">
                  <h2 className="text-2xl font-black text-gray-800">
                    {category} <span className="ml-2 rounded-full bg-red-100 text-red-700 px-3 py-1 text-sm">{items.length}</span>
                  </h2>
                  {hasQueueItems && (
                     <button 
                       onClick={() => handleSelectAll(category)}
                       className="ml-6 text-sm font-bold text-blue-600 hover:text-blue-800"
                     >
                       Select All Queue Items
                     </button>
                  )}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                  {items.map(item => {
                    const isQueue = item.id.startsWith('queue_');
                    const isSelected = selectedIds.has(item.id);
                    
                    return (
                      <div 
                        key={item.id} 
                        onClick={() => toggleSelect(item.id)}
                        className={`bg-white rounded-3xl p-6 shadow-sm border ${isSelected ? 'border-orange-500 ring-2 ring-orange-200' : 'border-red-100'} hover:shadow-md transition-all relative overflow-hidden ${isQueue ? 'cursor-pointer' : 'opacity-75'}`}
                      >
                        <div className={`absolute top-0 left-0 w-2 h-full ${isSelected ? 'bg-orange-500' : 'bg-red-500'}`} />
                        {isQueue && (
                          <div className="absolute top-4 right-4">
                            <div className={`w-6 h-6 rounded border-2 flex items-center justify-center ${isSelected ? 'bg-orange-500 border-orange-500' : 'border-gray-300'}`}>
                              {isSelected && <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                            </div>
                          </div>
                        )}
                        <div className="flex justify-between items-start mb-4 pr-8">
                          <div>
                            <p className="text-xs font-black uppercase tracking-widest text-gray-400">Bill No</p>
                            <p className="font-bold text-gray-900 text-lg">{item.invoice_no}</p>
                          </div>
                          <div className="text-right">
                            <p className="font-black text-gray-900 text-lg">{formatCurrency(item.amount)}</p>
                            <p className="text-xs font-bold uppercase text-gray-400">{item.payment_mode}</p>
                          </div>
                        </div>
                        <p className="text-sm font-semibold text-red-700 bg-red-50 rounded-xl p-3 border border-red-100">
                          {item.reason}
                        </p>
                        {!isQueue && (
                           <p className="text-[10px] text-gray-400 mt-3 font-bold uppercase">Not a queue item (Cannot action)</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default EscalationsPage;

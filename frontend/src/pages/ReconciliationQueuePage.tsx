import React, { useState, useEffect, useMemo } from 'react';
import ReconciliationTable from '../components/ReconciliationTable';
import InvoiceDetailDrawer from '../components/InvoiceDetailDrawer';
import type { ReconciliationItem } from '../types';
import { getHeaders } from '../api/client';

const ReconciliationQueuePage: React.FC = () => {
  const [items, setItems] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ReconciliationItem | null>(null);

  // Filter States
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [modeFilter, setModeFilter] = useState('All');
  const [confidenceFilter, setConfidenceFilter] = useState('All');
  const [differenceFilter, setDifferenceFilter] = useState('All');
  const [startDate, setStartDate] = useState('');
  const [endDate, setStartDateEnd] = useState('');

  useEffect(() => {
    fetch(`${window.location.origin}/api/reconciliations`, { headers: getHeaders() })
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch live reconciliation data.');
        return res.json();
      })
      .then(data => {
        const transformed: ReconciliationItem[] = data.map((r: any, idx: number) => ({
          id: r.invoice_no || `REC_${idx}`,
          billNo: r.invoice_no || '---',
          customer: r.details?.customer || 'S.A. JEWELLERS CLIENT',
          invoiceAmount: r.details?.total || 0.0,
          bankAmount: r.details?.payments || 0.0,
          difference: (r.details?.total || 0.0) - (r.details?.payments || 0.0),
          paymentMode: r.details?.mode || 'BANK',
          matchConfidence: r.status === 'GREEN' ? 'High' : (r.status === 'YELLOW' ? 'Medium' : 'Low'),
          status: r.status === 'GREEN' ? 'Verified' : (r.status === 'YELLOW' ? 'Advance Pending' : (r.status === 'ORANGE' ? 'Ambiguous Match' : (r.status === 'BLUE' ? 'Realizing Cheque' : 'Risk / Mismatch'))),
          rawStatus: r.status,
          invoiceDate: r.invoice_date,
          invoiceUrl: r.details?.invoice_url || null,
          proofUrl: r.details?.proof_url || null
        }));
        setItems(transformed);
      })
      .catch(err => {
        console.error("Reconciliation fetch error:", err);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, []);

  const filteredItems = useMemo(() => {
    return items.filter(item => {
      const matchesSearch = !search || 
        item.billNo.toLowerCase().includes(search.toLowerCase()) ||
        item.customer.toLowerCase().includes(search.toLowerCase());
      
      const matchesStatus = statusFilter === 'All' || item.rawStatus.toUpperCase() === statusFilter.toUpperCase();
      const matchesMode = modeFilter === 'All' || item.paymentMode.toUpperCase().includes(modeFilter.toUpperCase());
      const matchesConfidence = confidenceFilter === 'All' || item.matchConfidence.toUpperCase() === confidenceFilter.toUpperCase();
      
      const diffValue = Math.abs(item.difference);
      const matchesDifference = differenceFilter === 'All' || 
        (differenceFilter === 'Matched' && diffValue < 1) ||
        (differenceFilter === 'Difference Present' && diffValue >= 1);

      const matchesDate = (!startDate || (item.invoiceDate && item.invoiceDate >= startDate)) &&
                          (!endDate || (item.invoiceDate && item.invoiceDate <= endDate));

      return matchesSearch && matchesStatus && matchesMode && matchesConfidence && matchesDifference && matchesDate;
    });
  }, [items, search, statusFilter, modeFilter, confidenceFilter, differenceFilter, startDate, endDate]);

  const clearFilters = () => {
    setSearch('');
    setStatusFilter('All');
    setModeFilter('All');
    setConfidenceFilter('All');
    setDifferenceFilter('All');
    setStartDate('');
    setStartDateEnd('');
  };

  const handleRowClick = (item: ReconciliationItem) => {
    setSelectedItem(item);
  };

  if (error) return (
    <div className="m-8 p-12 bg-orange-50 border-2 border-orange-200 rounded-3xl text-center">
      <h2 className="text-2xl font-black text-orange-600 mb-2">Reconciliation Offline</h2>
      <p className="text-orange-500 font-bold">{error}</p>
    </div>
  );

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <header className="mb-8 flex flex-col md:flex-row justify-between items-end gap-4">
        <div>
          <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">Live Reconciliation Queue</h1>
          <p className="mt-1 text-gray-500 font-medium italic">Direct synchronization with Prime accounting records.</p>
        </div>
        <div className="bg-blue-600 text-white px-6 py-2 rounded-2xl font-black text-sm shadow-lg uppercase tracking-widest">
           {filteredItems.length} Records Found
        </div>
      </header>

      {/* Filter Bar */}
      <div className="mb-8 bg-white p-6 rounded-3xl shadow-xl border border-gray-100 grid grid-cols-1 md:grid-cols-4 gap-6">
        <div>
          <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Search Records</label>
          <input 
            type="text" 
            placeholder="Bill No, Customer..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-sm focus:border-blue-500 outline-none transition-all"
          />
        </div>

        <div>
          <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Status</label>
          <select 
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-sm focus:border-blue-500 outline-none transition-all"
          >
            {['All', 'Green', 'Yellow', 'Orange', 'Red', 'Blue', 'Grey'].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Mode</label>
          <select 
            value={modeFilter}
            onChange={(e) => setModeFilter(e.target.value)}
            className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-sm focus:border-blue-500 outline-none transition-all"
          >
            {['All', 'Cash', 'UPI', 'NEFT', 'IMPS', 'RTGS', 'Cheque'].map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <div className="flex items-end">
           <button 
             onClick={clearFilters}
             className="w-full bg-gray-100 hover:bg-gray-200 text-gray-600 font-black py-2 rounded-xl text-xs uppercase tracking-widest transition-all"
           >
             Clear Filters
           </button>
        </div>

        <div>
          <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Confidence</label>
          <select 
            value={confidenceFilter}
            onChange={(e) => setConfidenceFilter(e.target.value)}
            className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-sm focus:border-blue-500 outline-none transition-all"
          >
            {['All', 'High', 'Medium', 'Low'].map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Variance</label>
          <select 
            value={differenceFilter}
            onChange={(e) => setDifferenceFilter(e.target.value)}
            className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-sm focus:border-blue-500 outline-none transition-all"
          >
            {['All', 'Matched', 'Difference Present'].map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        <div className="md:col-span-2 grid grid-cols-2 gap-4">
           <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">From Date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-sm outline-none" />
           </div>
           <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">To Date</label>
              <input type="date" value={endDate} onChange={(e) => setStartDateEnd(e.target.value)} className="w-full bg-gray-50 border-2 border-gray-100 rounded-xl px-4 py-2 font-bold text-sm outline-none" />
           </div>
        </div>
      </div>

      {loading ? (
        <div className="p-20 text-center text-blue-600 font-black text-2xl animate-bounce uppercase tracking-widest">
          Syncing Records...
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="p-20 text-center bg-white rounded-3xl shadow-sm border border-gray-100 text-gray-400 font-bold text-xl uppercase tracking-tighter">
          No reconciliation records match current filters.
        </div>
      ) : (
        <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
          <ReconciliationTable items={filteredItems} onRowClick={handleRowClick} />
        </div>
      )}

      {selectedItem && (
        <InvoiceDetailDrawer item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}
    </div>
  );
};

export default ReconciliationQueuePage;

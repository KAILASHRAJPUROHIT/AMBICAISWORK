import re

file_path = 'frontend/src/pages/DashboardPage.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Interfaces
text = text.replace(
'''  is_historical_claim: boolean;
  historical_payment_date: string | null;
  pdf_path: string | null;
  created_at: string;
}''',
'''  is_historical_claim: boolean;
  historical_payment_date: string | null;
  pdf_path: string | null;
  payment_mode?: string;
  created_at: string;
}

interface LiveMappedPayment {
  id: number;
  bill_id: number;
  bill_number: string;
  customer_name: string;
  amount: number;
  payment_mode: string;
  utr_reference: string | null;
  payment_date: string | null;
  status: string;
  created_at: string | null;
}'''
)

# 2. State
text = text.replace(
'''  const [liveFeed, setLiveFeed] = useState<LiveInvoice[]>([]);
  const [paymentEvents, setPaymentEvents] = useState<LivePaymentEvent[]>([]);''',
'''  const [liveFeed, setLiveFeed] = useState<LiveInvoice[]>([]);
  const [mappedPaymentsFeed, setMappedPaymentsFeed] = useState<LiveMappedPayment[]>([]);
  const [paymentEvents, setPaymentEvents] = useState<LivePaymentEvent[]>([]);'''
)

# 3. State 'showFullPipeline'
text = text.replace(
'''  const [showFullPipeline, setShowFullPipeline] = useState(false);''',
'''  const [showFullPipeline, setShowFullPipeline] = useState(false); // @ts-ignore'''
)

# 4. Fetch logic
text = text.replace(
'''      const endpoints = [
        `${API_BASE}/api/dashboard/live`,
        `${API_BASE}/api/invoices/live-feed?days=7&per_day=20`,
        `${API_BASE}/api/admin/ingestion-status`,
        `${API_BASE}/api/admin/email-status`,
        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/live-payment-events`,
        `${API_BASE}/api/version`
      ];''',
'''      const endpoints = [
        `${API_BASE}/api/dashboard/live`,
        `${API_BASE}/api/invoices/live-feed?days=1&per_day=500&filter_today=true`,
        `${API_BASE}/api/admin/ingestion-status`,
        `${API_BASE}/api/admin/email-status`,
        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/live-payment-events`,
        `${API_BASE}/api/version`,
        `${API_BASE}/api/payments/live-feed?filter_today=true`
      ];'''
)

text = text.replace(
'''      if (responses[6] && responses[6].ok) {
         const vData = await (responses[6] as Response).json();
         setAppVersion(vData.version);
      }''',
'''      if (responses[6] && responses[6].ok) {
         const vData = await (responses[6] as Response).json();
         setAppVersion(vData.version);
      }
      if (responses[7] && responses[7].ok) setMappedPaymentsFeed(await (responses[7] as Response).json());'''
)

start_idx = text.find('        <div className={stats?.is_owner ? "lg:col-span-2" : "lg:col-span-3"}>')
end_idx = text.find('      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-6">\n        <div className="lg:col-span-3">\n          <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-6 border-b border-gray-200 pb-2">')

if start_idx != -1 and end_idx != -1:
    ui_replacement = """        <div className={stats?.is_owner ? "lg:col-span-2" : "lg:col-span-3"}>
          {/* Section A — Today's Bills */}
          <div className="flex justify-between items-center mb-6 border-b border-gray-200 pb-2">
             <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest">Today's Bills</h2>
          </div>
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden mb-8">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Invoice Number</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Customer Name</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Amount</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Mode</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Status</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Invoice Date</th>
                </tr>
              </thead>
              <tbody>
                {liveFeed.map((inv) => (
                  <tr key={inv.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="p-4 font-black text-gray-900">{inv.bill_number}</td>
                    <td className="p-4 text-sm text-gray-600 font-medium">{inv.customer_name}</td>
                    <td className="p-4 font-black text-gray-900 text-right">{money(inv.invoice_total)}</td>
                    <td className="p-4 text-xs font-bold text-gray-600 uppercase">{inv.payment_mode || 'N/A'}</td>
                    <td className="p-4">
                      <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase border ${pipelineStatusClass(inv.status, inv.status_text)}`}>
                        {operatorLabel(inv.status_text || inv.status)}
                      </span>
                    </td>
                    <td className="p-4 text-xs text-gray-500 font-bold text-right uppercase">
                      {inv.invoice_date || (inv.created_at ? inv.created_at.split('T')[0] : '-')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {liveFeed.length === 0 && (
              <div className="p-12 text-center text-gray-400 italic font-bold">No bills created today.</div>
            )}
          </div>

          {/* Section B — Today's Payments */}
          <div className="flex justify-between items-center mb-6 border-b border-gray-200 pb-2">
             <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest">Today's Payments</h2>
          </div>
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Invoice Number</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Customer Name</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Amount Received</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Mode</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">UTR / Reference</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Date</th>
                  <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Status</th>
                </tr>
              </thead>
              <tbody>
                {mappedPaymentsFeed.map((pmt) => (
                  <tr key={pmt.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="p-4 font-black text-gray-900">{pmt.bill_number}</td>
                    <td className="p-4 text-sm text-gray-600 font-medium">{pmt.customer_name}</td>
                    <td className="p-4 font-black text-green-600 text-right">{money(pmt.amount)}</td>
                    <td className="p-4 text-xs font-bold text-gray-600 uppercase">{pmt.payment_mode || 'N/A'}</td>
                    <td className="p-4 text-xs font-mono text-gray-500">{pmt.utr_reference || '-'}</td>
                    <td className="p-4 text-xs font-bold text-gray-600 uppercase">{pmt.payment_date || (pmt.created_at ? pmt.created_at.split('T')[0] : '-')}</td>
                    <td className="p-4">
                      <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase border ${pipelineStatusClass(pmt.status, pmt.status)}`}>
                        {pmt.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {mappedPaymentsFeed.length === 0 && (
              <div className="p-12 text-center text-gray-400 italic font-bold">No payments received today.</div>
            )}
          </div>
        </div>
"""
    text = text[:start_idx] + ui_replacement + text[end_idx:]
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print("UI Replacement successful.")
else:
    print("Block not found!")

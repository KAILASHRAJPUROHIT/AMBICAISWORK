import re
import os

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\frontend\src\pages\DashboardPage.tsx"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add Interfaces
interface_block = """
interface TodayBill {
  id: number;
  bill_number: string;
  customer_name: string;
  amount: number;
  payment_mode: string;
  status: string;
  invoice_date: string | null;
}

interface TodayPayment {
  id: number;
  invoice_number: string;
  customer_name: string;
  amount_received: number;
  payment_mode: string;
  utr_reference: string;
  payment_date: string | null;
  status: string;
}

const initialStats"""

content = content.replace("const initialStats", interface_block)

# 2. Add State
state_block = """  const [liveFeed, setLiveFeed] = useState<LiveInvoice[]>([]);
  const [paymentEvents, setPaymentEvents] = useState<LivePaymentEvent[]>([]);
  const [todayBills, setTodayBills] = useState<TodayBill[]>([]);
  const [todayPayments, setTodayPayments] = useState<TodayPayment[]>([]);"""

content = re.sub(r'const \[liveFeed, setLiveFeed\] = useState<LiveInvoice\[\]>\(\[\]\);\s*const \[paymentEvents, setPaymentEvents\] = useState<LivePaymentEvent\[\]>\(\[\]\);', state_block, content)

# 3. Update fetchData Endpoints
fetch_block = """        `${API_BASE}/api/admin/sms-status`,
        `${API_BASE}/api/live-payment-events`,
        `${API_BASE}/api/version`,
        `${API_BASE}/api/dashboard/today-bills`,
        `${API_BASE}/api/dashboard/today-payments`
      ];"""

content = re.sub(r'(`${API_BASE}/api/admin/sms-status`,\s*`${API_BASE}/api/live-payment-events`,\s*`${API_BASE}/api/version`\s*\];)', fetch_block, content)

# 4. Update fetchData Setting
set_data_block = """      if (responses[6] && responses[6].ok) {
         const vData = await (responses[6] as Response).json();
         setAppVersion(vData.version);
      }
      if (responses[7] && responses[7].ok) setTodayBills(await (responses[7] as Response).json());
      if (responses[8] && responses[8].ok) setTodayPayments(await (responses[8] as Response).json());"""

content = re.sub(r'if \(responses\[6\] && responses\[6\]\.ok\) \{\s*const vData = await \(responses\[6\] as Response\)\.json\(\);\s*setAppVersion\(vData\.version\);\s*\}', set_data_block, content)

# 5. Replace Recent Pipeline Activity UI
ui_pattern = r'<div className=\{stats\?.is_owner \? "lg:col-span-2" : "lg:col-span-3"\}>\s*<div className="flex justify-between items-center mb-6 border-b border-gray-200 pb-2">.*?<div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-6">'

replacement_ui = """<div className={stats?.is_owner ? "lg:col-span-2" : "lg:col-span-3"}>
          <div className="flex flex-col gap-8">
            {/* SECTION A - TODAY'S BILLS */}
            <div>
              <div className="flex justify-between items-center mb-4 border-b border-gray-200 pb-2">
                <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest">Section A — Today's Bills</h2>
              </div>
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="sticky top-0 bg-gray-50 z-10 shadow-sm border-b border-gray-100">
                      <tr>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Invoice Number</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Customer Name</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase text-right">Amount</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Payment Mode</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Invoice Date</th>
                        <th className="p-4 text-[10px] font-black text-gray-400 uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {todayBills.length > 0 ? todayBills.map((bill) => (
                        <tr key={bill.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                          <td className="p-4 font-black text-gray-900">{bill.bill_number}</td>
                          <td className="p-4 text-sm text-gray-600 font-medium">{bill.customer_name}</td>
                          <td className="p-4 font-black text-gray-900 text-right">{money(bill.amount)}</td>
                          <td className="p-4 text-xs font-bold text-gray-600">{bill.payment_mode}</td>
                          <td className="p-4 text-xs text-gray-500">{bill.invoice_date ? new Date(bill.invoice_date).toLocaleString() : 'N/A'}</td>
                          <td className="p-4">
                            <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase border ${pipelineStatusClass(bill.status, null)}`}>
                              {operatorLabel(bill.status)}
                            </span>
                          </td>
                        </tr>
                      )) : (
                        <tr><td colSpan={6} className="p-8 text-center text-gray-400 italic font-medium">No bills recorded for today.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* SECTION B - TODAY'S PAYMENTS */}
            <div>
              <div className="flex justify-between items-center mb-4 border-b border-gray-200 pb-2">
                <h2 className="text-sm font-black text-gray-400 uppercase tracking-widest">Section B — Today's Payments</h2>
              </div>
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="sticky top-0 bg-gray-50 z-10 shadow-sm border-b border-gray-100">
                      <tr>
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
                      {todayPayments.length > 0 ? todayPayments.map((payment) => (
                        <tr key={payment.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                          <td className="p-4 font-black text-gray-900">{payment.invoice_number}</td>
                          <td className="p-4 text-sm text-gray-600 font-medium">{payment.customer_name}</td>
                          <td className="p-4 font-black text-gray-900 text-right">{money(payment.amount_received)}</td>
                          <td className="p-4 text-xs font-bold text-gray-600">{payment.payment_mode}</td>
                          <td className="p-4 text-xs font-mono">{payment.utr_reference}</td>
                          <td className="p-4 text-xs text-gray-500">{payment.payment_date ? new Date(payment.payment_date).toLocaleString() : 'N/A'}</td>
                          <td className="p-4">
                            <span className={`text-[10px] font-black px-3 py-1 rounded-full uppercase border ${pipelineStatusClass(payment.status, null)}`}>
                              {operatorLabel(payment.status)}
                            </span>
                          </td>
                        </tr>
                      )) : (
                        <tr><td colSpan={7} className="p-8 text-center text-gray-400 italic font-medium">No payments recorded for today.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-6">"""

content = re.sub(ui_pattern, replacement_ui, content, flags=re.DOTALL)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("DashboardPage.tsx successfully patched")

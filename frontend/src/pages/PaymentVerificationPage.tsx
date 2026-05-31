import React, { useState, useEffect } from 'react';

interface Reconciliation {
  invoice_no: string;
  status: string;
  reason?: string;
  timestamp: string;
  details: any;
}

const PaymentVerificationPage: React.FC = () => {
  const [data, setData] = useState<Reconciliation[]>([]);
  const [comment, setComment] = useState('');

  useEffect(() => {
    // Mocking API call
    setData([
      {
        invoice_no: "SS/2026/196/",
        status: "RED",
        reason: "PAYMENT_TOTAL_MISMATCH",
        timestamp: new Date().toISOString(),
        details: { total: 12357.0, payments: 0.0 }
      },
      {
        invoice_no: "SS/2026/201/",
        status: "GREEN",
        reason: "EXACT_VERIFIED_MATCH",
        timestamp: new Date().toISOString(),
        details: { total: 9352.0, payments: 9352.0 }
      }
    ]);
  }, []);

  const handleAction = (invoiceNo: string, action: string) => {
    console.log(`Action: ${action} on ${invoiceNo} with comment: ${comment}`);
    alert(`Invoice ${invoiceNo} ${action}ed. Audit log created.`);
    setComment('');
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold mb-6 text-gray-800">Payment Verification Workflow</h1>
      
      <div className="grid gap-6">
        {data.map((item) => (
          <div key={item.invoice_no} className="bg-white p-4 rounded-lg shadow border-l-4 border-blue-500">
            <div className="flex justify-between items-start">
              <div>
                <h2 className="text-lg font-semibold">{item.invoice_no}</h2>
                <p className="text-sm text-gray-500">{item.timestamp}</p>
              </div>
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                item.status === 'GREEN' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
              }`}>
                {item.status}
              </span>
            </div>
            
            <div className="mt-4 text-sm text-gray-700">
              <p><strong>Reason:</strong> {item.reason || 'N/A'}</p>
              <p><strong>Total:</strong> ₹{item.details.total}</p>
              <p><strong>Verified Payments:</strong> ₹{item.details.payments}</p>
            </div>

            <div className="mt-4">
              <textarea 
                className="w-full p-2 border rounded text-sm" 
                placeholder="Add accountant comment..."
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <div className="flex gap-2 mt-2">
                <button 
                  onClick={() => handleAction(item.invoice_no, 'APPROVE')}
                  className="bg-green-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-green-700"
                >
                  Approve
                </button>
                <button 
                  onClick={() => handleAction(item.invoice_no, 'REJECT')}
                  className="bg-red-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-red-700"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default PaymentVerificationPage;

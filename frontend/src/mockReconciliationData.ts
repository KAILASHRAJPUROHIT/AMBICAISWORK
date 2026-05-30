export interface ReconciliationItem {
  id: string;
  date: string;
  customer: string;
  billNo: string;
  invoiceAmount: number;
  bankAmount: number;
  difference: number;
  source: string;
  matchConfidence: string;
  status: 'Verified' | 'Pending' | 'Delivered Before Payment' | 'Risk / Mismatch' | 'Cheque Pending' | 'Archived';
}

export const mockReconciliationData: ReconciliationItem[] = [
  {
    id: 'rec-001',
    date: '2023-01-15',
    customer: 'Alpha Corp',
    billNo: 'INV-2023-001',
    invoiceAmount: 12500.00,
    bankAmount: 12500.00,
    difference: 0.00,
    source: 'Prime ERP',
    matchConfidence: 'High',
    status: 'Verified',
  },
  {
    id: 'rec-002',
    date: '2023-01-16',
    customer: 'Beta Ltd',
    billNo: 'INV-2023-002',
    invoiceAmount: 8000.00,
    bankAmount: 7500.00,
    difference: 500.00,
    source: 'Bank Statement',
    matchConfidence: 'Medium',
    status: 'Risk / Mismatch',
  },
  {
    id: 'rec-003',
    date: '2023-01-17',
    customer: 'Gamma Inc',
    billNo: 'INV-2023-003',
    invoiceAmount: 5000.00,
    bankAmount: 0.00,
    difference: 5000.00,
    source: 'Email',
    matchConfidence: 'Low',
    status: 'Pending',
  },
];
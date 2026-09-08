export interface ReconciliationItem {
  id: string;
  billNo: string; // Changed from date to billNo for column mapping
  customer: string;
  invoiceAmount: number;
  bankAmount: number;
  difference: number;
  paymentMode: string; // New field, replaces 'source'
  matchConfidence: string;
  status: 'Verified' | 'Pending' | 'Delivered Before Payment' | 'Risk / Mismatch' | 'Cheque Pending' | 'Archived';
}

export const mockReconciliationData: ReconciliationItem[] = [
  {
    id: 'rec-001',
    billNo: 'INV-2023-001',
    customer: 'Customer A', // Generic name
    invoiceAmount: 12500.00,
    bankAmount: 12500.00,
    difference: 0.00,
    paymentMode: 'Bank Transfer',
    matchConfidence: 'High',
    status: 'Verified',
  },
  {
    id: 'rec-002',
    billNo: 'INV-2023-002',
    customer: 'Customer B', // Generic name
    invoiceAmount: 8000.00,
    bankAmount: 7500.00,
    difference: 500.00,
    paymentMode: 'Cash',
    matchConfidence: 'Medium',
    status: 'Risk / Mismatch',
  },
  {
    id: 'rec-003',
    billNo: 'INV-2023-003',
    customer: 'Customer C', // Generic name
    invoiceAmount: 5000.00,
    bankAmount: 0.00,
    difference: 5000.00,
    paymentMode: 'Cheque',
    matchConfidence: 'Low',
    status: 'Pending',
  },
];
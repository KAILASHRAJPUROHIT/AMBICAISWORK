export interface ReconciliationItem {
  id: string;
  billNo: string;
  customer: string;
  invoiceAmount: number;
  bankAmount: number;
  difference: number;
  paymentMode: string;
  matchConfidence: 'High' | 'Medium' | 'Low';
  status: 'Verified' | 'Pending' | 'Delivered Before Payment' | 'Risk / Mismatch' | 'Cheque Pending' | 'Archived';
}

export interface AuditLogItem {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  result: 'Success' | 'Failure' | 'Info';
  details: string;
}

export interface DashboardStats {
  totalBillsToday: number;
  verified: number;
  pendingReview: number;
  totalCollection: number;
  cashCollection: number;
  bankCollection: number;
  cardCollection: number;
  advanceCollection: number;
  matchAccuracy: number;
}

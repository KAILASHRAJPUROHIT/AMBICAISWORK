export interface ReconciliationPaymentEvidence {
  amount: number;
  mode: string;
  timestamp?: string | null;
  utrReference?: string | null;
  reference?: string | null;
  source?: string | null;
  proofUrl?: string | null;
  proofLabel?: string | null;
}

export interface ReconciliationItem {
  id: string;
  billId?: number | null;
  billNo: string;
  customer: string;
  invoiceAmount: number;
  bankAmount: number;
  difference: number;
  paymentMode: string;
  matchConfidence: 'High' | 'Medium' | 'Low';
  status: 'Verified' | 'Pending' | 'Delivered Before Payment' | 'Risk / Mismatch' | 'Cheque Pending' | 'Archived' | 'Advance Pending' | 'Ambiguous Match' | 'Realizing Cheque' | 'ACCOUNTANT APPROVAL REQUIRED';
  invoiceDate?: string | null;
  invoiceGeneratedAt?: string | null;
  invoiceTimestamp?: string | null;
  invoiceTimestampSource?: string | null;
  invoiceTimeRecorded?: boolean;
  invoiceProofUrl?: string | null;
  invoicePdfAvailable?: boolean;
  hasSpecialPaymentFlag?: boolean;
  paymentBreakdown: ReconciliationPaymentEvidence[];
  queueId?: number | string | null;
  queueStatus?: string | null;
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

export interface DashboardTodayKPIs {
  billsCreated: number;
  paymentsReceived: number;
  autoVerified: number;
  awaitingReview: number;
  pendingProof: number;
  escalations: number;
}

export interface DashboardTodayEvent {
  id: number;
  time: string;
  invoice_no: string;
  customer: string;
  amount: number;
  mode: string;
  proof: string;
  confidence: string;
  state: string;
}

export interface DashboardTodayResponse {
  kpis: DashboardTodayKPIs;
  recentEvents: DashboardTodayEvent[];
}

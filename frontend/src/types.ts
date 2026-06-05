export interface ReconciliationPaymentEvidence {
  amount: number;
  mode: string;
  timestamp?: string | null;
  utrReference?: string | null;
  reference?: string | null;
  source?: string | null;
  evidenceLink?: string | null;
  evidenceAvailable?: boolean;
}

export interface ReconciliationItem {
  id: string;
  billNo: string;
  customer: string;
  invoiceAmount: number;
  bankAmount: number;
  totalReceived: number;
  difference: number;
  outstanding: number;
  overpaid: number;
  differenceType: 'zero' | 'outstanding' | 'overpaid' | 'mismatch';
  paymentMode: string;
  matchConfidence: 'High' | 'Medium' | 'Low';
  status: 'CLEAR' | 'PARTIAL PAYMENT' | 'PENDING BANK' | 'RISK / MISMATCH' | 'REALIZING CHEQUE' | 'ADVANCE PENDING' | 'ACCOUNTANT APPROVAL REQUIRED';
  statusColor?: 'GREEN' | 'BLUE' | 'YELLOW' | 'RED' | 'PURPLE';
  reviewRequired?: boolean;
  statusExplanation?: string | null;
  invoiceDate?: string | null;
  invoiceGeneratedAt?: string | null;
  bankTime?: string | null;
  verifiedAt?: string | null;
  verifiedBy?: string | null;
  utrReference?: string | null;
  reviewAge?: string | null;
  sourceSystem?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  paymentBreakdown: ReconciliationPaymentEvidence[];
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

export interface ReconciliationPaymentEvidence {
  amount: number;
  mode: string;
  timestamp?: string | null;
  utrReference?: string | null;
  reference?: string | null;
  source?: string | null;
  proofUrl?: string | null;
  proofLabel?: string | null;
  proofExists?: boolean;
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
  matchConfidence: string;
  status: string;
  invoiceDate?: string | null;
  invoiceGeneratedAt?: string | null;
  invoiceTimestamp?: string | null;
  invoiceTimestampSource?: string | null;
  invoiceTimeRecorded: boolean;
  invoiceProofUrl?: string | null;
  invoicePdfAvailable: boolean;
  hasSpecialPaymentFlag: boolean;
  paymentBreakdown: ReconciliationPaymentEvidence[];
  queueId?: number | null;
  queueStatus?: string | null;
  proofStatus?: string;
  proofExists?: boolean;
  proofUrl?: string | null;
  reviewRequired?: boolean;
  integrityStatus?: string;
  verificationSource?: string;
  warningReason?: string;
  vetoes?: string[];
}

export interface LogEvent {
  id: number;
  timestamp: string;
  user_name: string;
  user_role: string;
  action: string;
  result: 'Success' | 'Failure' | 'Info';
  details: string;
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
  pendingProof: number;
  paymentTotals: Record<string, number>;
}

export interface PaymentBreakdown {
  payment_id: number;
  amount: number;
  mode: string;
  proof_label: string;
  proof_url: string;
  proof_exists: boolean;
  proof_source: string;
  utr_reference: string;
  timestamp: string;
  sources: Array<{type: string; details: string; status: string; url: string}>;
}

export interface DashboardTodayEvent {
  id: number;
  bill_id?: number;
  time: string;
  invoice_no: string;
  customer: string;
  amount: number;
  mode: string;
  proof: string;
  confidence: string;
  state: string;
  pdfUrl?: string;
  proofUrls?: string[];
  unifiedProofLabel?: string;
  sources?: Array<{type: string; details: string; status: string; url?: string}>;
  paymentBreakdown?: PaymentBreakdown[];
  stored_bill_status?: string;
  integrity_status?: string;
  verification_source?: string;
  dashboard_warning_reason?: string;
  proof_exists?: boolean;
  review_required?: boolean;
  vetoes?: string[];
}

export interface DashboardTodayResponse {
  totalBills: number;
  verifiedCount: number;
  unverifiedCount: number;
  matchAccuracy: number;
  recentEvents: DashboardTodayEvent[];
  kpis: DashboardTodayKPIs;
  integrity_errors?: number;
}

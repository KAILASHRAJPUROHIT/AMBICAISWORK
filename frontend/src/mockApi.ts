export interface Stat {
  label: string;
  value: string | number;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
}

export interface ReviewItem {
  id: string;
  date: string;
  amount: number;
  source: string;
  reason: string;
  status: 'Pending' | 'Flagged';
}

export interface EscalationItem {
  id: string;
  date: string;
  amount: number;
  source: string;
  urgency: 'High' | 'Medium' | 'Low';
  reason: string;
}

export interface ReportSummary {
  id: string;
  title: string;
  date: string;
  totalTransactions: number;
  totalAmount: number;
  reconciliationRate: string;
}

export const mockStats: Stat[] = [
  { label: 'Total Reconciled', value: '₹4,52,000', change: '+12%', trend: 'up' },
  { label: 'Pending Reviews', value: 24, change: '-3', trend: 'down' },
  { label: 'Escalations', value: 5, change: '+1', trend: 'up' },
  { label: 'Daily Accuracy', value: '98.5%', trend: 'neutral' },
];

export const mockReviews: ReviewItem[] = [
  { id: '1', date: '2023-10-27', amount: 1500, source: 'HDFC SMS', reason: 'Partial Match', status: 'Pending' },
  { id: '2', date: '2023-10-27', amount: 5000, source: 'ICICI Email', reason: 'Unrecognized Vendor', status: 'Flagged' },
  { id: '3', date: '2023-10-26', amount: 250, source: 'Paytm QR', reason: 'Duplicate entry', status: 'Pending' },
];

export const mockEscalations: EscalationItem[] = [
  { id: 'E1', date: '2023-10-27', amount: 125000, source: 'RTGS', urgency: 'High', reason: 'Large amount mismatch' },
  { id: 'E2', date: '2023-10-26', amount: 45000, source: 'Bank Statement', urgency: 'Medium', reason: 'Bounced cheque' },
];

export const mockReports: ReportSummary[] = [
  { id: 'R1', title: 'Daily Summary - Oct 27', date: '2023-10-27', totalTransactions: 145, totalAmount: 850000, reconciliationRate: '97%' },
  { id: 'R2', title: 'Daily Summary - Oct 26', date: '2023-10-26', totalTransactions: 132, totalAmount: 720000, reconciliationRate: '99%' },
];

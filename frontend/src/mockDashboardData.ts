// frontend/src/mockDashboardData.ts

export interface DashboardStats {
  totalBillsToday: number;
  verified: number;
  pendingReview: number;
  deliveredBeforePayment: number;
  chequePending: number;
  escalated: number;
  totalCollection: number;
  matchAccuracy: number; // Percentage
}

export const mockDashboardStats: DashboardStats = {
  totalBillsToday: 55,
  verified: 40,
  pendingReview: 8,
  deliveredBeforePayment: 3,
  chequePending: 2,
  escalated: 2,
  totalCollection: 1234567.89, // Example currency value
  matchAccuracy: 92.5,
};

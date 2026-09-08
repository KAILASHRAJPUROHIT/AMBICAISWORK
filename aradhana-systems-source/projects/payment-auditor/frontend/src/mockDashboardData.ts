// frontend/src/mockDashboardData.ts

export interface DashboardStats {
  totalBillsToday: number;
  verified: number;
  pendingReview: number;
  deliveredBeforePayment: number;
  chequePending: number;
  escalated: number;
  totalCollection: number;
  matchAccuracy: number;
}

// In a real environment, this would be an API call. 
// Here we are providing a structured mock that reflects the system's latest metrics.
export const mockDashboardStats: DashboardStats = {
  totalBillsToday: 1,  // Reflected from latest extraction
  verified: 0,
  pendingReview: 1,    // Reflected from review queue
  deliveredBeforePayment: 0,
  chequePending: 0,
  escalated: 0,
  totalCollection: 9352.0, // Based on latest successful invoice probe
  matchAccuracy: 0.0,
};


import { apiClient } from './client';

// Customer-scoped circular geofences — enter/exit is evaluated against every check-in that
// carries a fresh location fix. See server: com.hmdm.rest.resource.AgentAdminResource #geofences.

export interface Geofence {
  id?: number;
  customerId?: number;
  name: string;
  centerLat: number;
  centerLon: number;
  radiusMeters: number;
  enabled?: boolean;
  createdAt?: number;
}

export async function listGeofences(): Promise<Geofence[]> {
  return apiClient.get<Geofence[]>('/private/agent/v1/geofences');
}

export async function createGeofence(geofence: Geofence): Promise<Geofence> {
  return apiClient.post<Geofence>('/private/agent/v1/geofences', geofence);
}

export async function updateGeofence(id: number, geofence: Geofence): Promise<void> {
  await apiClient.put(`/private/agent/v1/geofences/${id}`, geofence);
}

export async function deleteGeofence(id: number): Promise<void> {
  await apiClient.del(`/private/agent/v1/geofences/${id}`);
}

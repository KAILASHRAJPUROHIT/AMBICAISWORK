import { apiClient } from './client';

// In-store positioning. The floor plan (geometry + picture) and the surveyed Wi-Fi points are stored per customer:
//   GET/PUT /rest/private/indoor/v1/map      DELETE /rest/private/indoor/v1/fingerprints[/{id}]
// Devices run the positioning engine themselves and report their position in telemetry (dynamic.indoor).

export interface IndoorZone {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface IndoorPlan {
  widthM: number;
  heightM: number;
  /** Compass bearing of the plan's "up" direction (0 = the top of the picture points north). */
  northDeg: number;
  /** Each wall is [x1, y1, x2, y2] in metres. */
  walls: number[][];
  zones: IndoorZone[];
}

export interface IndoorPoint {
  id: number;
  x: number;
  y: number;
  /** JSON text: { bssid: dBm }. */
  rssi: string;
  mag?: number | null;
  createdAt: number;
  createdBy?: string | null;
}

export interface IndoorMapResponse {
  plan: string | null;
  image: string | null;
  updatedAt: number | null;
  points: IndoorPoint[];
}

export interface IndoorMapState {
  plan: IndoorPlan | null;
  image: string | null;
  updatedAt: number | null;
  points: IndoorPoint[];
}

/** A device's own position estimate, from telemetry (dynamic.indoor). */
export interface IndoorFix {
  x: number;
  y: number;
  spreadM: number;
  zone?: string | null;
  at: number;
}

export const EMPTY_PLAN: IndoorPlan = { widthM: 20, heightM: 10, northDeg: 0, walls: [], zones: [] };

export async function getIndoorMap(): Promise<IndoorMapState> {
  const r = await apiClient.get<IndoorMapResponse>('/private/indoor/v1/map');
  let plan: IndoorPlan | null = null;
  if (r?.plan) {
    try {
      const p = JSON.parse(r.plan) as Partial<IndoorPlan>;
      plan = {
        widthM: Number(p.widthM) || EMPTY_PLAN.widthM,
        heightM: Number(p.heightM) || EMPTY_PLAN.heightM,
        northDeg: Number(p.northDeg) || 0,
        walls: Array.isArray(p.walls) ? p.walls : [],
        zones: Array.isArray(p.zones) ? p.zones : [],
      };
    } catch {
      plan = null;
    }
  }
  return { plan, image: r?.image ?? null, updatedAt: r?.updatedAt ?? null, points: r?.points ?? [] };
}

/** Saves the plan. Pass `image` to replace the picture, '' to remove it, or leave it undefined to keep the stored one. */
export async function saveIndoorMap(plan: IndoorPlan, image?: string | null): Promise<void> {
  const body: Record<string, unknown> = { plan: JSON.stringify(plan) };
  if (image !== undefined) body.image = image ?? '';
  await apiClient.put('/private/indoor/v1/map', body);
}

export async function deleteIndoorPoint(id: number): Promise<void> {
  await apiClient.del(`/private/indoor/v1/fingerprints/${id}`);
}

export async function clearIndoorSurvey(): Promise<void> {
  await apiClient.del('/private/indoor/v1/fingerprints');
}

/** Reads a device's indoor fix out of its telemetry snapshot, or null. */
export function indoorFixOf(dynamic: Record<string, unknown> | undefined): IndoorFix | null {
  const f = dynamic?.indoor as Partial<IndoorFix> | undefined;
  if (!f || typeof f.x !== 'number' || typeof f.y !== 'number') return null;
  return { x: f.x, y: f.y, spreadM: Number(f.spreadM) || 0, zone: f.zone ?? null, at: Number(f.at) || 0 };
}

/** Shrinks a chosen picture so the stored plan stays small: longest side 1600 px, JPEG. */
export function shrinkImage(file: File, maxSide = 1600): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      const ctx = c.getContext('2d');
      if (!ctx) { URL.revokeObjectURL(url); reject(new Error('This browser cannot read the picture')); return; }
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', 0.82));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('That file is not a picture the browser can open')); };
    img.src = url;
  });
}

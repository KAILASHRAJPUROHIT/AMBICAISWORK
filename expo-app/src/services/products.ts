import data from '@/assets/products.json';
import { productImages } from '@/services/productImages';

/* ── 3D types ─────────────────────────────────────────────────────────── */

export type MaterialVariant = {
  id: string;
  label: string;
  metalColor: 'yellow' | 'rose' | 'white';
  purity: 18 | 22;
  glbUrl: string;
  hexAccent?: string;
};

export type PurityOption = {
  karat: 18 | 22;
  label: string;
  rateMultiplier: number;
};

export type StoneDetail = {
  type: string;
  count: number;
  totalCaratWeight: number;
  clarity: string | null;
  setting: string;
};

export type CameraPreset = {
  position: [number, number, number];
  target: [number, number, number];
  fov: number;
  near: number;
  far: number;
};

export type Product3DConfig = {
  glbUrl: string | null;
  posterImageKey: string | null;
  materialVariants: MaterialVariant[];
  purityOptions: PurityOption[];
  totalWeight: number | null;
  stones: StoneDetail[];
  cameraPreset: CameraPreset;
  arEligible: boolean;
  availability: 'in_stock' | 'made_to_order' | 'enquiry_only';
  lod: {
    low: string;
    medium: string;
    high: string;
  };
  dimensions: { width: number; height: number; depth: number };
};

/* ── Product type ─────────────────────────────────────────────────────── */

export type Product = {
  id: string;
  label: string;
  category: string;
  categoryName: string;
  karat: number | null;
  weight: number | null;
  imageKey: string;
  /** 3D configuration. Null = 2D-only product (existing behaviour). */
  threeD: Product3DConfig | null;
};

export const products = (data as any[]).map((p) => ({
  id: p.id as string,
  label: p.label as string,
  category: (p.categoryName as string).toLowerCase(),
  categoryName: p.categoryName as string,
  karat: p.karat as number | null,
  weight: p.weight as number | null,
  imageKey: p.imageKey as string,
  threeD: (p.threeD as Product3DConfig | null) ?? null,
}));

/* ── Helpers ──────────────────────────────────────────────────────────── */

export function imageFor(p: Product): number | undefined {
  return productImages[p.imageKey];
}

export function is3DEnabled(p: Product): boolean {
  return p.threeD !== null && p.threeD.glbUrl !== null;
}

export function heroProducts(): Product[] {
  return products.filter(is3DEnabled);
}

export function categories(): { key: string; name: string; count: number }[] {
  const map = new Map<string, { name: string; count: number }>();
  for (const p of products) {
    const cur = map.get(p.category);
    if (cur) cur.count += 1;
    else map.set(p.category, { name: p.categoryName, count: 1 });
  }
  return [...map.entries()]
    .map(([key, v]) => ({ key, name: v.name, count: v.count }))
    .sort((a, b) => b.count - a.count);
}

export function byCategory(key: string): Product[] {
  if (key === 'all') return products;
  return products.filter((p) => p.category === key);
}

export function getById(id: string): Product | undefined {
  return products.find((p) => p.id === id);
}

export function searchProducts(query: string): Product[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return products.filter(
    (p) =>
      p.label.toLowerCase().includes(q) ||
      p.categoryName.toLowerCase().includes(q) ||
      p.category.toLowerCase().includes(q),
  );
}

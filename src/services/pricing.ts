import type { RateSnapshot } from '@/services/rates';
import type { Product } from '@/services/products';

/**
 * Shared price estimation service.
 * Single source of truth for all rate calculations across the app.
 * Do NOT duplicate rate math in screens.
 */

export type PriceBreakdown = {
  metalValue: number;
  karatLabel: string;
  ratePer10g: number;
  weight: number;
  disclaimer: string;
};

const DISCLAIMER =
  'Estimated metal value only. Excludes making charges, stones, GST, and final counter weight.';

/**
 * Compute the estimated metal value for a product at a given rate.
 *
 * @param weight - weight in grams
 * @param karat  - 18 or 22
 * @param snap   - live rate snapshot
 * @returns PriceBreakdown or null if data incomplete
 */
export function estimateMetalValue(
  weight: number | null,
  karat: number | null,
  snap: RateSnapshot | null,
): PriceBreakdown | null {
  if (!weight || !karat || !snap) return null;

  const rate22 = snap.published.rate22kt;
  if (!rate22 || rate22 <= 0) return null;

  let ratePer10g: number;
  let karatLabel: string;

  if (karat === 18) {
    ratePer10g = Math.round(rate22 * 0.75);
    karatLabel = '18K';
  } else if (karat === 22) {
    ratePer10g = rate22;
    karatLabel = '22K';
  } else {
    return null;
  }

  const metalValue = Math.round((weight * ratePer10g) / 10);

  return {
    metalValue,
    karatLabel,
    ratePer10g,
    weight,
    disclaimer: DISCLAIMER,
  };
}

/**
 * Estimate for a 3D-enabled product using its explicit purity options.
 * Falls back to product.karat if no purityOptions defined.
 */
export function estimate3DProduct(
  product: Product,
  selectedKarat: 18 | 22,
  snap: RateSnapshot | null,
): PriceBreakdown | null {
  const weight = product.threeD?.totalWeight ?? product.weight;
  const karat = selectedKarat;
  return estimateMetalValue(weight, karat, snap);
}

/**
 * Format INR currency value.
 */
export function formatInr(value: number): string {
  return value.toLocaleString('en-IN');
}

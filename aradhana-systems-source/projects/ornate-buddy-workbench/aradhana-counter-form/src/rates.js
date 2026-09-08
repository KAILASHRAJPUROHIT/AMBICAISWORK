import fs from 'node:fs';
import path from 'node:path';

const number = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export function normalizePurity(raw) {
  const n = number(raw);
  if (n == null || n <= 0) return null;
  // Accept 91.6, 91.67, 916, 999, 75, 750, etc.
  if (n <= 100) return n * 10;
  return n;
}

export function normalizeRemoteState(state, gstPercent = 3) {
  if (!state || typeof state !== 'object') throw new Error('Rate API returned an invalid payload');

  const p = state.published || {};
  const silverP = state.silver?.published || {};

  const gold = {
    ok: Boolean(state.ok && p.rate999 != null),
    rate999: number(p.rate999),
    rate24kt: number(p.rate24kt ?? p.rate999),
    rate999Loaded: number(p.rate999Loaded ?? p.rate999),
    rate22kt: number(p.rate22kt),
    rate22ktWithGst: number(p.rate22ktWithGst),
    variants: Array.isArray(p.variants) ? p.variants : [],
    unit: p.unit || 'per 10 g',
    status: p.status || state.live?.status || 'UNKNOWN',
    confidence: number(p.confidence ?? state.live?.confidence),
    updatedAt: number(p.at ?? state.live?.at),
    updatedAtIst: p.atIst || null
  };

  const silver = {
    ok: Boolean(state.silver?.ok && silverP.pure != null),
    silverBase: number(silverP.silverBase),
    pure: number(silverP.pure),
    ornament: number(silverP.ornament),
    ornamentDiscountPct: number(silverP.ornamentDiscountPct),
    unit: silverP.unit || 'per kg',
    status: silverP.status || state.silver?.live?.status || 'UNKNOWN',
    confidence: number(silverP.confidence ?? state.silver?.live?.confidence),
    updatedAt: number(silverP.at ?? state.silver?.live?.at),
    updatedAtIst: silverP.atIst || null
  };

  return { gold, silver, gstPercent, fetchedAt: Date.now() };
}

export function goldRateForPurity(snapshot, purityRaw) {
  const purity = normalizePurity(purityRaw);
  if (!snapshot?.gold?.ok || purity == null) return null;
  const g = snapshot.gold;

  // Preserve the monitor's business formulas for the standard sale purities.
  if (purity === 999 && g.rate24kt != null) return { ratePer10g: g.rate24kt, source: '24KT business rate' };
  if (purity === 916 && g.rate22kt != null) return { ratePer10g: g.rate22kt, source: '22KT business rate' };
  if (purity === 750) {
    const v = g.variants.find((x) => String(x.key).toLowerCase() === '18kt' || /18\s*kt/i.test(String(x.label)));
    if (v && number(v.rate) != null) return { ratePer10g: number(v.rate), source: '18KT business rate' };
  }

  // Custom purity: use the monitor's loaded 999 base and scale by fineness.
  if (g.rate999Loaded != null) {
    return { ratePer10g: g.rate999Loaded * (purity / 1000), source: `custom ${purity} fineness` };
  }
  return null;
}

export function silverRateForPurity(snapshot, purityRaw) {
  const purity = normalizePurity(purityRaw);
  if (!snapshot?.silver?.ok || purity == null) return null;
  const s = snapshot.silver;

  if (purity === 999 && s.pure != null) return { ratePerKg: s.pure, source: 'Silver Pure business rate' };
  // The monitor's ornament rate is a 2.5% reduction from pure = 975-equivalent business rate.
  if (purity === 975 && s.ornament != null) return { ratePerKg: s.ornament, source: 'Silver Ornament business rate' };
  if (s.pure != null) return { ratePerKg: s.pure * (purity / 999), source: `custom ${purity} fineness` };
  return null;
}

export function calculateNewLine({ metal, weight, purity }, snapshot) {
  const w = number(weight);
  const p = normalizePurity(purity);
  if (!w || w <= 0 || !p) return null;

  const gstPercent = number(snapshot?.gstPercent) ?? 3;
  let rateInfo;
  let metalValue;
  let displayRate;
  let rateUnit;

  if (metal === 'gold') {
    rateInfo = goldRateForPurity(snapshot, p);
    if (!rateInfo) return null;
    metalValue = (rateInfo.ratePer10g / 10) * w;
    displayRate = rateInfo.ratePer10g;
    rateUnit = 'per 10 g';
  } else if (metal === 'silver') {
    rateInfo = silverRateForPurity(snapshot, p);
    if (!rateInfo) return null;
    metalValue = (rateInfo.ratePerKg / 1000) * w;
    displayRate = rateInfo.ratePerKg;
    rateUnit = 'per kg';
  } else {
    return null;
  }

  const gst = metalValue * (gstPercent / 100);
  const total = metalValue + gst;
  return {
    metal,
    weight: w,
    purity: p,
    rate: Number(displayRate.toFixed(2)),
    rateUnit,
    rateSource: rateInfo.source,
    metalValue: Number(metalValue.toFixed(2)),
    gstPercent,
    gst: Number(gst.toFixed(2)),
    total: Number(total.toFixed(2))
  };
}

export class RateService {
  constructor(cfg, rootDir, log = console.log) {
    this.cfg = cfg;
    this.rootDir = rootDir;
    this.log = log;
    this.snapshot = null;
    this.lastError = null;
    this.timer = null;
    this.cacheFile = path.join(rootDir, 'data', 'rates-cache.json');
    this.loadCache();
  }

  loadCache() {
    try {
      const cached = JSON.parse(fs.readFileSync(this.cacheFile, 'utf8'));
      if (cached && cached.gold && cached.silver) this.snapshot = { ...cached, cached: true };
    } catch {}
  }

  saveCache() {
    try { fs.writeFileSync(this.cacheFile, JSON.stringify(this.snapshot, null, 2)); } catch {}
  }

  async refresh() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.cfg.requestTimeoutMs || 60000);
    try {
      const res = await fetch(this.cfg.url, {
        signal: controller.signal,
        headers: { 'accept': 'application/json', 'cache-control': 'no-cache' }
      });
      if (!res.ok) throw new Error(`rate API HTTP ${res.status}`);
      const payload = await res.json();
      const normalized = normalizeRemoteState(payload, this.cfg.gstPercent ?? 3);
      if (!normalized.gold.ok) throw new Error('gold rate is not verified/available');
      if (!normalized.silver.ok) throw new Error('silver rate is not verified/available');
      this.snapshot = { ...normalized, cached: false };
      this.lastError = null;
      this.saveCache();
      return this.snapshot;
    } catch (err) {
      this.lastError = err.name === 'AbortError' ? 'rate API request timed out' : err.message;
      this.log(`[rates] ${this.lastError}`);
      return this.snapshot;
    } finally {
      clearTimeout(timeout);
    }
  }

  isFresh(snapshot = this.snapshot) {
    if (!snapshot) return false;
    const latest = Math.min(
      snapshot.gold?.updatedAt || 0,
      snapshot.silver?.updatedAt || 0
    );
    if (!latest) return false;
    return Date.now() - latest <= (this.cfg.maxRateAgeMs || 300000);
  }

  publicStatus() {
    return {
      ...this.snapshot,
      sourceUrl: this.cfg.url,
      fresh: this.isFresh(),
      error: this.lastError
    };
  }

  start() {
    this.refresh();
    this.timer = setInterval(() => this.refresh(), this.cfg.refreshMs || 10000);
    this.timer.unref?.();
  }

  stop() { if (this.timer) clearInterval(this.timer); }
}

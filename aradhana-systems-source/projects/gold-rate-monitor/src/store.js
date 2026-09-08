/** In-memory state, history ring buffer, and daily CSV audit log. */

import fs from 'node:fs';
import path from 'node:path';
import { istDateKey, istPretty } from './time.js';

/** Keep this in sync with server.js's VALID_LAYOUTS and board.html's picker. */
const VALID_BOARD_LAYOUTS = ['fullbleed', 'diagonal', 'medallion', 'bands', 'waterfall'];

/**
 * Apply the business formula: (999 SELL + premiumAdd) x purityFactor = 22KT ex-GST.
 * The +premiumAdd is a flat rupee loading on top of the raw Safari 999 rate, applied
 * BEFORE the 95% purity multiply. It only affects the derived business rate - the
 * validation checks (GST invariant, Kaka cross-check, etc.) still run on the raw,
 * unmodified rate999 so accuracy verification is unaffected.
 */
export function deriveRates(rate999, cfg) {
  const b = cfg.business;
  const premiumAdd = b.premiumAdd || 0;
  const premiumAdd24kt = b.premiumAdd24kt || 0;
  const rate24kt = rate999 + premiumAdd24kt;
  const loaded = rate999 + premiumAdd;
  const raw = loaded * b.purityFactor;
  let value = raw;
  if (b.rounding === 'nearest1') value = Math.round(raw);
  else if (b.rounding === 'up10') value = Math.ceil(raw / 10) * 10;
  else if (b.rounding === 'nearest10') value = Math.round(raw / 10) * 10;
  // 'none' -> exact, unrounded

  const applyRounding = (n) => {
    if (b.rounding === 'nearest1') return Math.round(n);
    if (b.rounding === 'up10') return Math.ceil(n / 10) * 10;
    if (b.rounding === 'nearest10') return Math.round(n / 10) * 10;
    return n;
  };

  // Other karats share the same loaded base (999 + premiumAdd), just a
  // different purity multiplier - e.g. 18KT = loaded x 0.77.
  const variants = (b.variants || []).map((v) => {
    const vRaw = loaded * v.purityFactor;
    return {
      key: v.key,
      label: v.label,
      purityFactor: v.purityFactor,
      rate: applyRounding(vRaw),
      rateExact: Number(vRaw.toFixed(4)),
      rateWithGst: Number((applyRounding(vRaw) * (1 + b.gstPercent / 100)).toFixed(2)),
    };
  });

  return {
    rate999,
    premiumAdd24kt,
    rate24kt,
    premiumAdd,
    rate999Loaded: loaded,
    rate22kt: value,
    rate22ktExact: Number(raw.toFixed(4)),
    rate22ktWithGst: Number((value * (1 + b.gstPercent / 100)).toFixed(2)),
    purityFactor: b.purityFactor,
    rounding: b.rounding,
    variants,
  };
}

/**
 * Silver formula: Pure = SILVER COSTING + premiumAdd; Ornament = Pure x (1 - discount%).
 * Safari's Silver Rates tab has no per-product sell row, so the base is the
 * COSTING figure - the only priced INR value they publish there.
 */
export function deriveSilverRates(silverBase, cfg) {
  const s = cfg.silver.business;
  const premiumAdd = s.premiumAdd || 0;
  const pureRaw = silverBase + premiumAdd;
  const ornamentRaw = pureRaw * (1 - s.ornamentDiscountPct / 100);

  const applyRounding = (n) => {
    if (s.rounding === 'nearest1') return Math.round(n);
    if (s.rounding === 'up10') return Math.ceil(n / 10) * 10;
    if (s.rounding === 'nearest10') return Math.round(n / 10) * 10;
    return n;
  };

  return {
    silverBase,
    premiumAdd,
    pure: applyRounding(pureRaw),
    pureExact: Number(pureRaw.toFixed(4)),
    ornament: applyRounding(ornamentRaw),
    ornamentExact: Number(ornamentRaw.toFixed(4)),
    ornamentDiscountPct: s.ornamentDiscountPct,
    unit: s.unit,
    rounding: s.rounding,
  };
}

export class Store {
  constructor(cfg, rootDir) {
    this.cfg = cfg;
    this.rootDir = rootDir;
    this.dataDir = path.join(rootDir, 'data');
    this.logDir = path.join(rootDir, 'logs');
    fs.mkdirSync(this.dataDir, { recursive: true });
    fs.mkdirSync(this.logDir, { recursive: true });

    /** Most recent tick, verified or not. */
    this.latest = null;
    /** Most recent tick that passed every blocking check - what we publish. */
    this.lastVerified = null;
    /** Rolling history of verified rates for the chart. */
    this.history = [];
    /** Spike-quarantine carry-over between ticks. */
    this.quarantine = { pending: null, count: 0 };
    /** When the verified 999 rate last actually changed. */
    this.lastChangeAt = null;

    this.stats = {
      startedAt: Date.now(),
      ticks: 0,
      verified: 0,
      blocked: 0,
      warnings: 0,
      fetchErrors: 0,
      consecutiveFetchErrors: 0,
      lastError: null,
    };

    // Silver runs as a separate instrument with its own state, so a gold-side
    // block never holds up silver publishing (or vice versa).
    this.silverLatest = null;
    this.silverLastVerified = null;
    this.silverHistory = [];
    this.silverQuarantine = { pending: null, count: 0 };
    this.silverLastChangeAt = null;
    this.silverStats = {
      ticks: 0, verified: 0, blocked: 0, warnings: 0, fetchErrors: 0, consecutiveFetchErrors: 0, lastError: null,
    };

    this.subscribers = new Set();
    this._csvDay = null;
    this._csvStream = null;
    this._csvSilverDay = null;
    this._csvSilverStream = null;

    /** Central board-display control: which layout every /board.html client
     * shows, and a token that bumps to force them all to reload. Persisted
     * so a restart doesn't reset every kiosk back to the default layout. */
    this.boardControl = { layout: 'fullbleed', refreshToken: Date.now() };
    this._loadBoardControl();

    this._loadHistory();
  }

  get _boardControlFile() {
    return path.join(this.dataDir, 'board-control.json');
  }

  _loadBoardControl() {
    try {
      const raw = fs.readFileSync(this._boardControlFile, 'utf8');
      const parsed = JSON.parse(raw);
      // Fall back to the default if the persisted value predates a layout
      // set change (e.g. the old 'grid'/'ledger'/'hero' names) rather than
      // resurrecting a layout that no longer exists.
      if (parsed && VALID_BOARD_LAYOUTS.includes(parsed.layout)) {
        this.boardControl = { layout: parsed.layout, refreshToken: parsed.refreshToken || Date.now() };
      }
    } catch {
      // no persisted control state yet - defaults above stand.
    }
  }

  _saveBoardControl() {
    try {
      fs.writeFileSync(this._boardControlFile, JSON.stringify(this.boardControl));
    } catch (err) {
      console.error('[store] could not persist board control:', err.message);
    }
  }

  /** Sets the layout every board client shows on its next poll (~1s). */
  setBoardLayout(layout) {
    this.boardControl = { ...this.boardControl, layout };
    this._saveBoardControl();
    this.broadcast();
  }

  /** Bumps the refresh token, causing every board client to reload on its next poll. */
  forceBoardRefresh() {
    this.boardControl = { ...this.boardControl, refreshToken: Date.now() };
    this._saveBoardControl();
    this.broadcast();
  }

  /* ------------------------------------------------------------ persistence */

  get _historyFile() {
    return path.join(this.dataDir, 'history.json');
  }

  get _silverHistoryFile() {
    return path.join(this.dataDir, 'silver-history.json');
  }

  _loadHistory() {
    try {
      const raw = fs.readFileSync(this._historyFile, 'utf8');
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        this.history = parsed.slice(-this.cfg.storage.historyPoints);
        const last = this.history[this.history.length - 1];
        if (last) this.lastChangeAt = last.t;
      }
    } catch {
      this.history = [];
    }
    try {
      const raw = fs.readFileSync(this._silverHistoryFile, 'utf8');
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        this.silverHistory = parsed.slice(-this.cfg.storage.historyPoints);
        const last = this.silverHistory[this.silverHistory.length - 1];
        if (last) this.silverLastChangeAt = last.t;
      }
    } catch {
      this.silverHistory = [];
    }
  }

  saveHistory() {
    try {
      fs.writeFileSync(this._historyFile, JSON.stringify(this.history));
      fs.writeFileSync(this._silverHistoryFile, JSON.stringify(this.silverHistory));
    } catch (err) {
      console.error('[store] could not persist history:', err.message);
    }
  }

  _csv(record) {
    if (!this.cfg.storage.csvLog) return;
    const day = istDateKey();
    if (day !== this._csvDay) {
      if (this._csvStream) this._csvStream.end();
      const file = path.join(this.logDir, `rates-${day}.csv`);
      const fresh = !fs.existsSync(file);
      this._csvStream = fs.createWriteStream(file, { flags: 'a' });
      if (fresh) {
        this._csvStream.write(
          'iso_utc,ist_time,status,confidence,rate_999,rate_22kt,kaka_999,kaka_delta_pct,blocking,warnings\n'
        );
      }
      this._csvDay = day;
    }
    const esc = (s) => `"${String(s == null ? '' : s).replace(/"/g, '""')}"`;
    this._csvStream.write([
      new Date(record.t).toISOString(),
      esc(istPretty(new Date(record.t))),
      record.status,
      record.confidence,
      record.rate999,
      record.rate22kt,
      record.kaka == null ? '' : record.kaka,
      record.kakaDelta == null ? '' : record.kakaDelta,
      esc((record.blocking || []).map((b) => b.id).join('|')),
      esc((record.warnings || []).map((w) => w.id).join('|')),
    ].join(',') + '\n');
  }

  _csvSilver(record) {
    if (!this.cfg.storage.csvLog) return;
    const day = istDateKey();
    if (day !== this._csvSilverDay) {
      if (this._csvSilverStream) this._csvSilverStream.end();
      const file = path.join(this.logDir, `silver-${day}.csv`);
      const fresh = !fs.existsSync(file);
      this._csvSilverStream = fs.createWriteStream(file, { flags: 'a' });
      if (fresh) {
        this._csvSilverStream.write(
          'iso_utc,ist_time,status,confidence,silver_base,silver_pure,silver_ornament,kaka_999,kaka_delta_pct,blocking,warnings\n'
        );
      }
      this._csvSilverDay = day;
    }
    const esc = (s) => `"${String(s == null ? '' : s).replace(/"/g, '""')}"`;
    this._csvSilverStream.write([
      new Date(record.t).toISOString(),
      esc(istPretty(new Date(record.t))),
      record.status,
      record.confidence,
      record.silverBase,
      record.pure,
      record.ornament,
      record.kaka == null ? '' : record.kaka,
      record.kakaDelta == null ? '' : record.kakaDelta,
      esc((record.blocking || []).map((b) => b.id).join('|')),
      esc((record.warnings || []).map((w) => w.id).join('|')),
    ].join(',') + '\n');
  }

  /* ----------------------------------------------------------------- ticks */

  recordTick(tick) {
    this.stats.ticks++;
    this.latest = tick;

    if (tick.verdict.status === 'BLOCKED') {
      this.stats.blocked++;
    } else {
      this.stats.verified++;
      if (tick.verdict.status === 'VERIFIED_WITH_WARNINGS') this.stats.warnings++;

      const changed = !this.lastVerified || this.lastVerified.rates.rate999 !== tick.rates.rate999;
      if (changed) {
        this.lastChangeAt = tick.t;
        this.history.push({
          t: tick.t,
          v: tick.rates.rate999,
          k: tick.kaka == null ? null : tick.kaka,
        });
        if (this.history.length > this.cfg.storage.historyPoints) {
          this.history.splice(0, this.history.length - this.cfg.storage.historyPoints);
        }
      }
      this.lastVerified = tick;

      // Audit-log only on change, plus the first tick - not 3600 identical rows/hour.
      if (changed) this._csv(tick.csvRecord);
    }

    this.broadcast();
    return tick;
  }

  recordSilverTick(tick) {
    this.silverStats.ticks++;
    this.silverLatest = tick;

    if (tick.verdict.status === 'BLOCKED') {
      this.silverStats.blocked++;
    } else {
      this.silverStats.verified++;
      if (tick.verdict.status === 'VERIFIED_WITH_WARNINGS') this.silverStats.warnings++;

      const changed = !this.silverLastVerified || this.silverLastVerified.rates.silverBase !== tick.rates.silverBase;
      if (changed) {
        this.silverLastChangeAt = tick.t;
        this.silverHistory.push({ t: tick.t, v: tick.rates.silverBase, k: tick.kaka == null ? null : tick.kaka });
        if (this.silverHistory.length > this.cfg.storage.historyPoints) {
          this.silverHistory.splice(0, this.silverHistory.length - this.cfg.storage.historyPoints);
        }
      }
      this.silverLastVerified = tick;

      if (changed) this._csvSilver(tick.csvRecord);
    }

    this.broadcast();
    return tick;
  }

  recordSilverFetchError(message) {
    this.silverStats.fetchErrors++;
    this.silverStats.consecutiveFetchErrors++;
    this.silverStats.lastError = { message, at: Date.now() };
    this.broadcast();
  }

  clearSilverFetchError() {
    this.silverStats.consecutiveFetchErrors = 0;
  }

  recordFetchError(message) {
    this.stats.fetchErrors++;
    this.stats.consecutiveFetchErrors++;
    this.stats.lastError = { message, at: Date.now() };
    this.broadcast();
  }

  clearFetchError() {
    this.stats.consecutiveFetchErrors = 0;
  }

  /* ------------------------------------------------------------------- SSE */

  subscribe(fn) {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }

  broadcast() {
    if (this.subscribers.size === 0) return;
    const payload = this.publicState();
    for (const fn of this.subscribers) {
      try { fn(payload); } catch { /* a dead client must not break the loop */ }
    }
  }

  /** The shape served to the live page and the JSON API. */
  publicState() {
    const v = this.lastVerified;
    const l = this.latest;
    return {
      ok: !!v,
      published: v ? {
        rate999: v.rates.rate999,
        premiumAdd24kt: v.rates.premiumAdd24kt,
        rate24kt: v.rates.rate24kt,
        premiumAdd: v.rates.premiumAdd,
        rate999Loaded: v.rates.rate999Loaded,
        rate22kt: v.rates.rate22kt,
        rate22ktExact: v.rates.rate22ktExact,
        rate22ktWithGst: v.rates.rate22ktWithGst,
        purityFactor: v.rates.purityFactor,
        unit: this.cfg.business.unit,
        label: this.cfg.business.label,
        at: v.t,
        atIst: istPretty(new Date(v.t)),
        status: v.verdict.status,
        confidence: v.verdict.confidence,
        rowName: v.rowName,
        rowCode: v.rowCode,
        high: v.high,
        low: v.low,
        message: v.message,
        variants: v.rates.variants,
      } : null,
      live: l ? {
        status: l.verdict.status,
        confidence: l.verdict.confidence,
        at: l.t,
        atIst: istPretty(new Date(l.t)),
        rate999: l.rates ? l.rates.rate999 : null,
        checks: l.checks,
        groups: l.verdict.groups,
        blocking: l.verdict.blocking,
        warnings: l.verdict.warnings,
      } : null,
      references: {
        kaka: l ? l.kakaInfo : null,
        parity: l ? l.parityInfo : null,
      },
      lastChangeAt: this.lastChangeAt,
      stats: this.stats,
      history: this.history.slice(-720),
      silver: this._silverPublicState(),
      boardControl: this.boardControl,
      server: {
        domain: this.cfg.server.publicDomain,
        business: this.cfg.whatsapp.businessName,
        pollIntervalMs: this.cfg.poll.intervalMs,
      },
    };
  }

  _silverPublicState() {
    const v = this.silverLastVerified;
    const l = this.silverLatest;
    const sb = this.cfg.silver.business;
    return {
      ok: !!v,
      published: v ? {
        silverBase: v.rates.silverBase,
        premiumAdd: v.rates.premiumAdd,
        pure: v.rates.pure,
        pureExact: v.rates.pureExact,
        pureLabel: sb.pureLabel,
        ornament: v.rates.ornament,
        ornamentExact: v.rates.ornamentExact,
        ornamentLabel: sb.ornamentLabel,
        ornamentDiscountPct: v.rates.ornamentDiscountPct,
        unit: v.rates.unit,
        at: v.t,
        atIst: istPretty(new Date(v.t)),
        status: v.verdict.status,
        confidence: v.verdict.confidence,
      } : null,
      live: l ? {
        status: l.verdict.status,
        confidence: l.verdict.confidence,
        at: l.t,
        atIst: istPretty(new Date(l.t)),
        checks: l.checks,
        groups: l.verdict.groups,
        blocking: l.verdict.blocking,
        warnings: l.verdict.warnings,
      } : null,
      kaka: l ? l.kakaInfo : null,
      lastChangeAt: this.silverLastChangeAt,
      stats: this.silverStats,
      history: this.silverHistory.slice(-720),
    };
  }
}

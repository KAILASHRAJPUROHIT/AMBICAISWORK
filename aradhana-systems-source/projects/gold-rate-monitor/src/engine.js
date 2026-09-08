/**
 * The 1-second poll loop.
 *
 * Each tick: fetch Safari -> select the 999 row -> run all four validation groups
 * -> publish only if no BLOCKING check failed.
 *
 * Ticks never overlap: if a fetch runs long, the next one is skipped rather than
 * stacked, so a slow upstream can't build a backlog of in-flight requests.
 */

import { fetchFeed, selectRow, selectRowAny } from './feed.js';
import { checkInternal, checkKaka, checkParity, checkTemporal, summarise } from './validate.js';
import { deriveRates, deriveSilverRates } from './store.js';
import { inMarketHours } from './time.js';

export class Engine {
  constructor(cfg, store, kakaSource, paritySource, kakaSilverSource, log) {
    this.cfg = cfg;
    this.store = store;
    this.kaka = kakaSource;
    this.parity = paritySource;
    this.kakaSilver = kakaSilverSource;
    this.log = log || console.log;
    this.timer = null;
    this.inFlight = false;
    this.skipped = 0;
  }

  start() {
    this.tick();
    this.timer = setInterval(() => this.tick(), this.cfg.poll.intervalMs);
    this.log(`[engine] polling ${this.cfg.primary.label} + ${this.cfg.silver.primary.label} every ${this.cfg.poll.intervalMs}ms`);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  async tick() {
    if (this.inFlight) { this.skipped++; return; }
    this.inFlight = true;
    // Gold and silver are independent instruments: one feed failing must never
    // block or crash the other, so each gets its own try/catch inside Promise.all.
    await Promise.all([
      this.runOnce().catch((err) => {
        this.store.recordFetchError(err.message);
        const n = this.store.stats.consecutiveFetchErrors;
        if (n <= 3 || n % 30 === 0) this.log(`[engine] gold feed error (${n} consecutive): ${err.message}`);
      }),
      this.runSilverOnce().catch((err) => {
        this.store.recordSilverFetchError(err.message);
        const n = this.store.silverStats.consecutiveFetchErrors;
        if (n <= 3 || n % 30 === 0) this.log(`[engine] silver feed error (${n} consecutive): ${err.message}`);
      }),
    ]);
    this.inFlight = false;
  }

  async runOnce() {
    const cfg = this.cfg;
    const feed = await fetchFeed(cfg.primary.url, cfg.poll.timeoutMs);
    this.store.clearFetchError();

    // Resolve the target row (trying every known catalog shape - Safari has
    // reshuffled "GOLD INDIAN-BIS 999" to "GOLD IMPORTED 999" before) and
    // every internal reference row.
    const sel = selectRowAny(feed.rows, cfg.primary.targetCandidates);
    const targetField = sel.usedCandidate >= 0 ? cfg.primary.targetCandidates[sel.usedCandidate].field : 'sell';
    const refs = {};
    for (const [key, spec] of Object.entries(cfg.primary.refRows)) {
      refs[key] = selectRow(feed.rows, spec);
    }

    const value = sel.row ? sel.row[targetField] : null;
    const feedSpot = refs.spotUsd && refs.spotUsd.row ? refs.spotUsd.row.sell : null;
    const feedFx = refs.usdInr && refs.usdInr.row ? refs.usdInr.row.sell : null;

    const kakaSnap = this.kaka ? this.kaka.snapshot : null;
    const paritySnap = this.parity ? this.parity.snapshot : null;
    const marketOpen = inMarketHours(cfg);

    // ---- run all four groups -------------------------------------------
    let checks = checkInternal(sel, refs, cfg, targetField);

    const usable = typeof value === 'number' && Number.isFinite(value) && value > 0;
    let quarantine = this.store.quarantine;

    if (usable) {
      checks = checks.concat(checkKaka(value, kakaSnap, cfg.validation.kaka));
      checks = checks.concat(checkParity(value, feedSpot, feedFx, paritySnap, cfg));

      const prevGood = this.store.lastVerified ? this.store.lastVerified.rates.rate999 : null;
      const t = checkTemporal(
        value, prevGood, quarantine, this.store.lastChangeAt, marketOpen, cfg.validation.temporal
      );
      checks = checks.concat(t.checks);
      quarantine = t.quarantine;
    }

    const verdict = summarise(checks);
    this.store.quarantine = quarantine;

    const kakaDelta = (usable && kakaSnap && kakaSnap.ok && kakaSnap.value)
      ? Number((Math.abs(value - kakaSnap.value) / kakaSnap.value * 100).toFixed(4))
      : null;

    const tick = {
      t: Date.now(),
      rates: usable ? deriveRates(value, cfg) : null,
      rowName: sel.row ? sel.row.name : null,
      rowCode: sel.row ? sel.row.code : null,
      matchedBy: sel.matchedBy,
      high: sel.row ? sel.row.high : null,
      low: sel.row ? sel.row.low : null,
      message: sel.row ? sel.row.message : null,
      feedSpot,
      feedFx,
      feedLatencyMs: feed.latencyMs,
      marketOpen,
      checks,
      verdict,
      kaka: kakaSnap && kakaSnap.ok ? kakaSnap.value : null,
      kakaInfo: kakaSnap && kakaSnap.ok ? {
        label: cfg.validation.kaka.label,
        value: kakaSnap.value,
        rowName: kakaSnap.rowName,
        rowCode: kakaSnap.rowCode,
        secondary: kakaSnap.secondary,
        deltaPct: kakaDelta,
        ageSec: Number(((Date.now() - kakaSnap.fetchedAt) / 1000).toFixed(1)),
        ok: true,
      } : { label: cfg.validation.kaka.label, ok: false, error: kakaSnap ? kakaSnap.error : 'disabled' },
      parityInfo: paritySnap && paritySnap.ok ? {
        xau: paritySnap.xau,
        usdInr: paritySnap.usdInr,
        ageSec: Number(((Date.now() - paritySnap.fetchedAt) / 1000).toFixed(0)),
        ok: true,
      } : { ok: false, error: paritySnap ? paritySnap.error : 'disabled' },
    };

    tick.csvRecord = {
      t: tick.t,
      status: verdict.status,
      confidence: verdict.confidence,
      rate999: usable ? tick.rates.rate999 : '',
      rate22kt: usable ? tick.rates.rate22kt : '',
      kaka: tick.kaka,
      kakaDelta,
      blocking: verdict.blocking,
      warnings: verdict.warnings,
    };

    const prevStatus = this.store.latest ? this.store.latest.verdict.status : null;
    this.store.recordTick(tick);

    // Log only on state transitions - a 1s loop must not spam the console.
    if (verdict.status !== prevStatus) {
      if (verdict.status === 'BLOCKED') {
        this.log(`[engine] *** BLOCKED *** holding last verified rate. Reasons: ${
          verdict.blocking.map((b) => `${b.id} (${b.detail})`).join('; ')}`);
      } else if (verdict.status === 'VERIFIED_WITH_WARNINGS') {
        this.log(`[engine] verified with warnings: ${verdict.warnings.map((w) => w.id).join(', ')}`);
      } else {
        this.log(`[engine] VERIFIED - 999=${tick.rates.rate999} 22KT=${tick.rates.rate22kt} (${verdict.passed}/${verdict.total} checks)`);
      }
    }

    return tick;
  }

  /**
   * Silver's parallel pipeline. Lighter validation than gold: Safari's Silver
   * Rates tab exposes no per-product BUY/SELL row (only spot/FX/COSTING), so
   * there is no GST or purity invariant to check internally - only the Kaka
   * cross-check and the spike/staleness guard, both still blocking.
   */
  async runSilverOnce() {
    const cfg = this.cfg;
    const sCfg = cfg.silver;
    const feed = await fetchFeed(sCfg.primary.url, cfg.poll.timeoutMs);
    this.store.clearSilverFetchError();

    const sel = selectRow(feed.rows, sCfg.primary.target);
    const value = sel.row ? sel.row[sCfg.primary.target.field] : null;
    const usable = typeof value === 'number' && Number.isFinite(value) && value > 0;

    const kakaSnap = this.kakaSilver ? this.kakaSilver.snapshot : null;
    const marketOpen = inMarketHours(cfg);

    let checks = [];
    checks.push({
      id: 'SLV_ROW_IDENTITY', group: 'internal', level: 'blocking', ok: !!sel.row,
      detail: sel.row ? `Matched by ${sel.matchedBy}: "${sel.row.name}"` : (sel.note || 'SILVER COSTING row not found'),
    });
    checks.push({
      id: 'SLV_VALUE_PRESENT', group: 'internal', level: 'blocking', ok: usable,
      detail: usable ? `SELL = ${value}` : 'SILVER COSTING missing or non-numeric',
    });

    let quarantine = this.store.silverQuarantine;
    if (usable) {
      checks = checks.concat(checkKaka(value, kakaSnap, sCfg.validation.kaka));

      const prevGood = this.store.silverLastVerified ? this.store.silverLastVerified.rates.silverBase : null;
      const t = checkTemporal(
        value, prevGood, quarantine, this.store.silverLastChangeAt, marketOpen, sCfg.validation.temporal
      );
      checks = checks.concat(t.checks);
      quarantine = t.quarantine;
    }

    const verdict = summarise(checks);
    this.store.silverQuarantine = quarantine;

    const kakaDelta = (usable && kakaSnap && kakaSnap.ok && kakaSnap.value)
      ? Number((Math.abs(value - kakaSnap.value) / kakaSnap.value * 100).toFixed(4))
      : null;

    const tick = {
      t: Date.now(),
      rates: usable ? deriveSilverRates(value, cfg) : null,
      rowName: sel.row ? sel.row.name : null,
      rowCode: sel.row ? sel.row.code : null,
      checks,
      verdict,
      kaka: kakaSnap && kakaSnap.ok ? kakaSnap.value : null,
      kakaInfo: kakaSnap && kakaSnap.ok ? {
        label: sCfg.validation.kaka.label,
        value: kakaSnap.value,
        rowName: kakaSnap.rowName,
        rowCode: kakaSnap.rowCode,
        deltaPct: kakaDelta,
        ageSec: Number(((Date.now() - kakaSnap.fetchedAt) / 1000).toFixed(1)),
        ok: true,
      } : { label: sCfg.validation.kaka.label, ok: false, error: kakaSnap ? kakaSnap.error : 'disabled' },
    };

    tick.csvRecord = {
      t: tick.t,
      status: verdict.status,
      confidence: verdict.confidence,
      silverBase: usable ? tick.rates.silverBase : '',
      pure: usable ? tick.rates.pure : '',
      ornament: usable ? tick.rates.ornament : '',
      kaka: tick.kaka,
      kakaDelta,
      blocking: verdict.blocking,
      warnings: verdict.warnings,
    };

    const prevStatus = this.store.silverLatest ? this.store.silverLatest.verdict.status : null;
    this.store.recordSilverTick(tick);

    if (verdict.status !== prevStatus) {
      if (verdict.status === 'BLOCKED') {
        this.log(`[engine] *** SILVER BLOCKED *** holding last verified rate. Reasons: ${
          verdict.blocking.map((b) => `${b.id} (${b.detail})`).join('; ')}`);
      } else if (verdict.status === 'VERIFIED_WITH_WARNINGS') {
        this.log(`[engine] silver verified with warnings: ${verdict.warnings.map((w) => w.id).join(', ')}`);
      } else {
        this.log(`[engine] SILVER VERIFIED - base=${tick.rates.silverBase} pure=${tick.rates.pure} ornament=${tick.rates.ornament} (${verdict.passed}/${verdict.total} checks)`);
      }
    }

    return tick;
  }
}

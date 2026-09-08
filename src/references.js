/**
 * Background reference sources.
 *
 * Kaka Gold is the authoritative external cross-check (independent Zaveri Bazaar
 * dealer on the same Chirayu broadcast stack, so its 999 BIS row is directly
 * comparable to Safari's). It refreshes on its own timer - the 1s Safari poll
 * validates against the most recent cached snapshot.
 *
 * The international parity pair (XAU spot + USD/INR) is an ADVISORY floor only.
 * Set validation.parity.enabled=false in config.json to make Kaka Gold the sole
 * external reference.
 */

import { fetchFeed, selectRowAny } from './feed.js';

export class ReferenceSource {
  constructor(name, refreshMs, fetcher, log, attempts = 3) {
    this.name = name;
    this.refreshMs = refreshMs;
    this.fetcher = fetcher;
    this.log = log || (() => {});
    this.attempts = attempts;
    this.snapshot = { ok: false, error: 'not yet fetched', fetchedAt: 0 };
    this.timer = null;
    this.consecutiveFailures = 0;
  }

  /** Transient DNS/TLS blips are common on a cold start - retry before giving up. */
  async _fetchWithRetry() {
    let lastErr;
    for (let i = 0; i < this.attempts; i++) {
      try {
        return await this.fetcher();
      } catch (err) {
        lastErr = err;
        if (i < this.attempts - 1) {
          await new Promise((r) => setTimeout(r, 300 * (i + 1)));
        }
      }
    }
    throw lastErr;
  }

  async refresh() {
    try {
      const snap = await this._fetchWithRetry();
      this.snapshot = { ...snap, ok: true, error: null, fetchedAt: Date.now() };
      if (this.consecutiveFailures > 0) {
        this.log(`[ref:${this.name}] recovered after ${this.consecutiveFailures} failure(s)`);
      }
      this.consecutiveFailures = 0;
    } catch (err) {
      this.consecutiveFailures++;
      // Keep the last good snapshot; staleness checks will catch it if it ages out.
      this.snapshot = {
        ...this.snapshot,
        ok: this.snapshot.fetchedAt > 0 ? this.snapshot.ok : false,
        error: err.message,
        lastErrorAt: Date.now(),
      };
      if (this.consecutiveFailures <= 3 || this.consecutiveFailures % 20 === 0) {
        this.log(`[ref:${this.name}] fetch failed (${this.consecutiveFailures}x): ${err.message}`);
      }
    }
    return this.snapshot;
  }

  start() {
    this.refresh();
    this.timer = setInterval(() => this.refresh(), this.refreshMs);
    if (this.timer.unref) this.timer.unref();
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

/**
 * Generic Kaka Gold reference-row source. `c` is a validation.kaka-shaped
 * config block; `name` distinguishes the two instances in logs/ReferenceSource.
 */
function makeKakaSourceFrom(name, c, timeoutMs, log) {
  return new ReferenceSource(name, c.refreshMs, async () => {
    const feed = await fetchFeed(c.url, timeoutMs);

    // The dealer's product catalog itself can change shape (not just the
    // row's rotating date) - Kaka has flipped their 999 line between "BIS
    // APPROVED" and "IMPORTED" scrip codes more than once in the same week.
    // Try every known shape in priority order rather than hardcoding one.
    const primary = selectRowAny(feed.rows, c.targetCandidates);
    if (!primary.row) throw new Error(primary.note || `${c.label} target row not found`);
    const primaryField = c.targetCandidates[primary.usedCandidate].field;
    const value = primary.row[primaryField];
    if (typeof value !== 'number' || !(value > 0)) {
      throw new Error(`${c.label} ${primaryField} not numeric (raw "${primary.row.rawSell}")`);
    }

    const sec = c.secondaryCandidates ? selectRowAny(feed.rows, c.secondaryCandidates) : { row: null };
    const secField = sec.row && sec.usedCandidate >= 0 ? c.secondaryCandidates[sec.usedCandidate].field : null;
    const gst = c.refRows && c.refRows.gst999Candidates
      ? selectRowAny(feed.rows, c.refRows.gst999Candidates)
      : { row: null };

    return {
      value,
      rowName: primary.row.name,
      rowCode: primary.row.code,
      matchedBy: primary.matchedBy,
      confident: primary.confident,
      buy: primary.row.buy,
      high: primary.row.high,
      low: primary.row.low,
      secondary: sec.row ? sec.row[secField] : null,
      gst999: gst.row ? gst.row.sell : null,
      latencyMs: feed.latencyMs,
    };
  }, log);
}

/** Kaka Gold 999 BIS APPROVED - the background reference dealer for gold. */
export function makeKakaSource(cfg, log) {
  return makeKakaSourceFrom('kaka', cfg.validation.kaka, cfg.poll.timeoutMs, log);
}

/** Kaka Gold silver-bar feed - the background reference dealer for silver. */
export function makeKakaSilverSource(cfg, log) {
  return makeKakaSourceFrom('kaka-silver', cfg.silver.validation.kaka, cfg.poll.timeoutMs, log);
}

/** International parity: XAU/USD spot + USD/INR. Advisory only. */
export function makeParitySource(cfg, log) {
  const c = cfg.validation.parity;
  return new ReferenceSource('parity', c.refreshMs, async () => {
    const get = async (url, timeoutMs) => {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      try {
        const res = await fetch(url, { signal: ctrl.signal, headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } finally {
        clearTimeout(t);
      }
    };

    const [xauRes, fxRes] = await Promise.all([
      get(c.xauUrl, 8000),
      get(c.fxUrl, 8000),
    ]);

    const xau = Number(xauRes && xauRes.price);
    const usdInr = Number(fxRes && fxRes.rates && fxRes.rates.INR);
    if (!Number.isFinite(xau) || xau <= 0) throw new Error('XAU spot unparsable');
    if (!Number.isFinite(usdInr) || usdInr <= 0) throw new Error('USD/INR unparsable');

    return {
      xau,
      usdInr,
      xauUpdatedAt: xauRes && xauRes.updatedAt ? xauRes.updatedAt : null,
      fxUpdatedAt: fxRes && fxRes.time_last_update_utc ? fxRes.time_last_update_utc : null,
    };
  }, log);
}

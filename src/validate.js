/**
 * Rate validation engine.
 *
 * Four independent check groups run against every published tick:
 *   1. INTERNAL - structural invariants inside the Safari payload itself (no network).
 *   2. KAKA     - live cross-check against Kaka Gold, an independent Zaveri Bazaar dealer.
 *   3. PARITY   - advisory sanity floor vs international spot x USD/INR.
 *   4. TEMPORAL - spike quarantine + staleness guards.
 *
 * A BLOCKING failure means the tick is NOT published and NOT sent to WhatsApp;
 * the last verified rate is held instead.
 */

const TROY_OZ_G = 31.1034768;

const mk = (id, group, level, ok, detail, extra = {}) =>
  ({ id, group, level, ok, detail, ...extra });

const pctDiff = (a, b) => (b === 0 ? Infinity : Math.abs(a - b) / Math.abs(b) * 100);

/* ---------------------------------------------------------------- group 1 */

export function checkInternal(sel, refs, cfg, field) {
  const c = cfg.validation.internal;
  const out = [];
  if (!c.enabled) return out;
  const lvl = c.blocking ? 'blocking' : 'advisory';

  // Row identity: is this really the 999 product (whichever candidate matched)?
  if (!sel.row) {
    out.push(mk('INT_ROW_IDENTITY', 'internal', 'blocking', false,
      sel.note || 'Target row not found in feed.'));
    return out;
  }
  out.push(mk('INT_ROW_IDENTITY', 'internal', sel.confident ? 'advisory' : 'blocking',
    sel.confident,
    sel.confident ? `Matched by ${sel.matchedBy}: "${sel.row.name}"` : sel.note,
    { observed: sel.row.name, matchedBy: sel.matchedBy }));

  const v = sel.row[field];
  const valueOk = typeof v === 'number' && Number.isFinite(v) && v > 0;

  out.push(mk('INT_VALUE_PRESENT', 'internal', 'blocking', valueOk,
    valueOk
      ? `${field.toUpperCase()} = ${v}`
      : `${field.toUpperCase()} missing or non-numeric (raw "${sel.row.rawSell}")`,
    { observed: v }));

  if (!valueOk) return out;

  out.push(mk('INT_ABS_RANGE', 'internal', lvl,
    v >= c.absoluteMin && v <= c.absoluteMax,
    `${v} within absolute sanity range ${c.absoluteMin}-${c.absoluteMax}`,
    { observed: v }));

  // GST invariant: the dealer's "999 WITH GST" row must equal 999 x 1.03.
  // Advisory rather than blocking (gstBlocking) because the dealer can silently
  // re-link which product their GST row derives from - e.g. Safari added a
  // parallel "T+0" 999 line on 2026-08-24 and re-based their GST row on THAT
  // line instead of the dated one this monitor tracks, which broke this
  // invariant for a benign catalog reason, not a data-integrity one, and held
  // publishing for hours. Kaka Gold's independent cross-check (KAKA_AGREEMENT,
  // still blocking) is the real safety net against a genuinely bad rate.
  const gstLvl = (c.gstBlocking ?? c.blocking) ? 'blocking' : 'advisory';
  const gst = refs.gst999 && refs.gst999.row ? refs.gst999.row.sell : null;
  if (typeof gst === 'number') {
    const expected = v * c.gstFactor;
    const diff = Math.abs(expected - gst);
    out.push(mk('INT_GST_INVARIANT', 'internal', gstLvl, diff <= c.gstToleranceAbs,
      `999 x ${c.gstFactor} = ${expected.toFixed(2)} vs feed GST row ${gst} (delta ${diff.toFixed(2)}, tol ${c.gstToleranceAbs})`,
      { observed: gst, expected: Number(expected.toFixed(2)), delta: Number(diff.toFixed(2)) }));
  } else {
    out.push(mk('INT_GST_INVARIANT', 'internal', 'advisory', false,
      'GST reference row unavailable - invariant not evaluated.'));
  }

  // Purity: 999 must price above 995, by a believable margin.
  const g995 = refs.gold995 && refs.gold995.row ? refs.gold995.row.sell : null;
  if (typeof g995 === 'number' && g995 > 0) {
    const ratio = v / g995;
    out.push(mk('INT_PURITY_ORDER', 'internal', lvl, v > g995,
      `999 (${v}) > 995 (${g995})`, { observed: g995 }));
    out.push(mk('INT_PURITY_RATIO', 'internal', lvl,
      ratio >= c.purityRatioMin && ratio <= c.purityRatioMax,
      `999/995 ratio ${ratio.toFixed(5)} within ${c.purityRatioMin}-${c.purityRatioMax}`,
      { observed: Number(ratio.toFixed(5)) }));
  } else {
    out.push(mk('INT_PURITY_ORDER', 'internal', 'advisory', false,
      '995 reference row unavailable - purity checks not evaluated.'));
  }

  // Costing band
  const costing = refs.costing && refs.costing.row ? refs.costing.row.sell : null;
  if (typeof costing === 'number' && costing > 0) {
    const d = pctDiff(v, costing);
    out.push(mk('INT_COSTING_BAND', 'internal', 'advisory', d <= c.costingBandPct,
      `999 is ${d.toFixed(3)}% from GOLD COSTING (${costing}), band ${c.costingBandPct}%`,
      { observed: costing, delta: Number(d.toFixed(3)) }));
  }

  // Session high/low envelope (tolerate 1 rupee of feed lag)
  const high = sel.row.high;
  const low = sel.row.low;
  if (typeof high === 'number' && typeof low === 'number') {
    out.push(mk('INT_HILO_ENVELOPE', 'internal', 'advisory',
      v >= low - 1 && v <= high + 1,
      `${v} inside session low/high ${low}-${high}`,
      { observed: `${low}-${high}` }));
  }

  return out;
}

/* ---------------------------------------------------------------- group 2 */

/**
 * Cross-checks `value` against a background Kaka Gold reference.
 * `c` is a validation.kaka-shaped config block (gold's or silver's) - each
 * instrument passes its own, so this one function serves both.
 */
export function checkKaka(value, kakaSnap, c) {
  const out = [];
  if (!c.enabled) return out;
  const lvl = c.blocking ? 'blocking' : 'advisory';

  if (!kakaSnap || !kakaSnap.ok) {
    const err = kakaSnap && kakaSnap.error ? kakaSnap.error : 'not yet fetched';
    out.push(mk('KAKA_AVAILABLE', 'kaka', lvl, false,
      `${c.label} reference unavailable: ${err}`));
    return out;
  }

  const age = Date.now() - kakaSnap.fetchedAt;
  const fresh = age <= c.maxAgeMs;
  out.push(mk('KAKA_AVAILABLE', 'kaka', lvl, fresh,
    fresh
      ? `${c.label} reference fresh (${(age / 1000).toFixed(1)}s old)`
      : `${c.label} reference stale (${(age / 1000).toFixed(0)}s old, max ${c.maxAgeMs / 1000}s)`,
    { observed: kakaSnap.value, ageMs: age }));

  if (!fresh) return out;

  // Primary agreement: Safari "INDIAN-BIS 999" vs Kaka "999 BIS APPROVED".
  const d = pctDiff(value, kakaSnap.value);
  const pass = d <= c.failPct;
  const warn = d > c.warnPct && d <= c.failPct;
  out.push(mk('KAKA_AGREEMENT', 'kaka', lvl, pass,
    `Safari ${value} vs ${c.label} ${kakaSnap.value} = ${d.toFixed(4)}% apart (warn >${c.warnPct}%, fail >${c.failPct}%)`,
    { observed: kakaSnap.value, delta: Number(d.toFixed(4)), soft: warn }));

  if (typeof kakaSnap.secondary === 'number') {
    const d2 = pctDiff(value, kakaSnap.secondary);
    out.push(mk('KAKA_SECONDARY', 'kaka', 'advisory', d2 <= c.failPct,
      `Safari ${value} vs ${c.label} 999 IMPORTED ${kakaSnap.secondary} = ${d2.toFixed(4)}% apart`,
      { observed: kakaSnap.secondary, delta: Number(d2.toFixed(4)) }));
  }

  // Kaka's own GST invariant - proves the reference feed is itself healthy,
  // so we never validate against a silently broken comparator.
  if (typeof kakaSnap.gst999 === 'number') {
    const gstFactor = c.gstFactor || 1.03;
    const gstTol = c.gstToleranceAbs || 3;
    const exp = kakaSnap.value * gstFactor;
    const diff = Math.abs(exp - kakaSnap.gst999);
    out.push(mk('KAKA_SELF_GST', 'kaka', 'advisory',
      diff <= gstTol,
      `${c.label} self-consistency: ${kakaSnap.value} x ${gstFactor} = ${exp.toFixed(2)} vs ${kakaSnap.gst999} (delta ${diff.toFixed(2)})`,
      { observed: kakaSnap.gst999, delta: Number(diff.toFixed(2)) }));
  }

  return out;
}

/* ---------------------------------------------------------------- group 3 */

export function checkParity(value, feedSpot, feedFx, paritySnap, cfg) {
  const c = cfg.validation.parity;
  const out = [];
  if (!c.enabled) return out;
  const lvl = c.blocking ? 'blocking' : 'advisory';

  if (!paritySnap || !paritySnap.ok) {
    const err = paritySnap && paritySnap.error ? paritySnap.error : 'not yet fetched';
    out.push(mk('PAR_AVAILABLE', 'parity', lvl, false,
      `International reference unavailable: ${err}`));
    return out;
  }
  const age = Date.now() - paritySnap.fetchedAt;
  if (age > c.maxAgeMs) {
    out.push(mk('PAR_AVAILABLE', 'parity', lvl, false,
      `International reference stale (${(age / 60000).toFixed(1)} min old)`));
    return out;
  }
  out.push(mk('PAR_AVAILABLE', 'parity', lvl, true,
    `XAU ${paritySnap.xau} USD/oz, USDINR ${paritySnap.usdInr} (${(age / 1000).toFixed(0)}s old)`));

  // Does the dealer's own embedded spot agree with the outside world?
  if (typeof feedSpot === 'number') {
    const d = pctDiff(feedSpot, paritySnap.xau);
    out.push(mk('PAR_SPOT_MATCH', 'parity', lvl, d <= c.spotTolerancePct,
      `Feed spot ${feedSpot} vs XAU ${paritySnap.xau} = ${d.toFixed(3)}% (tol ${c.spotTolerancePct}%)`,
      { observed: paritySnap.xau, delta: Number(d.toFixed(3)) }));
  }
  if (typeof feedFx === 'number') {
    const d = pctDiff(feedFx, paritySnap.usdInr);
    out.push(mk('PAR_FX_MATCH', 'parity', lvl, d <= c.fxTolerancePct,
      `Feed USDINR ${feedFx} vs reference ${paritySnap.usdInr} = ${d.toFixed(3)}% (tol ${c.fxTolerancePct}%)`,
      { observed: paritySnap.usdInr, delta: Number(d.toFixed(3)) }));
  }

  // Landed-price premium: Indian domestic 999 sits above international parity
  // because of import duty + local premium. Outside the band, something is wrong.
  const parity10g = (paritySnap.xau * paritySnap.usdInr / TROY_OZ_G) * 10;
  const premium = value / parity10g;
  out.push(mk('PAR_PREMIUM_BAND', 'parity', lvl,
    premium >= c.premiumMin && premium <= c.premiumMax,
    `Domestic premium ${((premium - 1) * 100).toFixed(2)}% over parity ${parity10g.toFixed(0)}/10g (band ${((c.premiumMin - 1) * 100).toFixed(0)}-${((c.premiumMax - 1) * 100).toFixed(0)}%)`,
    { observed: Number(parity10g.toFixed(2)), premium: Number(premium.toFixed(4)) }));

  return out;
}

/* ---------------------------------------------------------------- group 4 */

/**
 * Spike quarantine + staleness. `c` is a validation.temporal-shaped config
 * block (gold's or silver's). Returns { checks, quarantine } - the caller
 * persists the returned quarantine state for the next tick.
 */
export function checkTemporal(value, prevGood, quarantine, lastChangeAt, inMarketHours, c) {
  const checks = [];
  let q = quarantine ? { pending: quarantine.pending, count: quarantine.count } : { pending: null, count: 0 };
  if (!c.enabled) return { checks, quarantine: q };
  const lvl = c.blocking ? 'blocking' : 'advisory';

  if (typeof prevGood !== 'number') {
    checks.push(mk('TMP_SPIKE', 'temporal', lvl, true, 'First reading - establishing baseline.'));
    q = { pending: null, count: 0 };
  } else {
    const jump = pctDiff(value, prevGood);
    if (jump <= c.maxTickJumpPct) {
      checks.push(mk('TMP_SPIKE', 'temporal', lvl, true,
        `Move ${jump.toFixed(4)}% from last verified ${prevGood} (limit ${c.maxTickJumpPct}%)`,
        { observed: prevGood, delta: Number(jump.toFixed(4)) }));
      q = { pending: null, count: 0 };
    } else {
      // Large gap: require N consecutive agreeing ticks before trusting it.
      const agrees = q.pending !== null && pctDiff(value, q.pending) <= 0.1;
      q = agrees
        ? { pending: value, count: q.count + 1 }
        : { pending: value, count: 1 };

      if (q.count >= c.confirmTicks) {
        checks.push(mk('TMP_SPIKE', 'temporal', lvl, true,
          `Gap of ${jump.toFixed(3)}% from ${prevGood} CONFIRMED by ${q.count} consecutive ticks - accepting.`,
          { observed: prevGood, delta: Number(jump.toFixed(3)), confirmed: true }));
        q = { pending: null, count: 0 };
      } else {
        checks.push(mk('TMP_SPIKE', 'temporal', lvl, false,
          `Suspicious ${jump.toFixed(3)}% jump from ${prevGood} - quarantined (${q.count}/${c.confirmTicks} confirmations)`,
          { observed: prevGood, delta: Number(jump.toFixed(3)), confirmed: false }));
      }
    }
  }

  if (inMarketHours && lastChangeAt) {
    const mins = (Date.now() - lastChangeAt) / 60000;
    checks.push(mk('TMP_STALE', 'temporal', 'advisory', mins <= c.staleWarnMinutes,
      mins <= c.staleWarnMinutes
        ? `Rate last moved ${mins.toFixed(1)} min ago`
        : `Rate has not moved for ${mins.toFixed(1)} min during market hours - feed may be frozen.`,
      { observed: Number(mins.toFixed(1)) }));
  }

  return { checks, quarantine: q };
}

/* ------------------------------------------------------------------ verdict */

export function summarise(checks) {
  const failures = checks.filter((c) => !c.ok);
  const blocking = failures.filter((c) => c.level === 'blocking');
  const warnings = [
    ...failures.filter((c) => c.level === 'advisory'),
    ...checks.filter((c) => c.ok && c.soft),
  ];

  const status = blocking.length > 0
    ? 'BLOCKED'
    : warnings.length > 0
      ? 'VERIFIED_WITH_WARNINGS'
      : 'VERIFIED';

  const passed = checks.filter((c) => c.ok).length;
  const confidence = checks.length ? Math.round((passed / checks.length) * 100) : 0;

  const groups = {};
  for (const c of checks) {
    if (!groups[c.group]) groups[c.group] = { total: 0, passed: 0 };
    groups[c.group].total++;
    if (c.ok) groups[c.group].passed++;
  }

  return {
    status,
    confidence,
    passed,
    total: checks.length,
    groups,
    blocking: blocking.map((c) => ({ id: c.id, detail: c.detail })),
    warnings: warnings.map((c) => ({ id: c.id, detail: c.detail })),
  };
}

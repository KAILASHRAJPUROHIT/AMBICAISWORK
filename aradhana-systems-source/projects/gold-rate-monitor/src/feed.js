/**
 * Chirayu VOTS broadcast feed client + parser.
 *
 * Wire format (verified 2026-08-23 against both Safari Bullions and Kaka Gold):
 *   \t<code>\t<name>\t<buy>\t<sell>\t<high>\t<low>\t<message>\r\n
 * Every line begins with a TAB, so the first split field is always empty.
 * A missing numeric is the literal "-" (e.g. Safari's 999 row has no BUY side).
 */

/** Parse one numeric feed cell. Returns null for blank / "-" / non-numeric. */
export function parseNum(cell) {
  const t = (cell ?? '').trim();
  if (!t || t === '-') return null;
  const v = Number(t.replace(/,/g, ''));
  return Number.isFinite(v) ? v : null;
}

/** Parse a raw feed body into structured rows. */
export function parseFeed(text) {
  const rows = [];
  if (typeof text !== 'string') return rows;

  for (const rawLine of text.split(/\r?\n/)) {
    if (!rawLine.trim()) continue;

    let fields = rawLine.split('\t');
    // Lines are TAB-prefixed; drop the leading empty cell if present.
    if (fields[0] === '') fields = fields.slice(1);
    if (fields.length < 6) continue;

    const code = (fields[0] || '').trim();
    const name = (fields[1] || '').trim();
    if (!code || !name) continue;

    rows.push({
      code,
      name,
      buy: parseNum(fields[2]),
      sell: parseNum(fields[3]),
      high: parseNum(fields[4]),
      low: parseNum(fields[5]),
      rawBuy: (fields[2] || '').trim(),
      rawSell: (fields[3] || '').trim(),
      message: fields.slice(6).join(' ').trim(),
    });
  }
  return rows;
}

/**
 * Locate a row by scrip code with a name-pattern cross-check.
 *
 * The dealer's row NAME embeds a rotating delivery date ("... (24th Aug)"), so the
 * CODE is the stable key. We still verify the name to catch the dangerous case
 * where a dealer re-assigns a code to a different product.
 *
 * Returns { row, matchedBy, confident, note }.
 */
export function selectRow(rows, spec) {
  const re = spec.namePattern ? new RegExp(spec.namePattern, 'i') : null;
  const byCode = spec.code ? rows.find((r) => r.code === spec.code) : undefined;
  const byName = re ? rows.filter((r) => re.test(r.name)) : [];

  if (byCode && re && re.test(byCode.name)) {
    return { row: byCode, matchedBy: 'code+name', confident: true, note: null };
  }
  if (byCode && !re) {
    return { row: byCode, matchedBy: 'code', confident: true, note: null };
  }
  if (byCode) {
    return {
      row: byCode,
      matchedBy: 'code-only',
      confident: false,
      note: `Code ${spec.code} found but its name "${byCode.name}" no longer matches the expected product pattern.`,
    };
  }
  if (byName.length === 1) {
    return {
      row: byName[0],
      matchedBy: 'name-only',
      confident: false,
      note: `Expected code ${spec.code} is absent; matched by name instead (code is now ${byName[0].code}).`,
    };
  }
  if (byName.length > 1) {
    return {
      row: null,
      matchedBy: 'ambiguous',
      confident: false,
      note: `${byName.length} rows match the name pattern and code ${spec.code} is absent.`,
    };
  }
  return {
    row: null,
    matchedBy: 'none',
    confident: false,
    note: `Neither code ${spec.code} nor the name pattern matched any row.`,
  };
}

/**
 * Locate a row by trying several candidate specs in priority order, for a
 * dealer whose product catalog itself changes shape over time - not just the
 * row's rotating date suffix, but which product line exists at all. Kaka Gold
 * has flipped their 999 line between "999 BIS APPROVED" and "999 IMPORTED"
 * (and back again) within the same week, each time under a different scrip
 * code. Rather than hardcode to whichever shape happens to exist today, try
 * each known shape and use the first one that resolves.
 *
 * A CONFIDENT match (code+name both agree) anywhere in the list always wins
 * over a LOW-CONFIDENCE match (name-only, because the code moved) earlier in
 * the list - a dealer can carry an old, renumbered row alongside a new one
 * that matches a later candidate cleanly, and the clean match is the one to
 * trust. Only when nothing in the list is confident do we fall back to the
 * first low-confidence hit, and only when nothing matches at all do we fail.
 *
 * Returns the same shape as selectRow(), plus `usedCandidate` (the index of
 * the candidate that matched, for logging) when a candidate matched, or a
 * combined note listing every candidate's failure when none did.
 */
export function selectRowAny(rows, candidates) {
  const attempts = [];
  let fallback = null;
  for (let i = 0; i < candidates.length; i++) {
    const sel = selectRow(rows, candidates[i]);
    if (sel.row && sel.confident) return { ...sel, usedCandidate: i };
    if (sel.row && !fallback) fallback = { ...sel, usedCandidate: i };
    if (!sel.row) attempts.push(`candidate ${i} (code ${candidates[i].code}): ${sel.note}`);
  }
  if (fallback) return fallback;
  return {
    row: null,
    matchedBy: 'none',
    confident: false,
    usedCandidate: -1,
    note: `No candidate matched - ${attempts.join('; ')}`,
  };
}

/** Fetch + parse a feed. Throws on transport/HTTP/empty-body problems. */
export async function fetchFeed(url, timeoutMs = 4000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const startedAt = Date.now();
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { 'Accept': 'text/plain,*/*', 'Cache-Control': 'no-cache' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    if (!text || !text.trim()) throw new Error('empty body');

    const rows = parseFeed(text);
    if (rows.length === 0) throw new Error('no parsable rows');

    return { rows, raw: text, latencyMs: Date.now() - startedAt, fetchedAt: Date.now() };
  } finally {
    clearTimeout(timer);
  }
}

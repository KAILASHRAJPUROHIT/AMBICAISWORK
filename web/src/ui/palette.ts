/** Stable per-app colours for charts: the same package always gets the same hue. */
const HUES = ['#22d3ee', '#a78bfa', '#f472b6', '#34d399', '#fbbf24', '#60a5fa', '#fb7185', '#2dd4bf', '#c084fc', '#f97316'];

export function appColor(pkg: string): string {
  let h = 0;
  for (let i = 0; i < pkg.length; i++) h = (h * 31 + pkg.charCodeAt(i)) >>> 0;
  return HUES[h % HUES.length];
}

/**
 * Distinct colours for a set of apps: each keeps its hashed hue unless another app in the set
 * already took it, then probes to the next free one. Deterministic for a given set.
 */
export function appColorMap(pkgs: string[]): Map<string, string> {
  const out = new Map<string, string>();
  const used = new Set<number>();
  for (const pkg of [...new Set(pkgs)].sort()) {
    let h = 0;
    for (let i = 0; i < pkg.length; i++) h = (h * 31 + pkg.charCodeAt(i)) >>> 0;
    let idx = h % HUES.length;
    for (let n = 0; n < HUES.length && used.has(idx); n++) idx = (idx + 1) % HUES.length;
    used.add(idx);
    out.set(pkg, HUES[idx]);
  }
  return out;
}

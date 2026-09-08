/**
 * Self-test: proves the whole validation chain against the real live feeds.
 * Run with:  npm run check
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Store } from './store.js';
import { Engine } from './engine.js';
import { makeKakaSource, makeParitySource, makeKakaSilverSource } from './references.js';
import { istPretty } from './time.js';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, 'config.json'), 'utf8'));

const pad = (s, n) => String(s).padEnd(n);
const inr = (n) => n == null ? '-' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });

console.log('='.repeat(78));
console.log(' ARADHANA JEWELLERS - GOLD RATE MONITOR :: SELF TEST');
console.log(' ' + istPretty());
console.log('='.repeat(78));

const store = new Store(cfg, ROOT);
const kaka = makeKakaSource(cfg, console.log);
const parity = makeParitySource(cfg, console.log);
const kakaSilver = makeKakaSilverSource(cfg, console.log);

console.log('\n[1/3] Fetching background references...');
await Promise.all([kaka.refresh(), parity.refresh(), kakaSilver.refresh()]);
console.log('  Kaka Gold :', kaka.snapshot.ok
  ? `${kaka.snapshot.rowName} (code ${kaka.snapshot.rowCode}) = ${inr(kaka.snapshot.value)}`
  : `FAILED - ${kaka.snapshot.error}`);
console.log('  Parity    :', parity.snapshot.ok
  ? `XAU $${parity.snapshot.xau}/oz, USD/INR ${parity.snapshot.usdInr}`
  : `FAILED - ${parity.snapshot.error}`);
console.log('  Kaka Silver:', kakaSilver.snapshot.ok
  ? `${kakaSilver.snapshot.rowName} (code ${kakaSilver.snapshot.rowCode}) = ${inr(kakaSilver.snapshot.value)}`
  : `FAILED - ${kakaSilver.snapshot.error}`);

console.log('\n[2/3] Running 3 live ticks against Safari Bullions (gold + silver)...');
const engine = new Engine(cfg, store, kaka, parity, kakaSilver, () => {});

let last = null;
let lastSilver = null;
for (let i = 0; i < 3; i++) {
  [last, lastSilver] = await Promise.all([engine.runOnce(), engine.runSilverOnce()]);
  console.log(`  tick ${i + 1}: 999=${last.rates ? last.rates.rate999 : 'n/a'} ` +
    `status=${last.verdict.status} confidence=${last.verdict.confidence}% ` +
    `latency=${last.feedLatencyMs}ms  ||  silver base=${lastSilver.rates ? lastSilver.rates.silverBase : 'n/a'} ` +
    `status=${lastSilver.verdict.status} confidence=${lastSilver.verdict.confidence}%`);
  if (i < 2) await new Promise((r) => setTimeout(r, 1000));
}

console.log('\n[3/3] Full check report for the last tick:');
console.log('-'.repeat(78));
let group = null;
for (const c of last.checks) {
  if (c.group !== group) {
    group = c.group;
    console.log(`\n  ${group.toUpperCase()}`);
  }
  const mark = c.ok ? (c.soft ? '~' : 'PASS') : (c.level === 'blocking' ? 'FAIL' : 'warn');
  console.log(`    [${pad(mark, 4)}] ${pad(c.id, 20)} ${c.detail}`);
}
console.log('\n' + '-'.repeat(78));

const v = last.verdict;
console.log(`  VERDICT      : ${v.status}`);
console.log(`  CONFIDENCE   : ${v.confidence}%  (${v.passed}/${v.total} checks passed)`);
console.log('  BY GROUP     : ' + Object.entries(v.groups)
  .map(([g, s]) => `${g} ${s.passed}/${s.total}`).join('  |  '));
if (v.blocking.length) console.log('  BLOCKING     : ' + v.blocking.map((b) => b.id).join(', '));
if (v.warnings.length) console.log('  WARNINGS     : ' + v.warnings.map((w) => w.id).join(', '));

if (last.rates) {
  console.log('\n' + '='.repeat(78));
  console.log('  PUBLISHED RATES - GOLD');
  console.log('='.repeat(78));
  console.log(`  999 FINE (Safari, raw)      : ${inr(last.rates.rate999)}  ${cfg.business.unit}`);
  console.log(`  24KT (999 + Rs.${last.rates.premiumAdd24kt})       : ${inr(last.rates.rate24kt)}  ${cfg.business.unit}`);
  if (last.rates.premiumAdd) {
    console.log(`  999 + Rs.${last.rates.premiumAdd} loading         : ${inr(last.rates.rate999Loaded)}  ${cfg.business.unit}`);
  }
  console.log(`  ${pad(cfg.business.label, 28)}: ${inr(last.rates.rate22kt)}  ${cfg.business.unit}   <-- ${cfg.business.purityFactor * 100}% of ${last.rates.premiumAdd ? '(999+' + last.rates.premiumAdd + ')' : '999'}`);
  for (const variant of last.rates.variants || []) {
    console.log(`  ${pad(variant.label, 28)}: ${inr(variant.rate)}  ${cfg.business.unit}   <-- ${(variant.purityFactor * 100).toFixed(0)}% of (999+${last.rates.premiumAdd})`);
  }
  console.log(`  Cross-check (Kaka Gold)     : ${inr(last.kaka)}  (${last.kakaInfo.deltaPct}% apart)`);
  console.log('='.repeat(78));
}

console.log('\n' + '-'.repeat(78));
console.log('  SILVER - full check report for the last tick:');
console.log('-'.repeat(78));
let sgroup = null;
for (const c of lastSilver.checks) {
  if (c.group !== sgroup) {
    sgroup = c.group;
    console.log(`\n  ${sgroup.toUpperCase()}`);
  }
  const mark = c.ok ? (c.soft ? '~' : 'PASS') : (c.level === 'blocking' ? 'FAIL' : 'warn');
  console.log(`    [${pad(mark, 4)}] ${pad(c.id, 20)} ${c.detail}`);
}
const sv = lastSilver.verdict;
console.log('\n' + '-'.repeat(78));
console.log(`  VERDICT      : ${sv.status}  (${sv.passed}/${sv.total} checks passed, ${sv.confidence}%)`);

if (lastSilver.rates) {
  const sb = cfg.silver.business;
  console.log('\n' + '='.repeat(78));
  console.log('  PUBLISHED RATES - SILVER');
  console.log('='.repeat(78));
  console.log(`  SILVER COSTING (Safari)     : ${inr(lastSilver.rates.silverBase)}  ${sb.unit}`);
  console.log(`  ${pad(sb.pureLabel, 28)}: ${inr(lastSilver.rates.pure)}  ${sb.unit}   <-- COSTING + Rs.${lastSilver.rates.premiumAdd}`);
  console.log(`  ${pad(sb.ornamentLabel, 28)}: ${inr(lastSilver.rates.ornament)}  ${sb.unit}   <-- Pure - ${sb.ornamentDiscountPct}%`);
  console.log(`  Cross-check (${cfg.silver.validation.kaka.label}): ${inr(lastSilver.kaka)}  (${lastSilver.kakaInfo.deltaPct}% apart)`);
  console.log('='.repeat(78));
}

kaka.stop();
parity.stop();
kakaSilver.stop();
process.exit(v.status === 'BLOCKED' || sv.status === 'BLOCKED' ? 1 : 0);

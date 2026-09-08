#!/usr/bin/env node
/**
 * Aradhana Jewellers - Gold Rate Monitor
 *
 *   npm start              full service: poller + live page + WhatsApp
 *   npm run monitor        poller + live page only (no WhatsApp)
 *   npm run check          one-shot validation self-test
 *   npm run wa-login       link WhatsApp by QR, then exit
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { Store } from './store.js';
import { Engine } from './engine.js';
import { makeKakaSource, makeParitySource, makeKakaSilverSource } from './references.js';
import { WhatsAppSender } from './whatsapp.js';
import { Scheduler } from './scheduler.js';
import { createServer } from './server.js';
import { istPretty } from './time.js';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const argv = process.argv.slice(2);
const has = (f) => argv.includes(f);

const log = (...a) => console.log(`${new Date().toISOString().slice(11, 19)}`, ...a);

const cfg = JSON.parse(fs.readFileSync(path.join(ROOT, 'config.json'), 'utf8'));
if (process.env.PORT) cfg.server.port = Number(process.env.PORT);

console.log('');
console.log('  ARADHANA JEWELLERS  -  GOLD RATE MONITOR');
console.log(`  ${istPretty()} IST`);
console.log(`  Primary : ${cfg.primary.label} (codes: ${cfg.primary.targetCandidates.map((c) => c.code).join(', ')})`);
console.log(`  Reference: ${cfg.validation.kaka.label} (codes: ${cfg.validation.kaka.targetCandidates.map((c) => c.code).join(', ')})`);
console.log(`  Business : ${cfg.business.label} = ${cfg.business.purityFactor * 100}% of 999, ${cfg.business.unit}`);
console.log(`  Silver   : ${cfg.silver.business.pureLabel} = COSTING + Rs.${cfg.silver.business.premiumAdd}; ${cfg.silver.business.ornamentLabel} = Pure - ${cfg.silver.business.ornamentDiscountPct}%`);
console.log('');

const store = new Store(cfg, ROOT);
const kaka = cfg.validation.kaka.enabled ? makeKakaSource(cfg, log) : null;
const parity = cfg.validation.parity.enabled ? makeParitySource(cfg, log) : null;
const kakaSilver = cfg.silver.validation.kaka.enabled ? makeKakaSilverSource(cfg, log) : null;

const ctx = { rootDir: ROOT, sender: null, scheduler: null };

// ---- WhatsApp (optional) ------------------------------------------------
const wantWhatsApp = cfg.whatsapp.enabled && !has('--no-whatsapp');
if (wantWhatsApp) {
  const sender = new WhatsAppSender(cfg, ROOT, log);
  ctx.sender = sender;

  sender.start().then((ok) => {
    if (!ok) return;
    if (has('--wa-login-only')) {
      log('[main] WhatsApp linked. Session saved to data/wa-session. Exiting.');
      setTimeout(() => process.exit(0), 1500);
      return;
    }
    const scheduler = new Scheduler(cfg, store, sender, log);
    ctx.scheduler = scheduler;
    scheduler.start();
  });

  if (!cfg.whatsapp.groupNames.length && !cfg.whatsapp.numbers.length) {
    log('[main] NOTE: no WhatsApp recipients configured yet.');
    log('[main]       Add them to config.json -> whatsapp.groupNames / whatsapp.numbers');
  }
} else {
  log('[main] WhatsApp disabled for this run');
}

if (has('--wa-login-only')) {
  // Skip the poller and server; we only want the QR handshake.
} else {
  if (kaka) kaka.start();
  if (parity) parity.start();
  if (kakaSilver) kakaSilver.start();

  const engine = new Engine(cfg, store, kaka, parity, kakaSilver, log);
  engine.start();

  const server = createServer(cfg, store, ctx, log);

  // Persist history periodically so a restart keeps the chart.
  const saver = setInterval(() => store.saveHistory(), 60000);

  const shutdown = async (sig) => {
    log(`[main] ${sig} received - shutting down`);
    clearInterval(saver);
    engine.stop();
    if (kaka) kaka.stop();
    if (parity) parity.stop();
    if (kakaSilver) kakaSilver.stop();
    if (ctx.scheduler) ctx.scheduler.stop();
    store.saveHistory();
    server.close();
    if (ctx.sender) await ctx.sender.stop();
    process.exit(0);
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

process.on('unhandledRejection', (err) => {
  log('[main] unhandled rejection:', err && err.message ? err.message : err);
});

/**
 * Hourly WhatsApp broadcast, 09:00-21:00 IST every day.
 *
 * Fires on the top of each hour in the window. A 30s ticker checks the clock, and
 * an hour-slot key ("2026-08-23T09") guarantees exactly one send per slot even if
 * the process restarts mid-hour or the clock drifts.
 */

import { istParts, istPretty, istClock, inBroadcastWindow } from './time.js';

/** Indian grouping. Shows paise only when the value actually has a fraction. */
const inr = (n) => {
  if (n == null) return '-';
  const num = Number(n);
  const hasFraction = Math.abs(num % 1) > 1e-9;
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: 2,
  });
};

/** The hourly rate message. */
export function formatRateMessage(state, cfg) {
  const p = state.published;
  const b = cfg.business;
  const lines = [];

  lines.push(`*${cfg.whatsapp.businessName.toUpperCase()}*`);
  lines.push(`_Live Gold Rate_`);
  lines.push('');
  lines.push(`*${b.label}*`);
  lines.push(`*₹ ${inr(p.rate22kt)}* ${b.unit}`);
  lines.push('');
  lines.push(`24KT   :  ₹ ${inr(p.rate24kt)}`);
  const v18 = (p.variants || []).find((x) => x.key === '18kt');
  if (v18) lines.push(`${v18.label}   :  ₹ ${inr(v18.rate)}`);
  lines.push('');

  const ref = state.references && state.references.kaka;
  if (p.status === 'VERIFIED') {
    lines.push(`✅ Verified — ${state.live.groups ? Object.values(state.live.groups).reduce((a, g) => a + g.passed, 0) : ''}/${state.live ? state.live.checks.length : ''} accuracy checks passed`);
  } else {
    lines.push(`⚠️ Verified with warnings (${p.confidence}% checks passed)`);
  }
  if (ref && ref.ok) {
    lines.push(`Cross-checked vs ${ref.label}: ₹ ${inr(ref.value)} (${ref.deltaPct}% apart)`);
  }

  const sil = state.silver && state.silver.published;
  if (sil) {
    lines.push('');
    lines.push(`*Silver*`);
    lines.push(`${sil.pureLabel}      :  ₹ ${inr(sil.pure)} ${sil.unit}`);
    lines.push(`${sil.ornamentLabel}  :  ₹ ${inr(sil.ornament)} ${sil.unit}`);
    lines.push(sil.status === 'VERIFIED' || sil.status === 'VERIFIED_WITH_WARNINGS'
      ? `✅ Verified (${sil.confidence}% checks passed)`
      : `⚠️ Silver rate held — verification failed`);
  }

  lines.push('');
  lines.push(`🕐 ${istPretty(new Date(p.at))} IST`);
  lines.push(`🔗 ${cfg.server.publicDomain}`);

  return lines.join('\n');
}

/** Sent when the monitor refuses to publish a rate. */
export function formatAlertMessage(state, cfg) {
  const lines = [];
  lines.push(`🔴 *${cfg.whatsapp.businessName.toUpperCase()} — RATE ALERT*`);
  lines.push('');
  lines.push('The gold rate monitor has *stopped publishing* because a safety check failed.');
  lines.push('');
  const blocking = (state.live && state.live.blocking) || [];
  for (const b of blocking.slice(0, 4)) lines.push(`• ${b.detail}`);
  lines.push('');
  if (state.published) {
    lines.push(`Last *verified* rate (${istClock(new Date(state.published.at))} IST):`);
    lines.push(`22KT: ₹ ${inr(state.published.rate22kt)}  |  999: ₹ ${inr(state.published.rate999)}`);
    lines.push('');
    lines.push('_Do not quote a newer figure until this clears._');
  }
  lines.push(`🕐 ${istPretty()} IST`);
  return lines.join('\n');
}

export class Scheduler {
  constructor(cfg, store, sender, log) {
    this.cfg = cfg;
    this.store = store;
    this.sender = sender;
    this.log = log || console.log;
    this.timer = null;
    this.lastSlot = null;
    this.lastAlertAt = 0;
    this.history = [];
  }

  slotKey(d = new Date()) {
    const p = istParts(d);
    return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}T${String(p.hour).padStart(2, '0')}`;
  }

  start() {
    this.timer = setInterval(() => this.check(), 30000);
    this.check();
    const w = this.cfg.whatsapp;
    this.log(`[scheduler] hourly broadcast ${w.scheduleStartHour}:00-${w.scheduleEndHour}:00 IST, every ${w.intervalMinutes} min`);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  async check() {
    const cfg = this.cfg;
    if (!cfg.whatsapp.enabled) return;

    const now = new Date();
    const p = istParts(now);
    const state = this.store.publicState();

    // --- alert path: publishing is blocked -----------------------------
    if (cfg.whatsapp.alertOnBlocked && state.live && state.live.status === 'BLOCKED') {
      const since = Date.now() - this.lastAlertAt;
      if (since > cfg.whatsapp.alertCooldownMinutes * 60000) {
        this.lastAlertAt = Date.now();
        this.log('[scheduler] publishing is BLOCKED - sending alert');
        await this.sender.send(formatAlertMessage(state, cfg));
      }
      return;
    }

    // --- hourly path ---------------------------------------------------
    if (!inBroadcastWindow(cfg, now)) return;

    // Fire in the first two minutes of the hour.
    const stepHours = Math.max(1, Math.round(cfg.whatsapp.intervalMinutes / 60));
    const hoursIn = p.hour - cfg.whatsapp.scheduleStartHour;
    if (hoursIn % stepHours !== 0) return;
    if (p.minute > 2) return;

    const slot = this.slotKey(now);
    if (slot === this.lastSlot) return;

    if (!state.ok || !state.published) {
      this.log(`[scheduler] slot ${slot}: no verified rate yet - skipping`);
      return;
    }
    if (cfg.whatsapp.sendOnlyWhenVerified && state.published.status === 'BLOCKED') {
      this.log(`[scheduler] slot ${slot}: last rate not verified - skipping`);
      return;
    }

    this.lastSlot = slot;
    const text = formatRateMessage(state, cfg);
    this.log(`[scheduler] sending hourly broadcast for slot ${slot}`);
    const res = await this.sender.send(text);
    this.history.push({ slot, at: Date.now(), sent: res.sent, failed: res.failed });
    if (this.history.length > 100) this.history.shift();
  }

  /** Manual trigger used by the /api/send-now endpoint. */
  async sendNow() {
    const state = this.store.publicState();
    if (!state.ok || !state.published) return { ok: false, reason: 'no verified rate available' };
    const res = await this.sender.send(formatRateMessage(state, this.cfg));
    return { ok: true, ...res };
  }

  status() {
    const w = this.cfg.whatsapp;
    return {
      window: `${w.scheduleStartHour}:00-${w.scheduleEndHour}:00 IST`,
      intervalMinutes: w.intervalMinutes,
      lastSlot: this.lastSlot,
      recent: this.history.slice(-10),
    };
  }
}

/**
 * WhatsApp sender (whatsapp-web.js).
 *
 * Authenticates once by QR scan from your phone, then persists the session under
 * data/wa-session so restarts do not require re-scanning.
 *
 * IMPORTANT: this drives your own WhatsApp account. It is appropriate for an
 * internal staff group and a small fixed list of numbers, which is how it is
 * configured. Do NOT point it at a large customer list - unsolicited bulk sending
 * from a personal account is what gets numbers banned. For customer broadcasts you
 * need the official Meta Cloud API with an approved template and opt-in consent.
 */

import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

export class WhatsAppSender {
  constructor(cfg, rootDir, log) {
    this.cfg = cfg;
    this.rootDir = rootDir;
    this.log = log || console.log;
    this.client = null;
    this.ready = false;
    this.lastError = null;
    this.sentCount = 0;
    this.lastSentAt = null;
    this.resolvedTargets = [];
  }

  async start() {
    let Client, LocalAuth, qrcode, qrcodePng;
    try {
      ({ Client, LocalAuth } = require('whatsapp-web.js'));
      qrcode = require('qrcode-terminal');
      qrcodePng = require('qrcode');
    } catch (err) {
      this.lastError = 'whatsapp-web.js not installed - run: npm install';
      this.log(`[whatsapp] ${this.lastError}`);
      return false;
    }

    this.client = new Client({
      authStrategy: new LocalAuth({
        clientId: 'aradhana-gold',
        dataPath: path.join(this.rootDir, 'data', 'wa-session'),
      }),
      puppeteer: {
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
      },
    });

    this.client.on('qr', (qr) => {
      this.log('\n[whatsapp] Scan this QR with the phone that should SEND the updates:');
      this.log('           WhatsApp > Settings > Linked Devices > Link a Device\n');
      qrcode.generate(qr, { small: true });
      const pngPath = path.join(this.rootDir, 'data', 'wa-qr.png');
      qrcodePng.toFile(pngPath, qr, { width: 500 }, (err) => {
        if (err) this.log(`[whatsapp] could not write QR image: ${err.message}`);
        else this.log(`[whatsapp] QR image also saved to ${pngPath}`);
      });
    });

    this.client.on('authenticated', () => this.log('[whatsapp] authenticated'));
    this.client.on('auth_failure', (m) => {
      this.lastError = `auth failure: ${m}`;
      this.log(`[whatsapp] ${this.lastError}`);
    });
    this.client.on('disconnected', (r) => {
      this.ready = false;
      this.lastError = `disconnected: ${r}`;
      this.log(`[whatsapp] ${this.lastError}`);
    });

    const readyPromise = new Promise((resolve) => {
      this.client.on('ready', async () => {
        this.ready = true;
        this.lastError = null;
        this.log('[whatsapp] connected and ready');
        await this.resolveTargets();
        resolve(true);
      });
    });

    this.log('[whatsapp] starting client (first run opens a QR code)...');
    this.client.initialize().catch((err) => {
      this.lastError = err.message;
      this.log(`[whatsapp] init failed: ${err.message}`);
    });

    return readyPromise;
  }

  /** Turn configured group names + phone numbers into concrete chat IDs. */
  async resolveTargets() {
    const targets = [];
    const w = this.cfg.whatsapp;

    if (w.groupNames && w.groupNames.length) {
      try {
        const chats = await this.client.getChats();
        for (const wanted of w.groupNames) {
          const match = chats.find(
            (c) => c.isGroup && c.name && c.name.trim().toLowerCase() === String(wanted).trim().toLowerCase()
          );
          if (match) {
            targets.push({ id: match.id._serialized, label: `group "${match.name}"` });
          } else {
            this.log(`[whatsapp] WARNING: group "${wanted}" not found in your chat list`);
          }
        }
      } catch (err) {
        this.log(`[whatsapp] could not list chats: ${err.message}`);
      }
    }

    for (const raw of w.numbers || []) {
      const digits = String(raw).replace(/\D/g, '');
      if (!digits) continue;
      // Bare 10-digit Indian numbers get the 91 country code.
      const full = digits.length === 10 ? `91${digits}` : digits;
      targets.push({ id: `${full}@c.us`, label: `+${full}` });
    }

    this.resolvedTargets = targets;
    this.log(`[whatsapp] ${targets.length} recipient(s): ${targets.map((t) => t.label).join(', ') || 'NONE CONFIGURED'}`);
    return targets;
  }

  async send(text) {
    if (!this.ready) {
      this.log('[whatsapp] not ready - message not sent');
      return { sent: 0, failed: 0, skipped: true };
    }
    if (!this.resolvedTargets.length) await this.resolveTargets();

    let sent = 0, failed = 0;
    for (const t of this.resolvedTargets) {
      try {
        await this.client.sendMessage(t.id, text);
        sent++;
        // Small gap between sends - bursts look automated and risk rate limiting.
        await new Promise((r) => setTimeout(r, 1200));
      } catch (err) {
        failed++;
        this.log(`[whatsapp] send to ${t.label} failed: ${err.message}`);
      }
    }
    this.sentCount += sent;
    this.lastSentAt = Date.now();
    this.log(`[whatsapp] broadcast complete: ${sent} sent, ${failed} failed`);
    return { sent, failed, skipped: false };
  }

  async stop() {
    if (this.client) {
      try { await this.client.destroy(); } catch { /* already gone */ }
    }
    this.ready = false;
  }

  status() {
    return {
      enabled: this.cfg.whatsapp.enabled,
      ready: this.ready,
      error: this.lastError,
      recipients: this.resolvedTargets.map((t) => t.label),
      sentCount: this.sentCount,
      lastSentAt: this.lastSentAt,
    };
  }
}

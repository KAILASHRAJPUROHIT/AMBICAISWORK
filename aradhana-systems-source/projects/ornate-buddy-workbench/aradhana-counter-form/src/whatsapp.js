import path from 'node:path';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

const digits = (v) => String(v || '').replace(/\D/g, '');

function browserExecutable() {
  const candidates = [
    process.env.ARADHANA_BROWSER_PATH,
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Google', 'Chrome', 'Application', 'chrome.exe'),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe')
  ].filter(Boolean);
  return candidates.find((file) => fs.existsSync(file));
}

export class WhatsAppSender {
  constructor(cfg, rootDir, log = console.log) {
    this.cfg = cfg;
    this.rootDir = rootDir;
    this.log = log;
    this.client = null;
    this.ready = false;
    this.actualSender = null;
    this.lastError = null;
    this.qrPending = false;
  }

  async start() {
    if (!this.cfg.enabled) return;
    let Client, LocalAuth, qrcode;
    try {
      ({ Client, LocalAuth } = require('whatsapp-web.js'));
      qrcode = require('qrcode-terminal');
    } catch (err) {
      this.lastError = 'WhatsApp dependencies missing. Run npm install.';
      return;
    }

    const executablePath = browserExecutable();
    if (!executablePath) {
      this.lastError = 'Chrome or Edge was not found. Install either browser, or set ARADHANA_BROWSER_PATH.';
      this.log(`[whatsapp] ${this.lastError}`);
      return;
    }

    this.client = new Client({
      authStrategy: new LocalAuth({
        clientId: this.cfg.clientId || 'aradhana-counter-slip',
        dataPath: path.join(this.rootDir, 'data', 'wa-session')
      }),
      puppeteer: {
        headless: true,
        executablePath,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
      }
    });

    this.client.on('qr', (qr) => {
      this.qrPending = true;
      this.ready = false;
      this.log(`\n[whatsapp] FIRST LOGIN: scan this QR using WhatsApp on +${digits(this.cfg.expectedSender)}`);
      this.log('[whatsapp] WhatsApp > Settings > Linked Devices > Link a Device\n');
      qrcode.generate(qr, { small: true });
    });

    this.client.on('authenticated', () => this.log('[whatsapp] authenticated'));
    this.client.on('auth_failure', (m) => {
      this.ready = false;
      this.lastError = `Authentication failed: ${m}`;
    });
    this.client.on('disconnected', (r) => {
      this.ready = false;
      this.lastError = `Disconnected: ${r}`;
    });
    this.client.on('ready', () => {
      this.qrPending = false;
      this.actualSender = digits(this.client.info?.wid?.user);
      const expected = digits(this.cfg.expectedSender);
      if (expected && this.actualSender !== expected) {
        this.ready = false;
        this.lastError = `Wrong WhatsApp account linked. Expected +${expected}, got +${this.actualSender || 'unknown'}.`;
        this.log(`[whatsapp] ${this.lastError}`);
        return;
      }
      this.ready = true;
      this.lastError = null;
      this.log(`[whatsapp] ready - sender +${this.actualSender}, fixed recipient +${digits(this.cfg.recipient)}`);
    });

    this.client.initialize().catch((err) => {
      this.lastError = err.message;
      this.ready = false;
    });
  }

  async send(text) {
    if (!this.cfg.enabled) return { sent: false, reason: 'disabled' };
    if (!this.ready || !this.client) return { sent: false, reason: this.lastError || 'WhatsApp not ready' };

    const recipient = digits(this.cfg.recipient);
    const id = `${recipient}@c.us`;
    try {
      await this.client.sendMessage(id, text);
      return { sent: true, recipient: `+${recipient}`, sender: `+${this.actualSender}` };
    } catch (err) {
      this.lastError = err.message;
      return { sent: false, reason: err.message };
    }
  }

  status() {
    return {
      enabled: Boolean(this.cfg.enabled),
      ready: this.ready,
      qrPending: this.qrPending,
      expectedSender: `+${digits(this.cfg.expectedSender)}`,
      actualSender: this.actualSender ? `+${this.actualSender}` : null,
      recipient: `+${digits(this.cfg.recipient)}`,
      error: this.lastError
    };
  }
}

import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { RateService, calculateNewLine } from './rates.js';
import { WhatsAppSender } from './whatsapp.js';
import { SubmissionStore } from './storage.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const cfg = JSON.parse(fs.readFileSync(path.join(rootDir, 'config.json'), 'utf8'));

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '256kb' }));
app.use(express.static(path.join(rootDir, 'public'), { maxAge: 0 }));

const rates = new RateService(cfg.rates, rootDir, console.log);
const whatsapp = new WhatsAppSender(cfg.whatsapp, rootDir, console.log);
const store = new SubmissionStore(rootDir);

rates.start();
whatsapp.start();

const money = (n) => Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const clean = (v, max = 500) => String(v ?? '').trim().slice(0, max);
const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

function calcOld(rows = []) {
  return rows.slice(0, 3).map((r, i) => ({
    no: i + 1,
    weight: num(r.weight),
    purity: num(r.purity),
    amount: num(r.amount)
  })).filter((r) => r.weight || r.purity || r.amount);
}

function formatNew(title, form, calc) {
  if (!form?.weight || !form?.purity || !calc) return `${title}: None`;
  return [
    `${title}`,
    `Item: ${clean(form.item) || '—'}`,
    `Weight: ${calc.weight} g | Purity: ${calc.purity}`,
    `Rate: ₹${money(calc.rate)} ${calc.rateUnit} (${calc.rateSource})`,
    `Metal value: ₹${money(calc.metalValue)}`,
    `GST ${calc.gstPercent}%: ₹${money(calc.gst)}`,
    `Total incl. GST: ₹${money(calc.total)}`
  ].join('\n');
}

function formatOld(title, rows) {
  if (!rows.length) return `${title}: None`;
  return `${title}\n` + rows.map((r) => `${r.no}. Wt ${r.weight || '—'} g | Purity ${r.purity || '—'} | Amt ₹${money(r.amount)}`).join('\n');
}

function makeMessage(record) {
  return [
    '*ARADHANA JEWELLERS – COUNTER SLIP*',
    `Ref: ${record.ref}`,
    `Date: ${record.dateIst}`,
    '',
    `Customer: ${record.customer.name || '—'}`,
    `Mobile: ${record.customer.mobile || '—'}`,
    `Address: ${record.customer.address || '—'}`,
    '',
    formatNew('*NEW GOLD*', record.input.newGold, record.calculated.newGold),
    '',
    formatNew('*NEW SILVER*', record.input.newSilver, record.calculated.newSilver),
    '',
    formatOld('*OLD GOLD*', record.oldGold),
    `Old Gold entered amount total: ₹${money(record.oldGoldAmountTotal)} (not deducted from final bill)`,
    '',
    formatOld('*OLD SILVER*', record.oldSilver),
    `Old Silver entered amount total: ₹${money(record.oldSilverAmountTotal)} (not deducted from final bill)`,
    '',
    `URD No.: ${record.urd.no || '—'}`,
    `URD Amount: ${record.urd.amount ? '₹' + money(record.urd.amount) : '—'}`,
    `URD Txn No.: ${record.urd.txnNo || '—'}`,
    '',
    `*FINAL BILL AMOUNT: ₹${money(record.finalBillAmount)}*`,
    `Payment: ${record.payment || '—'}`,
    `Salesman: ${record.salesman || '—'}`,
    `Billing: ${record.billing || '—'}`,
    '',
    `Rate source: ${cfg.rates.url}`,
    'Final bill amount includes NEW items only.'
  ].join('\n');
}

app.get('/api/config', (req, res) => {
  res.json({
    items: cfg.items,
    gstPercent: cfg.rates.gstPercent,
    whatsapp: {
      expectedSender: `+${cfg.whatsapp.expectedSender}`,
      recipient: `+${cfg.whatsapp.recipient}`
    }
  });
});

app.get('/api/rates', async (req, res) => {
  if (!rates.snapshot) await rates.refresh();
  res.status(rates.snapshot ? 200 : 503).json(rates.publicStatus());
});

app.get('/api/status', (req, res) => {
  res.json({ rates: rates.publicStatus(), whatsapp: whatsapp.status() });
});

app.post('/api/submit', async (req, res) => {
  try {
    // Always refresh before billing. If Render is waking up, this may take longer on the first submission.
    await rates.refresh();
    const snapshot = rates.snapshot;
    const body = req.body || {};

    const hasNewGold = num(body.newGold?.weight) > 0;
    const hasNewSilver = num(body.newSilver?.weight) > 0;
    if ((hasNewGold || hasNewSilver) && (!snapshot || !rates.isFresh(snapshot))) {
      return res.status(503).json({ ok: false, error: 'Verified live rate is unavailable or stale. Bill was not submitted.' });
    }

    const newGold = hasNewGold ? calculateNewLine({ metal: 'gold', weight: body.newGold.weight, purity: body.newGold.purity }, snapshot) : null;
    const newSilver = hasNewSilver ? calculateNewLine({ metal: 'silver', weight: body.newSilver.weight, purity: body.newSilver.purity }, snapshot) : null;
    if (hasNewGold && !newGold) return res.status(400).json({ ok:false, error:'New Gold weight/purity could not be calculated.' });
    if (hasNewSilver && !newSilver) return res.status(400).json({ ok:false, error:'New Silver weight/purity could not be calculated.' });

    const oldGold = calcOld(body.oldGold);
    const oldSilver = calcOld(body.oldSilver);
    const oldGoldAmountTotal = oldGold.reduce((a, r) => a + r.amount, 0);
    const oldSilverAmountTotal = oldSilver.reduce((a, r) => a + r.amount, 0);
    const finalBillAmount = Number(((newGold?.total || 0) + (newSilver?.total || 0)).toFixed(2));

    const now = new Date();
    const record = {
      ref: store.nextRef(),
      createdAt: now.toISOString(),
      dateIst: new Intl.DateTimeFormat('en-IN', { timeZone:'Asia/Kolkata', dateStyle:'medium', timeStyle:'short' }).format(now),
      customer: {
        name: clean(body.customer?.name, 120),
        mobile: clean(body.customer?.mobile, 20),
        address: clean(body.customer?.address, 300)
      },
      input: {
        newGold: { item: clean(body.newGold?.item, 80), weight: num(body.newGold?.weight), purity: num(body.newGold?.purity) },
        newSilver: { item: clean(body.newSilver?.item, 80), weight: num(body.newSilver?.weight), purity: num(body.newSilver?.purity) }
      },
      calculated: { newGold, newSilver },
      oldGold,
      oldSilver,
      oldGoldAmountTotal: Number(oldGoldAmountTotal.toFixed(2)),
      oldSilverAmountTotal: Number(oldSilverAmountTotal.toFixed(2)),
      urd: {
        no: clean(body.urd?.no, 80),
        amount: num(body.urd?.amount),
        txnNo: clean(body.urd?.txnNo, 120)
      },
      payment: clean(body.payment, 50),
      salesman: clean(body.salesman, 80),
      billing: clean(body.billing, 80),
      finalBillAmount,
      rateSnapshot: snapshot
    };

    // Save before WhatsApp so a transient WhatsApp issue never loses the slip.
    store.save(record);
    const message = makeMessage(record);
    const waResult = await whatsapp.send(message);

    res.json({ ok: true, record, whatsapp: waResult, message });
  } catch (err) {
    console.error('[submit]', err);
    res.status(500).json({ ok: false, error: err.message || 'Unexpected error' });
  }
});

const server = app.listen(cfg.server.port, cfg.server.host, () => {
  console.log(`\nAradhana Counter Form: http://localhost:${cfg.server.port}`);
  const nets = os.networkInterfaces();
  for (const entries of Object.values(nets)) {
    for (const n of entries || []) {
      if (n.family === 'IPv4' && !n.internal) console.log(`LAN: http://${n.address}:${cfg.server.port}`);
    }
  }
  console.log(`Rates: ${cfg.rates.url}`);
  console.log(`WhatsApp: +${cfg.whatsapp.expectedSender} -> +${cfg.whatsapp.recipient}\n`);
});

process.on('SIGINT', () => { rates.stop(); server.close(() => process.exit(0)); });

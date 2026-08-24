# Aradhana Jewellers — Gold Rate Monitor

Polls the **GOLD INDIAN-BIS 999** rate from Safari Bullions **every second**, runs it through
four independent accuracy checks, publishes your **22KT (95% of 999, without GST)** rate to a
live page, and broadcasts it on WhatsApp hourly from 9 AM to 9 PM IST.

---

## Quick start

```bash
npm install
```

Verify everything works against the live feeds:

```bash
npm run check
```

Run the monitor and live page (no WhatsApp):

```bash
npm run monitor
```

Then open <http://localhost:8080>.

Run the full service including WhatsApp:

```bash
npm start
```

---

## The rate it publishes

| Figure | How it is derived |
|---|---|
| **999 fine (24KT)** | Safari Bullions row `GOLD INDIAN-BIS 999`, **SELL** column, scrip code `2287` |
| **22KT without GST** | `999 × 0.95` — exact, unrounded |
| **22KT with GST** | `22KT × 1.03` |

The 999 row has no BUY price (the feed shows `-`), so the **SELL** value is used. The row's
display name carries a rotating delivery date, so the monitor keys on the stable **scrip code**
and uses the name only as a cross-check.

Change the purity factor or rounding in `config.json` → `business`.

---

## The four accuracy checks

Every single tick is validated by four independent groups. **If any blocking check fails, the
new rate is not published and not sent to WhatsApp** — the last verified rate is held and an
alert goes out.

### 1. Internal structure — blocking
Runs on the Safari payload alone, no network needed.

- **GST invariant** — the feed's own `GOLD RTGS INDIAN 999 (WITH GST)` row must equal
  `999 × 1.03`. This matches to the rupee and is the single strongest check: it proves the
  number parsed is genuinely the ex-GST 999 rate.
- **Purity ordering** — 999 must price above 995, within a believable ratio band.
- **Row identity** — scrip code and product name must both still match.
- **Costing band, high/low envelope, absolute sanity range.**

### 2. Kaka Gold cross-check — blocking
[Kaka Gold](https://kakagold.in) is an independent Zaveri Bazaar dealer running the same
broadcast stack, so its `GOLD 999 BIS APPROVED` row (code `4620`) is directly comparable.

- Warns above **0.35%** disagreement, blocks above **1.0%**.
- Typical live agreement is **~0.03%**.
- Kaka's *own* GST invariant is checked too, so the monitor never validates against a
  silently broken comparator.

### 3. International parity — advisory only
Gold spot (XAU/USD) × USD/INR gives the landed parity price. Confirms Safari's own embedded
spot and FX figures match the outside world, and that the domestic premium sits in a sane band
(typically ~14%).

This group **never blocks a publish**. To make Kaka Gold the sole external reference, set
`validation.parity.enabled: false` in `config.json`.

### 4. Spike and staleness guards — blocking
- **Spike quarantine** — a jump over 1.5% in one second is quarantined and must be confirmed by
  3 consecutive agreeing ticks before it is trusted. Protects against a corrupted tick without
  freezing you out of a genuine market gap.
- **Staleness** — warns if the rate has not moved for 25 minutes during market hours.

Run `npm run check` to see the full report for a live tick.

---

## WhatsApp setup

This drives **your own WhatsApp account** via a linked device.

1. Put your recipients in `config.json`:

```json
"whatsapp": {
  "groupNames": ["Aradhana Staff"],
  "numbers": ["9825012345", "919825067890"]
}
```

- `groupNames` must match the group name **exactly** as it appears in your chat list.
- `numbers` may be bare 10-digit Indian numbers (91 is added) or full international format.

2. Link the phone that will send the messages:

```bash
npm run wa-login
```

Scan the QR with **WhatsApp → Settings → Linked Devices → Link a Device**. The session is
saved to `data/wa-session`, so you only do this once.

3. Start the service:

```bash
npm start
```

It sends on the hour, 9 AM through 9 PM IST — 13 messages a day — and only ever sends a
**verified** rate. If publishing is blocked, it sends an alert instead (at most once every
30 minutes).

Trigger a message manually at any time:

```bash
curl -X POST http://localhost:8080/api/send-now
```

> **Important:** an unofficial client is fine for an internal staff group and a short list of
> known numbers, which is how this is configured. Do **not** point it at a large customer list —
> bulk unsolicited sending from a personal account is what gets numbers banned. Customer
> broadcasts require the official Meta WhatsApp Cloud API with an approved template and opt-in
> consent. `src/whatsapp.js` is a self-contained module, so swapping in Cloud API later only
> means replacing that one file.

---

## HTTP API

| Endpoint | Purpose |
|---|---|
| `GET /` | The live page |
| `GET /api/rate` | Full state — rates, all check results, references, history |
| `GET /api/rate/simple` | Minimal JSON for embedding in your main website or POS |
| `GET /api/stream` | Server-Sent Events, pushes on every tick |
| `GET /api/health` | Health, uptime, tick stats, WhatsApp status |
| `POST /api/send-now` | Send a WhatsApp update immediately |

`/api/rate/simple` returns:

```json
{
  "ok": true,
  "rate_22kt": 153519.05,
  "rate_999": 161599,
  "rate_22kt_with_gst": 158124.62,
  "unit": "per 10 g",
  "status": "VERIFIED",
  "confidence": 100,
  "updated_at_ist": "23 Aug 2026, 12:46:31 PM"
}
```

To protect the manual-send endpoint, set an `ADMIN_TOKEN` environment variable and pass it as
an `x-admin-token` header.

---

## Internal live monitor (Render)

**This is deliberately internal-only — no `live.aradhanajewellers.com`, no custom domain.**
The service is reachable at whatever `*.onrender.com` URL Render assigned it (currently
`https://aradhana-gold-monitor.onrender.com`), which is not linked from the public website and
not advertised anywhere. That URL is not access-restricted (Render's free tier has no
built-in auth), so treat it as "unlisted," not "private" — anyone who has the exact link can
open it. If real access control is ever needed, a shared password/token gate can be added to
`src/server.js` at that point; nothing about the current setup blocks doing that later.

**Architecture: the poller + live page + API run in the cloud (Render), independent of this
PC. WhatsApp keeps running here on your laptop**, because it needs a phone-linked browser
session that free-tier cloud hosts handle badly (they sleep on idle, and a persistent Chromium
session is heavy on a free plan's memory / risks getting logged out). Both instances poll
Safari Bullions and Kaka Gold independently and validate the same way, so they always agree —
there's no dependency between them, and no single point of failure. If the laptop is off, the
live page and API keep working; if Render has an outage, WhatsApp still sends from here.

### The counter iPad (`/board.html`) is a special case - it needs the local relay

`public/board.html` is the full-bleed, numbers-only kiosk display. It's served by both
instances identically, but **the counter iPad (an iPad Mini 2) must use the local URL**
(`http://<this-PC's-LAN-IP>:8080/board.html`), not the cloud one, and that's not going to
change without new hardware:

- Render force-redirects all HTTP to HTTPS (confirmed - there's no way to serve the cloud
  copy over plain HTTP even if we wanted to).
- The iPad Mini 2 is stuck on iOS 12 (Apple never updated it further), and iOS 12's Safari
  cannot complete a modern HTTPS handshake with Render's edge - "Safari could not establish a
  secure connection." This is a hardware/OS ceiling on the iPad itself, not fixable from the
  app or by changing where it's hosted.

**This does not mean the rate data depends on the laptop.** Local and cloud each poll Safari
Bullions and Kaka Gold independently - the laptop is acting purely as a plain-HTTP relay for
this one old device, nothing more. Every other device (phones, a newer tablet, anything with
normal HTTPS support) should just use the cloud URL directly and is fully laptop-independent.

Because of this, the local instance is set up to survive as much as reasonably possible without
becoming a second full deployment project:
- Runs under `pm2` (`pm2 start src/index.js --name gold-monitor -- --no-whatsapp`), which
  restarts it automatically if it crashes.
- `pm2-windows-startup` registers a registry `Run` key so `pm2 resurrect` fires at login,
  bringing it back after a normal reboot. **Caveat:** this fires at user *login*, not raw
  power-on - if Windows restarts unattended and sits at the lock screen, it stays down until
  someone logs in. Closing that gap fully would mean enabling Windows auto-login, which trades
  away the login password, so it's left as a manual choice rather than done silently.
- Windows sleep is already disabled system-wide (standby idle = never, both AC and battery),
  so sleep is not a factor here.

If the counter display is ever upgraded to a tablet from roughly the last 6 years, point it at
the cloud URL instead and this whole local-relay setup becomes unnecessary for it.

### Cloud (Render) — poller, live page, API

Repo: `AradhanaJewellers/aradhana-gold-monitor` on GitHub. Deployed via `render.yaml` (Blueprint)
at the repo root — build/start commands and the env var below are defined there, not entered
by hand in the dashboard.

- Build command: `npm install`
- Start command: `npm run monitor` (this is `node src/index.js --no-whatsapp` — no WhatsApp,
  no QR prompt, nothing that needs a person present)
- `PUPPETEER_SKIP_DOWNLOAD=true`: this service never launches Chromium (WhatsApp is excluded
  via the start command above), but `npm install` would otherwise still download a ~300MB
  Chromium binary as part of the `whatsapp-web.js` dependency. This lives in `render.yaml`,
  scoped to this Render service only — deliberately **not** in `.npmrc` or anywhere else that
  would also apply locally, where WhatsApp genuinely needs that Chromium install.
- Plan: **Free** is enough — this is a plain Express server + a 1-second `fetch()` poll.

**Free-tier caveats to know about:**
- Render's free web services **sleep after ~15 minutes with no HTTP traffic** and take
  20–50s to wake on the next request. A monitor nobody is actively viewing will go quiet
  between visits — the first visitor after a gap sees a short delay, then it's live again.
  If that's a problem, Render's cheapest paid tier (~$7/mo) removes the sleep.
- The filesystem is **ephemeral** — `data/history.json` and `logs/*.csv` reset on every
  redeploy/restart. The chart history and audit trail persist fine while it's running, they
  just don't survive a redeploy. That's fine for the cloud mirror since this PC's local
  instance (if you still run one) keeps its own permanent history and logs.

### Local (this PC) — WhatsApp only

```bash
npm run wa-login
```

to link WhatsApp once (see [WhatsApp setup](#whatsapp-setup) above), then keep it running so
the hourly broadcast fires. Install it as a Windows service so it survives reboots:

```bash
npm install -g pm2 pm2-windows-startup
pm2 start src/index.js --name gold-monitor-whatsapp
pm2 save
pm2-startup install
```

The local instance still runs its own full poller too (same `npm start` — WhatsApp needs the
current rate to broadcast), it just isn't what the public `live.aradhanajewellers.com` page
points at anymore.

### Alternative: embed instead of a separate page

If you'd rather not run a dedicated page at all, keep the monitor private and just call
`/api/rate/simple` from a widget on aradhanajewellers.com.

---

## Files

```
config.json          all settings - recipients, thresholds, schedule
src/feed.js          Chirayu broadcast feed client + parser
src/validate.js      the four check groups and the verdict
src/references.js    Kaka Gold + international parity sources
src/engine.js        the 1-second poll loop
src/store.js         state, history, daily CSV audit log
src/scheduler.js     hourly WhatsApp broadcast + message formatting
src/whatsapp.js      WhatsApp client (swap this file to change provider)
src/server.js        HTTP API + SSE
src/selftest.js      npm run check
public/index.html    the live page
logs/rates-*.csv     every rate change, with the verdict that approved it
```

`logs/rates-*.csv` is written only when the rate actually changes, so it stays a readable audit
trail rather than 3,600 identical rows an hour.

---

## Load on the source

Safari's own website polls this same endpoint every **500 ms**, so a 1-second poll is gentler
than their normal web client. Kaka Gold is polled every 5 seconds and the international
reference every 60 seconds. Ticks never overlap — if a fetch runs long the next one is skipped
rather than stacked.

/** HTTP API + live page - internal-only, unlisted URL (see README). */

import express from 'express';
import path from 'node:path';
import { istPretty } from './time.js';

export function createServer(cfg, store, ctx, log) {
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json());

  app.use((req, res, next) => {
    // The rate is public information; allow embedding it in the main site.
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 'no-store');
    next();
  });

  app.use(express.static(path.join(ctx.rootDir, 'public'), { maxAge: 0 }));

  /** Full state - what the live page renders. */
  app.get('/api/rate', (req, res) => res.json(store.publicState()));

  /** Minimal payload for embedding elsewhere (website widget, POS, etc). */
  app.get('/api/rate/simple', (req, res) => {
    const s = store.publicState();
    if (!s.ok) return res.status(503).json({ ok: false, error: 'no verified rate yet' });
    res.json({
      ok: true,
      rate_22kt: s.published.rate22kt,
      rate_999: s.published.rate999,
      rate_22kt_with_gst: s.published.rate22ktWithGst,
      unit: s.published.unit,
      status: s.published.status,
      confidence: s.published.confidence,
      updated_at: s.published.at,
      updated_at_ist: s.published.atIst,
    });
  });

  app.get('/api/health', (req, res) => {
    const s = store.publicState();
    const healthy = s.ok && s.live && s.live.status !== 'BLOCKED';
    res.status(healthy ? 200 : 503).json({
      healthy,
      status: s.live ? s.live.status : 'STARTING',
      uptimeSec: Math.round((Date.now() - store.stats.startedAt) / 1000),
      stats: store.stats,
      whatsapp: ctx.sender ? ctx.sender.status() : { enabled: false },
      scheduler: ctx.scheduler ? ctx.scheduler.status() : null,
      serverTimeIst: istPretty(),
    });
  });

  /** Server-Sent Events - pushes a new state on every tick. */
  app.get('/api/stream', (req, res) => {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    res.write(`data: ${JSON.stringify(store.publicState())}\n\n`);

    const unsubscribe = store.subscribe((payload) => {
      res.write(`data: ${JSON.stringify(payload)}\n\n`);
    });
    // Comment frames keep proxies from closing an idle connection.
    const keepAlive = setInterval(() => res.write(': keep-alive\n\n'), 20000);

    req.on('close', () => {
      unsubscribe();
      clearInterval(keepAlive);
    });
  });

  /** Manual broadcast. Guarded by ADMIN_TOKEN when one is set. */
  app.post('/api/send-now', async (req, res) => {
    const required = process.env.ADMIN_TOKEN;
    if (required && req.get('x-admin-token') !== required) {
      return res.status(401).json({ ok: false, error: 'unauthorized' });
    }
    if (!ctx.scheduler) return res.status(503).json({ ok: false, error: 'scheduler not running' });
    try {
      res.json(await ctx.scheduler.sendNow());
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  /** Which layout every /board.html client should show, plus the refresh
   * token they poll for. Read by every board every ~1s via /api/rate's
   * boardControl field (below), so no separate endpoint is needed for that. */
  const VALID_LAYOUTS = ['fullbleed', 'diagonal', 'medallion', 'bands', 'waterfall'];
  const checkAdminToken = (req, res) => {
    const required = process.env.ADMIN_TOKEN;
    if (required && req.get('x-admin-token') !== required) {
      res.status(401).json({ ok: false, error: 'unauthorized' });
      return false;
    }
    return true;
  };

  app.post('/api/board-control', (req, res) => {
    if (!checkAdminToken(req, res)) return;
    const { layout, forceRefresh } = req.body || {};

    if (layout !== undefined) {
      if (!VALID_LAYOUTS.includes(layout)) {
        return res.status(400).json({ ok: false, error: `layout must be one of ${VALID_LAYOUTS.join(', ')}` });
      }
      store.setBoardLayout(layout);
    }
    if (forceRefresh) store.forceBoardRefresh();

    res.json({ ok: true, boardControl: store.boardControl });
  });

  const server = app.listen(cfg.server.port, cfg.server.host, () => {
    log(`[server] listening on http://${cfg.server.host}:${cfg.server.port}`);
    log(`[server] live page  -> http://localhost:${cfg.server.port}/`);
    log(`[server] JSON API   -> http://localhost:${cfg.server.port}/api/rate/simple`);
  });

  return server;
}

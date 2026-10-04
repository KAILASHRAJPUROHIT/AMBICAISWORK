import { useCallback, useEffect, useRef, useState } from 'react';
import type { IndoorPlan } from '../api/indoor';

export type PlanTool = 'view' | 'wall' | 'zone' | 'erase' | 'point';

export interface PlanDot {
  id: string | number;
  x: number;
  y: number;
}

export interface PlanDevice extends PlanDot {
  label: string;
  spreadM: number;
  stale: boolean;
}

interface Props {
  plan: IndoorPlan;
  image: string | null;
  tool: PlanTool;
  /** Called with the edited plan when a wall/zone is added or erased. */
  onPlanChange?: (plan: IndoorPlan) => void;
  /** Called with plan coordinates (metres) when the "point" tool is clicked. */
  onPick?: (x: number, y: number) => void;
  surveyPoints?: PlanDot[];
  devices?: PlanDevice[];
  pending?: { x: number; y: number } | null;
}

const SNAP_M = 0.1;
const ERASE_RADIUS_M = 0.5;

function snap(v: number): number {
  return Math.round(v / SNAP_M) * SNAP_M;
}

function distToSegment(px: number, py: number, w: number[]): number {
  const [x1, y1, x2, y2] = w;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/**
 * Draws the store floor plan (picture, grid, walls, zones, survey points, devices) and edits it with simple tools.
 * Plan coordinates are metres with y growing upward; the canvas flips y so the picture is the right way up.
 */
export function IndoorPlanCanvas({ plan, image, tool, onPlanChange, onPick, surveyPoints, devices, pending }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(640);
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);

  const scale = width / plan.widthM; // px per metre
  const height = Math.max(120, Math.round(plan.heightM * scale));

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(280, Math.floor(el.clientWidth)));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!image) { setImg(null); return; }
    const i = new Image();
    i.onload = () => setImg(i);
    i.src = image;
  }, [image]);

  useEffect(() => { setStart(null); }, [tool]);

  const toPx = useCallback((x: number, y: number): [number, number] => [x * scale, height - y * scale], [scale, height]);

  useEffect(() => {
    const c = canvasRef.current;
    const ctx = c?.getContext('2d');
    if (!c || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = width * dpr;
    c.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#f7f8fa';
    ctx.fillRect(0, 0, width, height);
    if (img) {
      ctx.globalAlpha = 0.85;
      ctx.drawImage(img, 0, 0, width, height);
      ctx.globalAlpha = 1;
    }
    // Grid: light every metre (when roomy), stronger every 5 m.
    for (let m = 0; m <= plan.widthM + 1e-6; m += 1) {
      const major = m % 5 === 0;
      if (!major && scale < 14) continue;
      const [px] = toPx(m, 0);
      ctx.strokeStyle = major ? 'rgba(60,70,90,.28)' : 'rgba(60,70,90,.10)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, height); ctx.stroke();
      if (major) { ctx.fillStyle = 'rgba(40,50,70,.7)'; ctx.font = '10px system-ui'; ctx.fillText(`${m} m`, px + 2, height - 3); }
    }
    for (let m = 0; m <= plan.heightM + 1e-6; m += 1) {
      const major = m % 5 === 0;
      if (!major && scale < 14) continue;
      const [, py] = toPx(0, m);
      ctx.strokeStyle = major ? 'rgba(60,70,90,.28)' : 'rgba(60,70,90,.10)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(width, py); ctx.stroke();
      if (major && m > 0) { ctx.fillStyle = 'rgba(40,50,70,.7)'; ctx.font = '10px system-ui'; ctx.fillText(`${m} m`, 3, py - 2); }
    }
    // Zones.
    for (const z of plan.zones) {
      const [x1, y1] = toPx(z.x, z.y + z.h);
      ctx.fillStyle = 'rgba(46,125,255,.14)';
      ctx.strokeStyle = 'rgba(46,125,255,.7)';
      ctx.lineWidth = 1.5;
      ctx.fillRect(x1, y1, z.w * scale, z.h * scale);
      ctx.strokeRect(x1, y1, z.w * scale, z.h * scale);
      ctx.fillStyle = '#1f4fb4';
      ctx.font = '600 11px system-ui';
      ctx.fillText(z.name, x1 + 4, y1 + 13);
    }
    // Walls.
    ctx.strokeStyle = '#2b2f3a';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    for (const w of plan.walls) {
      const [ax, ay] = toPx(w[0], w[1]);
      const [bx, by] = toPx(w[2], w[3]);
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    }
    ctx.strokeStyle = '#2b2f3a';
    ctx.lineWidth = 2;
    ctx.strokeRect(1, 1, width - 2, height - 2);
    // Rubber band for the wall / zone being drawn.
    if (start && hover) {
      const [ax, ay] = toPx(start.x, start.y);
      const [bx, by] = toPx(hover.x, hover.y);
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = '#e0522d';
      ctx.lineWidth = 2;
      if (tool === 'wall') { ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); }
      if (tool === 'zone') ctx.strokeRect(Math.min(ax, bx), Math.min(ay, by), Math.abs(bx - ax), Math.abs(by - ay));
      ctx.setLineDash([]);
    }
    // Survey points.
    for (const p of surveyPoints ?? []) {
      const [px, py] = toPx(p.x, p.y);
      ctx.fillStyle = 'rgba(20,150,90,.85)';
      ctx.beginPath(); ctx.arc(px, py, 3.5, 0, Math.PI * 2); ctx.fill();
    }
    // Where the admin is about to record.
    if (pending) {
      const [px, py] = toPx(pending.x, pending.y);
      ctx.strokeStyle = '#e0522d';
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(px, py, 9, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(px - 13, py); ctx.lineTo(px + 13, py); ctx.moveTo(px, py - 13); ctx.lineTo(px, py + 13); ctx.stroke();
    }
    // Devices: a dot, a halo showing how unsure the position is, and a name.
    for (const d of devices ?? []) {
      const [px, py] = toPx(d.x, d.y);
      const colour = d.stale ? '140,150,165' : '230,70,40';
      if (d.spreadM > 0) {
        ctx.fillStyle = `rgba(${colour},.15)`;
        ctx.strokeStyle = `rgba(${colour},.5)`;
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(px, py, Math.max(6, d.spreadM * scale), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
      ctx.fillStyle = `rgb(${colour})`;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(px, py, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.font = '600 11px system-ui';
      const tw = ctx.measureText(d.label).width;
      const lx = Math.min(px + 9, width - tw - 6);
      ctx.fillStyle = 'rgba(255,255,255,.88)';
      ctx.fillRect(lx - 2, py - 18, tw + 6, 15);
      ctx.fillStyle = '#222';
      ctx.fillText(d.label, lx + 1, py - 7);
    }
  }, [plan, img, width, height, scale, toPx, start, hover, tool, surveyPoints, devices, pending]);

  const eventToPlan = (e: React.PointerEvent<HTMLCanvasElement>): { x: number; y: number } => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * plan.widthM;
    const y = plan.heightM - ((e.clientY - r.top) / r.height) * plan.heightM;
    return { x: Math.max(0, Math.min(plan.widthM, x)), y: Math.max(0, Math.min(plan.heightM, y)) };
  };

  const onClick = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const p = eventToPlan(e);
    if (tool === 'point') { onPick?.(snap(p.x), snap(p.y)); return; }
    if (tool === 'erase' && onPlanChange) {
      let bestWall = -1;
      let bestD = ERASE_RADIUS_M;
      plan.walls.forEach((w, i) => { const d = distToSegment(p.x, p.y, w); if (d < bestD) { bestD = d; bestWall = i; } });
      if (bestWall >= 0) { onPlanChange({ ...plan, walls: plan.walls.filter((_, i) => i !== bestWall) }); return; }
      const inside = plan.zones
        .map((z, i) => ({ z, i }))
        .filter(({ z }) => p.x >= z.x && p.x <= z.x + z.w && p.y >= z.y && p.y <= z.y + z.h)
        .sort((a, b) => a.z.w * a.z.h - b.z.w * b.z.h)[0];
      if (inside) onPlanChange({ ...plan, zones: plan.zones.filter((_, i) => i !== inside.i) });
      return;
    }
    if ((tool === 'wall' || tool === 'zone') && onPlanChange) {
      const q = { x: snap(p.x), y: snap(p.y) };
      if (!start) { setStart(q); return; }
      if (tool === 'wall') {
        if (Math.hypot(q.x - start.x, q.y - start.y) >= 0.2) {
          onPlanChange({ ...plan, walls: [...plan.walls, [start.x, start.y, q.x, q.y]] });
        }
        // Keep drawing from the end of the last wall, so a room outline is a run of clicks.
        setStart(q);
      } else {
        setStart(null);
        const w = Math.abs(q.x - start.x);
        const h = Math.abs(q.y - start.y);
        if (w < 0.3 || h < 0.3) return;
        const name = window.prompt('Name this zone (for example "Counter 2" or "Vault")');
        if (name && name.trim()) {
          onPlanChange({
            ...plan,
            zones: [...plan.zones, { name: name.trim(), x: Math.min(q.x, start.x), y: Math.min(q.y, start.y), w, h }],
          });
        }
      }
    }
  };

  return (
    <div ref={wrapRef} className="indoor-canvas-wrap">
      <canvas
        ref={canvasRef}
        style={{ width, height, display: 'block', borderRadius: 6, touchAction: 'manipulation',
          cursor: tool === 'view' ? 'default' : 'crosshair', border: '1px solid var(--line, #cfd5de)' }}
        onPointerDown={onClick}
        onPointerMove={(e) => { if (start) setHover(eventToPlan(e)); }}
        onContextMenu={(e) => { e.preventDefault(); setStart(null); }}
        aria-label="Store floor plan"
      />
      {start && <p className="muted" style={{ marginTop: 6 }}>
        {tool === 'wall' ? 'Click the next corner. Right-click or pick another tool to stop.' : 'Click the opposite corner.'}
      </p>}
    </div>
  );
}

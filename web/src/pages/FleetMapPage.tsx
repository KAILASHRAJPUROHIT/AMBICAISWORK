import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AppShell } from '../ui/AppShell';
import { useToast } from '../ui/toast';
import { useDevices } from '../data/useDevices';
import { getTelemetry } from '../api/telemetry';
import { listLocations, type LocationFix } from '../api/deviceLocations';
import type { DeviceView } from '../api/devices';
import { fmtRelative } from '../ui/format';

/** Map tiles. The public OpenStreetMap servers are fine for a handful of admins; for heavier use point
 *  VITE_TILE_URL at a tile provider that allows it (for example your own tile server). */
const TILE_URL: string = (import.meta.env.VITE_TILE_URL as string | undefined) || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';

/** A position older than this is drawn grey. */
const STALE_MS = 30 * 60_000;

interface Where { device: DeviceView; lat: number; lon: number; accuracyM?: number; at: number }

const RANGES: Array<[string, number]> = [['Last 4 hours', 4 * 3600e3], ['Today', 0], ['Last 24 hours', 24 * 3600e3], ['Last 7 days', 7 * 24 * 3600e3]];

function rangeStart(ms: number): number {
  if (ms > 0) return Date.now() - ms;
  const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime();
}

function csvOf(fixes: LocationFix[]): string {
  const rows = fixes.map((f) => [new Date(f.capturedAt).toISOString(), f.lat, f.lon, f.accuracy ?? '', f.provider ?? ''].join(','));
  return `time,lat,lon,accuracy_m,provider\n${rows.join('\n')}\n`;
}

export function FleetMapPage() {
  const toast = useToast();
  const { devices } = useDevices();
  const [where, setWhere] = useState<Where[]>([]);
  const [updated, setUpdated] = useState<number | null>(null);
  const [selected, setSelected] = useState<DeviceView | null>(null);
  const [rangeMs, setRangeMs] = useState(RANGES[0][1]);
  const [trail, setTrail] = useState<LocationFix[]>([]); // oldest first
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);

  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const fleetLayer = useRef<L.LayerGroup | null>(null);
  const trailLayer = useRef<L.LayerGroup | null>(null);
  const fitted = useRef(false);

  const refresh = useCallback(async () => {
    const out: Where[] = [];
    await Promise.all(devices.map(async (device) => {
      const t = await getTelemetry(device.number).catch(() => null);
      const loc = t?.dynamic?.location as { lat?: number; lon?: number; accuracyM?: number; capturedAt?: number } | undefined;
      if (loc && typeof loc.lat === 'number' && typeof loc.lon === 'number') {
        out.push({ device, lat: loc.lat, lon: loc.lon, accuracyM: loc.accuracyM, at: Number(loc.capturedAt) || 0 });
      }
    }));
    setWhere(out);
    setUpdated(Date.now());
  }, [devices]);

  useEffect(() => {
    if (devices.length === 0) return;
    void refresh();
    const t = window.setInterval(() => { void refresh(); }, 30_000);
    return () => window.clearInterval(t);
  }, [devices, refresh]);

  // Map setup (once).
  useEffect(() => {
    const el = elRef.current;
    if (!el || mapRef.current) return;
    const map = L.map(el, { worldCopyJump: true }).setView([20.6, 78.9], 5);
    L.tileLayer(TILE_URL, { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map);
    fleetLayer.current = L.layerGroup().addTo(map);
    trailLayer.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // Fleet markers.
  useEffect(() => {
    const layer = fleetLayer.current;
    const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();
    const pts: Array<[number, number]> = [];
    for (const w of where) {
      const stale = Date.now() - w.at > STALE_MS;
      const colour = stale ? '#8c96a6' : '#e0522d';
      const name = w.device.description || w.device.number;
      if (w.accuracyM) L.circle([w.lat, w.lon], { radius: w.accuracyM, color: colour, weight: 1, fillOpacity: 0.08 }).addTo(layer);
      L.circleMarker([w.lat, w.lon], { radius: 8, color: '#fff', weight: 2, fillColor: colour, fillOpacity: 1 })
        .bindTooltip(`${name} · ${fmtRelative(w.at)}${stale ? ' (stale)' : ''}`, { permanent: true, direction: 'top', offset: [0, -8] })
        .on('click', () => setSelected(w.device))
        .addTo(layer);
      pts.push([w.lat, w.lon]);
    }
    if (pts.length && !fitted.current) {
      map.fitBounds(L.latLngBounds(pts), { padding: [60, 60], maxZoom: 17 });
      fitted.current = true;
    }
  }, [where]);

  // Trail for the selected device.
  useEffect(() => {
    if (!selected) { setTrail([]); return; }
    let live = true;
    void listLocations(selected.number, rangeStart(rangeMs)).then((fixes) => {
      if (!live) return;
      const chrono = [...fixes].sort((a, b) => a.capturedAt - b.capturedAt);
      setTrail(chrono);
      setIdx(Math.max(0, chrono.length - 1));
      setPlaying(false);
    }).catch((e) => { if (live) toast.push('err', 'Could not load the trail', e instanceof Error ? e.message : ''); });
    return () => { live = false; };
  }, [selected, rangeMs, toast]);

  useEffect(() => {
    if (!playing) return;
    if (idx >= trail.length - 1) { setPlaying(false); return; }
    const t = window.setTimeout(() => setIdx((i) => Math.min(trail.length - 1, i + 1)), 350);
    return () => window.clearTimeout(t);
  }, [playing, idx, trail.length]);

  useEffect(() => {
    const layer = trailLayer.current;
    const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();
    if (trail.length === 0) return;
    const pts = trail.map((f) => [f.lat, f.lon] as [number, number]);
    L.polyline(pts, { color: '#3b82f6', weight: 3, opacity: 0.35 }).addTo(layer);
    L.polyline(pts.slice(0, idx + 1), { color: '#3b82f6', weight: 4, opacity: 0.9 }).addTo(layer);
    const cur = trail[Math.min(idx, trail.length - 1)];
    L.circleMarker([cur.lat, cur.lon], { radius: 9, color: '#fff', weight: 2, fillColor: '#2563eb', fillOpacity: 1 })
      .bindTooltip(new Date(cur.capturedAt).toLocaleString(), { permanent: true, direction: 'bottom', offset: [0, 8] })
      .addTo(layer);
    if (idx === trail.length - 1 && !playing) map.fitBounds(L.latLngBounds(pts), { padding: [60, 60], maxZoom: 18 });
  }, [trail, idx, playing]);

  const exportCsv = () => {
    if (!selected || trail.length === 0) return;
    const blob = new Blob([csvOf(trail)], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trail-${selected.description || selected.number}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const sorted = useMemo(() => [...where].sort((a, b) => b.at - a.at), [where]);
  const cur = trail.length ? trail[Math.min(idx, trail.length - 1)] : null;

  return (
    <AppShell title="Fleet map">
      <div className="page-head">
        <div>
          <p className="ais-eyebrow">LOCATION</p>
          <h1>Fleet map</h1>
          <p className="page-sub">Every device's last known position. Pick one to replay where it has been.</p>
        </div>
        <span className="muted">{updated ? `updated ${fmtRelative(updated)}` : 'loading…'}</span>
      </div>

      <section className="panel fleetmap">
        <div ref={elRef} className="fleetmap-canvas" role="application" aria-label="Fleet map" />
        {selected && (
          <div className="fleetmap-trail">
            <div className="fleetmap-trail-head">
              <strong>{selected.description || selected.number}</strong>
              <select id="fleetmap-range" aria-label="Trail period" value={rangeMs} onChange={(e) => setRangeMs(Number(e.target.value))}>
                {RANGES.map(([label, ms]) => <option key={label} value={ms}>{label}</option>)}
              </select>
              <button className="btn btn-sm" onClick={() => setSelected(null)}>Close</button>
            </div>
            {trail.length === 0 ? <p className="muted">No positions in this period.</p> : (
              <>
                <div className="fleetmap-play">
                  <button className="btn btn-sm" onClick={() => { if (idx >= trail.length - 1) setIdx(0); setPlaying((p) => !p); }}>
                    {playing ? 'Pause' : 'Play'}
                  </button>
                  <input id="fleetmap-slider" type="range" min={0} max={trail.length - 1} value={Math.min(idx, trail.length - 1)}
                    aria-label="Trail position" onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)); }} />
                  <button className="btn btn-sm" onClick={exportCsv}>Export CSV</button>
                </div>
                <p className="muted">
                  {trail.length} position{trail.length === 1 ? '' : 's'}
                  {cur ? ` · ${new Date(cur.capturedAt).toLocaleString()}${cur.accuracy ? ` · ±${Math.round(cur.accuracy)} m` : ''}` : ''}
                </p>
              </>
            )}
          </div>
        )}
        <div className="fleetmap-list">
          {sorted.map((w) => {
            const stale = Date.now() - w.at > STALE_MS;
            return (
              <button key={w.device.id} className={`fleetmap-row${selected?.id === w.device.id ? ' on' : ''}`} onClick={() => setSelected(w.device)}>
                <strong>{w.device.description || w.device.number}</strong>
                <span className="muted">{w.accuracyM ? `±${Math.round(w.accuracyM)} m · ` : ''}<span style={stale ? { color: 'var(--warn, #d9822b)' } : undefined}>{fmtRelative(w.at)}{stale ? ' (stale)' : ''}</span></span>
              </button>
            );
          })}
          {sorted.length === 0 && <p className="muted">No device has reported a position yet.</p>}
        </div>
      </section>
    </AppShell>
  );
}

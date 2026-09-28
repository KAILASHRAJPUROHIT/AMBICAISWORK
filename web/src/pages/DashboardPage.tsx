import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../ui/AppShell';
import { useDevices } from '../data/useDevices';
import { useFleetPulse, updateWindowState, UPDATE_WINDOW } from '../data/FleetPulse';
import { statusMeta, isOnline as isOnlineByRecency } from '../ui/status';
import { fmtRelative, orDash } from '../ui/format';
import { getEvents, type DeviceEvent } from '../api/events';
import { getAppUsage, fmtDuration, dayStart, type AppUsageRow } from '../api/reports';
import { ACTIVITY_NOISE } from '../components/EventTimeline';
import type { DeviceView, ConfigurationLookup } from '../api/devices';
import type { TelemetrySnapshot } from '../api/telemetry';
import { appColorMap } from '../ui/palette';

type Bucket = 'online' | 'attention' | 'offline';

export const EVENT_VERBS: Record<string, string> = {
  boot: 'booted',
  appInstalled: 'installed an app',
  appUninstalled: 'removed an app',
  commandResult: 'ran a command',
  connectivityChange: 'changed network',
  lowBattery: 'reported low battery',
  enrolled: 'enrolled',
  kioskEnter: 'started kiosk',
  kioskExit: 'exited kiosk',
  quickControl: 'changed a Quick Control',
  crash: 'agent crashed',
  kioskCrashLoop: 'kiosk crash loop',
  selfUninstall: 'started an uninstall',
};

function configName(d: DeviceView, configs: Record<string, ConfigurationLookup>): string {
  if (d.configurationId == null) return 'Unassigned';
  return configs[String(d.configurationId)]?.name ?? 'Unassigned';
}

function bucketOf(d: DeviceView, now?: number): Bucket {
  // Offline first (recency of last check-in); a still-reporting device with a config issue is
  // "attention". statusCode alone can't say offline — it stays green after a factory reset.
  if (!isOnlineByRecency(d.lastUpdate, now)) return 'offline';
  return statusMeta(d.statusCode).tone === 'warn' ? 'attention' : 'online';
}

interface ActivityItem {
  key: string;
  device: DeviceView;
  ev: DeviceEvent;
  /** Consecutive identical events (same device + type) folded into this one. */
  count: number;
}

const HEALTH: Record<Bucket, { label: string; cls: string }> = {
  online: { label: 'Healthy', cls: 'ok' },
  attention: { label: 'Warning', cls: 'warn' },
  offline: { label: 'Offline', cls: 'fail' },
};

function flag(t: TelemetrySnapshot | undefined, key: string): boolean | null {
  const v = t?.dynamic?.[key];
  return typeof v === 'boolean' ? v : null;
}

function network(t: TelemetrySnapshot | undefined): string {
  const dyn = t?.dynamic;
  if (!dyn) return '—';
  if (typeof dyn.wifiSsid === 'string' && dyn.wifiSsid) return dyn.wifiSsid;
  if (dyn.networkType === 'cellular') return typeof dyn.cellularOperator === 'string' ? dyn.cellularOperator : 'Cellular';
  return typeof dyn.networkType === 'string' && dyn.networkType ? dyn.networkType : 'offline';
}

/** Short node label for the mesh: "TAB PRO" -> "TP", "TAB1" -> "T1", "REDMI14R" -> "RE". */
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  const w = words[0] ?? '?';
  const m = w.match(/^([A-Za-z]+)(\d+)$/);
  return (m ? m[1][0] + m[2].slice(-1) : w.slice(0, 2)).toUpperCase();
}

/** Animates a number towards its new value whenever the value changes. */
function useCountUp(target: number, ms = 900): number {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    if (a === target || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      from.current = target;
      setV(target);
      return;
    }
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      setV(Math.round(a + (target - a) * e));
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function Count({ value }: { value: number }) {
  return <>{useCountUp(value)}</>;
}

function ActivityIcon({ type }: { type: string }) {
  const common = {
    width: 14,
    height: 14,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };
  switch (type) {
    case 'appInstalled':
    case 'enrolled':
      return (
        <svg {...common}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      );
    case 'appUninstalled':
      return (
        <svg {...common}>
          <path d="M5 12h14" />
        </svg>
      );
    case 'boot':
      return (
        <svg {...common}>
          <path d="M21 12a9 9 0 1 1-3-6.7" />
          <path d="M21 4v5h-5" />
        </svg>
      );
    case 'commandResult':
      return (
        <svg {...common}>
          <path d="M20 6 9 17l-5-5" />
        </svg>
      );
    case 'lowBattery':
    case 'connectivityChange':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
  }
}

interface MeshNode {
  d: DeviceView;
  b: Bucket;
  battery: number | null;
  charging: boolean;
}

/**
 * Orbital device mesh. Every visual is live data: ring colour = health, outer arc = battery,
 * link flow speed = how recently the device checked in, bolt = charging.
 */
function DeviceMesh({ nodes, now, onOpen }: { nodes: MeshNode[]; now: number; onOpen: (d: DeviceView) => void }) {
  const C = 190;
  const n = Math.max(nodes.length, 1);
  const placed = nodes.map((node, i) => {
    const ring = n > 6 && i % 2 ? 156 : 132;
    const a = (-90 + (360 / n) * i) * (Math.PI / 180);
    return { ...node, x: C + ring * Math.cos(a), y: C + ring * Math.sin(a) };
  });
  const sweepEnd = { x: C + 176 * Math.cos(-0.7), y: C + 176 * Math.sin(-0.7) };
  const ARC = 2 * Math.PI * 21;
  return (
    <svg className="mesh-svg" viewBox="0 0 380 392" role="img" aria-label="Device mesh">
      <defs>
        <radialGradient id="meshCore" cx="50%" cy="40%" r="60%">
          <stop offset="0" stopColor="#7cf3ff" />
          <stop offset=".55" stopColor="#3b82f6" />
          <stop offset="1" stopColor="#a64dff" />
        </radialGradient>
        <linearGradient id="meshSweep" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#22d3ee" stopOpacity="0" />
          <stop offset="1" stopColor="#22d3ee" stopOpacity=".26" />
        </linearGradient>
      </defs>
      {[70, 132, 156, 176].map((r) => (
        <circle key={r} cx={C} cy={C} r={r} className="mesh-ring" />
      ))}
      <g className="mesh-sweep">
        <path d={`M${C} ${C} L${C + 176} ${C} A176 176 0 0 0 ${sweepEnd.x} ${sweepEnd.y} Z`} fill="url(#meshSweep)" />
      </g>
      {placed.map(({ d, x, y, b }) => {
        const age = now - (d.lastUpdate ?? 0);
        // Fresh check-in = fast flow; stale = slow; offline = still.
        const dur = b === 'offline' ? 0 : Math.min(6, 0.8 + age / 60000);
        return (
          <line
            key={`l${d.id}`}
            x1={C}
            y1={C}
            x2={x}
            y2={y}
            className={`mesh-link ${HEALTH[b].cls}`}
            style={dur ? { animationDuration: `${dur}s` } : { animation: 'none' }}
          />
        );
      })}
      <circle cx={C} cy={C} r="46" className="mesh-halo" />
      <circle cx={C} cy={C} r="36" fill="url(#meshCore)" className="mesh-core" />
      <text x={C} y={C + 2} className="mesh-core-t">MDM</text>
      <text x={C} y={C + 15} className="mesh-core-s">CORE</text>
      {placed.map(({ d, x, y, b, battery, charging }) => {
        const name = d.description || d.number;
        const batCls = battery == null ? '' : battery <= 20 ? 'fail' : battery <= 45 ? 'warn' : 'ok';
        return (
          <g
            key={d.id}
            className={`mesh-node ${HEALTH[b].cls}`}
            role="button"
            tabIndex={0}
            onClick={() => onOpen(d)}
            onKeyDown={(e) => e.key === 'Enter' && onOpen(d)}
          >
            <title>{`${name} · ${HEALTH[b].label}${battery != null ? ` · battery ${battery}%` : ''}${charging ? ' (charging)' : ''}`}</title>
            <circle cx={x} cy={y} r="27" className="mesh-node-glow" />
            {battery != null && (
              <>
                <circle cx={x} cy={y} r="21" className="mesh-bat-track" />
                <circle
                  cx={x}
                  cy={y}
                  r="21"
                  className={`mesh-bat ${batCls}`}
                  strokeDasharray={`${(battery / 100) * ARC} ${ARC}`}
                  transform={`rotate(-90 ${x} ${y})`}
                />
              </>
            )}
            <circle cx={x} cy={y} r="15" className="mesh-node-dot" />
            <text x={x} y={y + 3.5} className="mesh-node-t">{initials(name)}</text>
            {charging && (
              <path className="mesh-charge" d={`M${x + 13} ${y - 22} l-4 7 h3 l-2 6 l5 -8 h-3 z`} />
            )}
            <text x={x} y={y + 40} className="mesh-node-l">{name}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** 24h dial: the update window arc, a live "now" needle and the time until it opens/closes. */
function WindowDial({ now, auto }: { now: number; auto: boolean }) {
  const R = 52;
  const C = 64;
  const pt = (min: number, r = R) => {
    const a = (min / 1440) * 2 * Math.PI - Math.PI / 2;
    return [C + r * Math.cos(a), C + r * Math.sin(a)];
  };
  const { from, to } = UPDATE_WINDOW;
  const span = (to - from + 1440) % 1440;
  const [x1, y1] = pt(from);
  const [x2, y2] = pt(to);
  const d = new Date(now);
  const m = d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
  const [nx, ny] = pt(m, R - 10);
  const st = updateWindowState(now);
  return (
    <div className="dial">
      <svg viewBox="0 0 128 128" className="dial-svg" aria-hidden="true">
        <circle cx={C} cy={C} r={R} className="dial-track" />
        <path className={`dial-win ${auto ? '' : 'off'}`} d={`M${x1} ${y1} A${R} ${R} 0 ${span > 720 ? 1 : 0} 1 ${x2} ${y2}`} />
        {[0, 360, 720, 1080].map((mm) => {
          const [a, b] = pt(mm, R - 6);
          const [c, e] = pt(mm, R + 4);
          return <line key={mm} x1={a} y1={b} x2={c} y2={e} className="dial-tick" />;
        })}
        <line x1={C} y1={C} x2={nx} y2={ny} className="dial-needle" />
        <circle cx={C} cy={C} r="4" className="dial-hub" />
      </svg>
      <div className="dial-tx">
        <span className={`dial-state ${auto && st.open ? 'open' : ''}`}>
          {!auto ? 'AUTO-UPDATE OFF' : st.open ? 'WINDOW OPEN' : 'WINDOW CLOSED'}
        </span>
        <b>
          {Math.floor(st.minutesToChange / 60)}h {st.minutesToChange % 60}m
        </b>
        <small>{st.open ? 'until 10:30 AM' : 'until 8:30 PM'}</small>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { devices, total, configurations, loading, error } = useDevices();
  const pulse = useFleetPulse();
  const states = pulse?.states ?? new Map();
  const tele = pulse?.tele ?? new Map<string, TelemetrySnapshot>();
  const now = pulse?.now ?? Date.now();
  const [events, setEvents] = useState<{ device: DeviceView; ev: DeviceEvent }[] | null>(null);
  const [usage, setUsage] = useState<AppUsageRow[] | null>(null);

  // Fleet-wide list and per-device events + today's app time, refreshed each minute.
  const minute = Math.floor(now / 60000);
  useEffect(() => {
    if (loading) return;
    if (devices.length === 0) {
      setEvents([]);
      return;
    }
    let cancelled = false;
    const top = [...devices].sort((a, b) => (b.lastUpdate ?? 0) - (a.lastUpdate ?? 0)).slice(0, 12);
    void Promise.allSettled(top.map((d) => getEvents(d.number, Date.now() - 86400000, 500).then((evs) => ({ d, evs })))).then(
      (results) => {
        if (cancelled) return;
        const items: { device: DeviceView; ev: DeviceEvent }[] = [];
        for (const r of results) {
          if (r.status !== 'fulfilled') continue;
          for (const ev of r.value.evs ?? []) items.push({ device: r.value.d, ev });
        }
        items.sort((a, b) => b.ev.ts - a.ev.ts);
        setEvents(items);
      },
    );
    getAppUsage(dayStart(0), Date.now())
      .then((r) => !cancelled && setUsage(r ?? []))
      .catch(() => !cancelled && setUsage([]));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, devices, minute]);

  const counts = useMemo(() => {
    let online = 0,
      attention = 0,
      offline = 0;
    for (const d of devices) {
      const b = bucketOf(d, now);
      if (b === 'online') online++;
      else if (b === 'attention') attention++;
      else offline++;
    }
    return { online, attention, offline };
  }, [devices, now]);

  const access = useMemo(() => {
    let write = 0,
      adb = 0,
      reported = 0;
    for (const d of devices) {
      const t = tele.get(d.number);
      if (!t) continue;
      reported++;
      if (flag(t, 'writeSettingsGranted')) write++;
      if (flag(t, 'wirelessDebuggingOn')) adb++;
    }
    return { write, adb, reported };
  }, [devices, tele]);

  // Problems first, then alphabetical.
  const sorted = useMemo(() => {
    const rank: Record<Bucket, number> = { attention: 0, offline: 1, online: 2 };
    return [...devices].sort(
      (a, b) =>
        rank[bucketOf(a, now)] - rank[bucketOf(b, now)] ||
        (a.description || a.number).localeCompare(b.description || b.number),
    );
  }, [devices, now]);

  const meshNodes: MeshNode[] = useMemo(
    () =>
      [...devices]
        .sort((a, b) => (a.description || a.number).localeCompare(b.description || b.number))
        .map((d) => {
          const st = states.get(d.number);
          return { d, b: bucketOf(d, now), battery: st && st.battery >= 0 ? st.battery : null, charging: !!st?.charging };
        }),
    [devices, states, now],
  );

  // Hourly histogram of every event (incl. screen/app activity) over the last 24h.
  const hourly = useMemo(() => {
    const buckets = new Array(24).fill(0);
    for (const { ev } of events ?? []) {
      const h = Math.floor((now - ev.ts) / 3600000);
      if (h >= 0 && h < 24) buckets[23 - h]++;
    }
    return buckets;
  }, [events, now]);
  const hourMax = Math.max(1, ...hourly);
  const events24h = hourly.reduce((s, v) => s + v, 0);

  // Feed: notable events only, consecutive repeats (same device + type) folded into "×N".
  const feed: ActivityItem[] = useMemo(() => {
    const out: ActivityItem[] = [];
    for (const { device, ev } of events ?? []) {
      if (ACTIVITY_NOISE.has(ev.type)) continue;
      const last = out[out.length - 1];
      if (last && last.device.id === device.id && last.ev.type === ev.type) {
        last.count++;
        continue;
      }
      out.push({ key: `${device.id}-${ev.id}`, device, ev, count: 1 });
      if (out.length >= 8) break;
    }
    return out;
  }, [events]);

  const appsToday = useMemo(() => {
    const m = new Map<string, { pkg: string; label: string; seconds: number }>();
    for (const r of usage ?? []) {
      const a = m.get(r.pkg) ?? { pkg: r.pkg, label: r.label || r.pkg, seconds: 0 };
      a.seconds += r.seconds;
      m.set(r.pkg, a);
    }
    return [...m.values()].sort((a, b) => b.seconds - a.seconds);
  }, [usage]);
  const appTotal = appsToday.reduce((s, a) => s + a.seconds, 0);
  const appColors = useMemo(() => appColorMap(appsToday.map((a) => a.pkg)), [appsToday]);

  const byConfig = useMemo(() => {
    const m = new Map<string, number>();
    for (const d of devices) {
      const n = configName(d, configurations);
      m.set(n, (m.get(n) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [devices, configurations]);

  const open = (d: DeviceView) => navigate(`/devices/${encodeURIComponent(d.number)}`);
  const issues = counts.offline + counts.attention;
  const risk =
    total === 0
      ? { label: 'NONE', cls: 'ok', sub: 'no devices enrolled' }
      : issues === 0
        ? { label: 'LOW', cls: 'ok', sub: 'every device checking in' }
        : issues >= Math.ceil(total / 2)
          ? { label: 'CRITICAL', cls: 'fail', sub: `${issues} devices need action` }
          : { label: 'ELEVATED', cls: 'warn', sub: `${issues} device${issues === 1 ? '' : 's'} need action` };
  const batteries = meshNodes.map((n) => n.battery).filter((b): b is number => b != null);
  const avgBattery = batteries.length ? Math.round(batteries.reduce((s, b) => s + b, 0) / batteries.length) : null;
  const charging = meshNodes.filter((n) => n.charging).length;

  return (
    <AppShell title="Overview">
      <div className="page-head">
        <div>
          <p className="ais-eyebrow">OVERVIEW · LIVE</p>
          <h1>Fleet command</h1>
          <p className="page-sub">
            {total} tablets · {counts.online} online · avg battery {avgBattery ?? '—'}%{charging ? ` · ${charging} charging` : ''}
          </p>
        </div>
      </div>

      {error && <div className="banner banner-alert">{error}</div>}

      <div className="kpi-row">
        <div className="kpi cyan">
          <span className="kpi-k">ONLINE NOW</span>
          <span className="kpi-v">
            <Count value={counts.online} />
            <small>/{total}</small>
          </span>
          <span className="kpi-s">checked in within 15 minutes</span>
          <span className="kpi-meter">
            <i style={{ width: total ? `${(counts.online / total) * 100}%` : '0%' }} />
          </span>
        </div>
        <div className="kpi violet">
          <span className="kpi-k">ACTIVITY · 24H</span>
          <span className="kpi-v">{events === null ? '…' : <Count value={events24h} />}</span>
          <span className="kpi-s">events logged by the agents</span>
          <span className="kpi-hist" aria-label="Events per hour, last 24 hours">
            {hourly.map((v, i) => (
              <i key={i} style={{ height: `${Math.max(6, (v / hourMax) * 100)}%`, animationDelay: `${i * 20}ms` }} title={`${v} events`} />
            ))}
          </span>
        </div>
        <div className="kpi amber">
          <span className="kpi-k">ACCESS GUARDS</span>
          <span className="kpi-v">
            <Count value={access.write} />
            <small>/{access.reported || total} write</small>
          </span>
          <span className="kpi-s">
            {access.adb}/{access.reported || total} reachable over wireless ADB
          </span>
          <span className="kpi-meter">
            <i style={{ width: access.reported ? `${(access.adb / access.reported) * 100}%` : '0%' }} />
          </span>
        </div>
        <div className={`kpi risk ${risk.cls}`}>
          <span className="kpi-k">FLEET RISK</span>
          <span className="kpi-v">{risk.label}</span>
          <span className="kpi-s">{risk.sub}</span>
        </div>
      </div>

      <div className="cmd-grid">
        <section className="panel mesh-panel">
          <div className="mesh-head">
            <div>
              <p className="ais-eyebrow">DEVICE MESH</p>
              <span className="mesh-sub">Arc = battery · flow speed = last check-in</span>
            </div>
            <div className="mesh-legend">
              <span className="ok">OK</span>
              <span className="warn">WARN</span>
              <span className="fail">OFF</span>
            </div>
          </div>
          {loading && devices.length === 0 ? (
            <div className="empty">
              <span className="spin" /> Loading…
            </div>
          ) : (
            <DeviceMesh nodes={meshNodes} now={now} onOpen={open} />
          )}
          <div className="mesh-foot">
            <div>
              <span>CONFIGS</span>
              <b>{byConfig.length}</b>
            </div>
            <div className={issues ? 'warn' : 'ok'}>
              <span>ATTENTION</span>
              <b>{String(issues).padStart(2, '0')}</b>
            </div>
            <div>
              <span>CHARGING</span>
              <b>{charging}</b>
            </div>
          </div>
        </section>

        <section className="panel reg-panel">
          <div className="reg-head">
            <p className="ais-eyebrow">DEVICE REGISTRY</p>
            <span className="reg-meta">
              {total} DEVICES · <i className="ok">● LIVE</i> · CLICK A ROW FOR DEEP TELEMETRY
            </span>
          </div>
          <div className="reg-scroll">
            <table className="reg-table">
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Health</th>
                  <th>Battery</th>
                  <th>Network</th>
                  <th>Agent</th>
                  <th>Guards</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((d, i) => {
                  const b = bucketOf(d, now);
                  const st = states.get(d.number);
                  const t = tele.get(d.number);
                  const bat = st && st.battery >= 0 ? st.battery : null;
                  const w = flag(t, 'writeSettingsGranted');
                  const a = flag(t, 'wirelessDebuggingOn');
                  const fresh = now - (d.lastUpdate ?? 0) < 90_000;
                  return (
                    <tr
                      key={d.id}
                      className={`reg-row ${HEALTH[b].cls}`}
                      style={{ animationDelay: `${i * 40}ms` }}
                      tabIndex={0}
                      onClick={() => open(d)}
                      onKeyDown={(e) => e.key === 'Enter' && open(d)}
                    >
                      <td>
                        <b className="reg-name">{d.description || d.number}</b>
                        <span className="reg-sub">{configName(d, configurations)}</span>
                      </td>
                      <td>
                        <span className={`reg-health ${HEALTH[b].cls}`}>
                          <i />
                          {b === 'attention' ? statusMeta(d.statusCode).label : HEALTH[b].label}
                        </span>
                      </td>
                      <td>
                        {bat == null ? (
                          '—'
                        ) : (
                          <span className="reg-bat">
                            <span className={`reg-bat-bar ${bat <= 20 ? 'fail' : bat <= 45 ? 'warn' : 'ok'} ${st?.charging ? 'charging' : ''}`}>
                              <i style={{ width: `${bat}%` }} />
                            </span>
                            {bat}%{st?.charging ? ' ⚡' : ''}
                          </span>
                        )}
                      </td>
                      <td className="reg-dim">{b === 'offline' ? '—' : network(t)}</td>
                      <td className="reg-mono">{st?.agentVersion || d.launcherVersion || '—'}</td>
                      <td>
                        <span className={`reg-guard ${w == null ? 'na' : w ? 'ok' : 'fail'}`} title="Write access (auto-rotate)">
                          W
                        </span>
                        <span className={`reg-guard ${a == null ? 'na' : a ? 'ok' : 'fail'}`} title="Wireless ADB reachable">
                          ADB
                        </span>
                      </td>
                      <td className={`reg-dim ${fresh ? 'reg-fresh' : ''}`}>{fmtRelative(d.lastUpdate)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div className="bento-3">
        <section className="panel tile">
          <div className="tile-head">
            <p className="ais-eyebrow">APP TIME · TODAY</p>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate('/reports')}>
              Report →
            </button>
          </div>
          {usage === null ? (
            <div className="empty">
              <span className="spin" /> Loading…
            </div>
          ) : appsToday.length === 0 ? (
            <div className="empty tile-empty">No app time logged yet today.</div>
          ) : (
            <>
              <div className="tile-big">{fmtDuration(appTotal)}</div>
              <div className="app-stack">
                {appsToday.map((a) => (
                  <i key={a.pkg} style={{ flexGrow: a.seconds, background: appColors.get(a.pkg) }} title={`${a.label} · ${fmtDuration(a.seconds)}`} />
                ))}
              </div>
              {appsToday.slice(0, 4).map((a, i) => (
                <div className="app-line" key={a.pkg}>
                  <span className="atr-dot" style={{ background: appColors.get(a.pkg) }} />
                  <span className="app-name">{a.label}</span>
                  <span className="app-track">
                    <i style={{ width: `${(a.seconds / appsToday[0].seconds) * 100}%`, background: appColors.get(a.pkg), animationDelay: `${i * 80}ms` }} />
                  </span>
                  <span className="app-val">{fmtDuration(a.seconds)}</span>
                </div>
              ))}
            </>
          )}
        </section>

        <section className="panel tile">
          <div className="tile-head">
            <p className="ais-eyebrow">AGENT UPDATES</p>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate('/settings')}>
              Manage →
            </button>
          </div>
          <WindowDial now={now} auto={!!pulse?.update?.auto} />
          <div className="tile-foot">
            <span>
              Latest <b className="mono">{pulse?.update?.apk?.version ?? '—'}</b>
            </span>
            <span>
              Console <b className="mono">{pulse?.update?.current ?? '—'}</b>
            </span>
          </div>
        </section>

        <section className="panel tile">
          <div className="tile-head">
            <p className="ais-eyebrow">RECENT ACTIVITY</p>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate('/devices')}>
              All →
            </button>
          </div>
          <div className="tile-feed">
            {events === null ? (
              <div className="empty">
                <span className="spin" /> Loading…
              </div>
            ) : feed.length === 0 ? (
              <div className="empty tile-empty">No notable events in the last 24 hours.</div>
            ) : (
              feed.map((a, i) => (
                <div
                  key={a.key}
                  className={`feed-item feed-${a.ev.type}`}
                  style={{ animationDelay: `${i * 50}ms` }}
                  role="button"
                  tabIndex={0}
                  onClick={() => open(a.device)}
                  onKeyDown={(e) => e.key === 'Enter' && open(a.device)}
                >
                  <span className="feed-ic">
                    <ActivityIcon type={a.ev.type} />
                  </span>
                  <div className="feed-tx">
                    <span>
                      <b>{a.device.description || orDash(a.device.number)}</b> {EVENT_VERBS[a.ev.type] ?? a.ev.type}
                      {a.count > 1 && <em className="feed-x">×{a.count}</em>}
                    </span>
                    {a.ev.detail && <div className="feed-sub">{a.ev.detail}</div>}
                  </div>
                  <span className="feed-tm">{fmtRelative(a.ev.ts)}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </AppShell>
  );
}

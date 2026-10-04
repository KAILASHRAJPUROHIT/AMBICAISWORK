import { useEffect, useMemo, useState } from 'react';
import { getEvents, type DeviceEvent } from '../api/events';

type Device = { number: string };

const LABELS: Record<string, string> = {
  boot: 'Booted',
  appInstalled: 'App installed',
  appUninstalled: 'App uninstalled',
  commandResult: 'Command',
  connectivityChange: 'Network',
  offlineReport: 'Offline report',
  lowBattery: 'Low battery',
  enrolled: 'Enrolled',
  // Activity log (agent v0.2.71+)
  appUsage: 'App used',
  screenOn: 'Screen on',
  screenOff: 'Screen off',
  unlock: 'Unlocked',
  powerConnected: 'Charger connected',
  powerDisconnected: 'Charger disconnected',
  kioskEnter: 'Kiosk started',
  kioskExit: 'Kiosk exited',
  quickControl: 'Quick Controls',
  crash: 'Agent crash',
  logcat: 'Crash log',
  kioskCrashLoop: 'Kiosk crash loop',
  selfUninstall: 'Uninstall started',
};

/** High-volume activity-log types: fine on a device's own timeline, noise on the dashboard. */
export const ACTIVITY_NOISE = new Set(['appUsage', 'screenOn', 'screenOff', 'unlock', 'powerConnected', 'powerDisconnected', 'logcat']);

type Filter = 'all' | 'apps' | 'screen' | 'network' | 'mdm';
const FILTERS: { key: Filter; label: string; types?: string[] }[] = [
  { key: 'all', label: 'All' },
  { key: 'apps', label: 'App usage', types: ['appUsage', 'appInstalled', 'appUninstalled'] },
  { key: 'screen', label: 'Screen & power', types: ['screenOn', 'screenOff', 'unlock', 'powerConnected', 'powerDisconnected', 'lowBattery', 'boot'] },
  { key: 'network', label: 'Network', types: ['connectivityChange', 'offlineReport'] },
  { key: 'mdm', label: 'MDM & kiosk', types: ['commandResult', 'kioskEnter', 'kioskExit', 'quickControl', 'enrolled', 'crash', 'logcat', 'kioskCrashLoop', 'selfUninstall'] },
];

const QUICK_CONTROL_NAMES: Record<string, string> = {
  autoRotation: 'Auto-rotate',
  autoBrightness: 'Adaptive brightness',
  wifiRadio: 'Wi-Fi',
  brightness: 'Brightness',
};

function fmtDuration(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}

/** Human-readable detail for the activity-log formats; anything else is shown as sent. */
export function formatEventDetail(type: string, detail?: string | null): string | null {
  if (!detail) return null;
  switch (type) {
    case 'appUsage': {
      // "com.pkg|Label|seconds"
      const [pkg, label, secs] = detail.split('|');
      const n = Number(secs);
      return `${label || pkg}${Number.isFinite(n) ? ` · ${fmtDuration(n)}` : ''}`;
    }
    case 'connectivityChange':
      if (detail.startsWith('wifi:')) return `Wi-Fi connected: ${detail.slice(5)}`;
      if (detail === 'offline') return 'Disconnected';
      if (detail === 'cellular') return 'Mobile data';
      return detail;
    case 'quickControl': {
      // "autoRotation=on" | "brightness=40%"
      const [k, v] = detail.split('=');
      return `${QUICK_CONTROL_NAMES[k] ?? k} ${v ?? ''}`.trim();
    }
    case 'kioskEnter':
      return null; // detail is the agent's own package; says nothing useful
    default:
      return detail;
  }
}

export function EventTimeline({ device }: { device: Device }) {
  const [events, setEvents] = useState<DeviceEvent[]>([]);
  const [filter, setFilter] = useState<Filter>('all');
  useEffect(() => {
    let on = true;
    let t: ReturnType<typeof setTimeout>;
    // Self-scheduling poll — the next tick is armed only after the current one finishes.
    const load = async () => {
      await getEvents(device.number, 0, 500)
        .then((evs) => { if (on) setEvents(evs); })
        .catch(() => undefined);
      if (!on) return;
      t = setTimeout(() => void load(), 5000);
    };
    void load();
    return () => { on = false; clearTimeout(t); };
  }, [device.number]);

  const shown = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter);
    return f?.types ? events.filter((e) => f.types!.includes(e.type)) : events;
  }, [events, filter]);

  return (
    <div className="panel">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <h2 className="panel-title">Events</h2>
        <select id="event-filter" value={filter} onChange={(e) => setFilter(e.target.value as Filter)} aria-label="Filter events">
          {FILTERS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
        </select>
      </div>
      {shown.length === 0 ? (
        <p className="muted">No events yet.</p>
      ) : (
        <ul className="timeline">
          {shown.map((e) => {
            const detail = formatEventDetail(e.type, e.detail);
            return (
              <li key={e.id} className="timeline-item">
                <span className="t-status">{new Date(e.ts).toLocaleString()}</span>
                <span className="t-type">{LABELS[e.type] ?? e.type}</span>
                {detail && (e.type === 'logcat' || e.type === 'crash' ? (
                  <details className="t-detail"><summary>{detail.length} chars</summary><pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{detail}</pre></details>
                ) : (
                  <span className="t-detail">{detail}</span>
                ))}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

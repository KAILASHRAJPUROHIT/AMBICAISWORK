import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { searchDevices, type DeviceView } from '../api/devices';
import { getDeviceState, type DeviceState } from '../api/commands';
import { getTelemetry, type TelemetrySnapshot } from '../api/telemetry';
import { getUpdateStatus, type UpdateStatus } from '../api/updates';
import { isOnline } from '../ui/status';

/**
 * Live fleet snapshot shared by the top command bar (search, alerts, status strip) and any page
 * that wants it. Lives above the routes, so switching pages doesn't refetch. Cheap: one device
 * list per minute, per-device state/telemetry every two minutes (capped), update status every five.
 */
export interface FleetPulse {
  devices: DeviceView[];
  states: Map<string, DeviceState>;
  tele: Map<string, TelemetrySnapshot>;
  update: UpdateStatus | null;
  /** Epoch ms of the last completed device-list refresh (drives the refresh progress line). */
  refreshedAt: number;
  now: number;
  refresh: () => void;
}

export const DEVICE_POLL_MS = 60_000;
const DETAIL_POLL_MS = 120_000;
const UPDATE_POLL_MS = 300_000;
const DETAIL_CAP = 30;

const Ctx = createContext<FleetPulse | null>(null);

export function useFleetPulse(): FleetPulse | null {
  return useContext(Ctx);
}

export function FleetPulseLayout() {
  return (
    <FleetPulseProvider>
      <Outlet />
    </FleetPulseProvider>
  );
}

function FleetPulseProvider({ children }: { children: ReactNode }) {
  const [devices, setDevices] = useState<DeviceView[]>([]);
  const [states, setStates] = useState<Map<string, DeviceState>>(new Map());
  const [tele, setTele] = useState<Map<string, TelemetrySnapshot>>(new Map());
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [refreshedAt, setRefreshedAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const devRef = useRef<DeviceView[]>([]);

  const loadDevices = useCallback(async () => {
    try {
      const res = await searchDevices({ value: '', pageSize: 1000 });
      const list = res.devices?.items ?? [];
      devRef.current = list;
      setDevices(list);
      setRefreshedAt(Date.now());
    } catch {
      /* session expiry etc. is surfaced by the pages themselves */
    }
  }, []);

  const loadDetails = useCallback(async () => {
    const list = [...devRef.current].sort((a, b) => (b.lastUpdate ?? 0) - (a.lastUpdate ?? 0)).slice(0, DETAIL_CAP);
    const st = new Map<string, DeviceState>();
    const te = new Map<string, TelemetrySnapshot>();
    await Promise.allSettled(
      list.flatMap((d) => [
        getDeviceState(d.number).then((s) => s && st.set(d.number, s)),
        getTelemetry(d.number).then((t) => t && te.set(d.number, t)),
      ]),
    );
    setStates(st);
    setTele(te);
  }, []);

  const loadUpdate = useCallback(async () => {
    try {
      setUpdate(await getUpdateStatus());
    } catch {
      /* optional */
    }
  }, []);

  useEffect(() => {
    void loadDevices().then(loadDetails);
    void loadUpdate();
    const a = setInterval(() => void loadDevices(), DEVICE_POLL_MS);
    const b = setInterval(() => void loadDetails(), DETAIL_POLL_MS);
    const c = setInterval(() => void loadUpdate(), UPDATE_POLL_MS);
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => [a, b, c, t].forEach(clearInterval);
  }, [loadDevices, loadDetails, loadUpdate]);

  const refresh = useCallback(() => {
    void loadDevices().then(loadDetails);
    void loadUpdate();
  }, [loadDevices, loadDetails, loadUpdate]);

  const value = useMemo(
    () => ({ devices, states, tele, update, refreshedAt, now, refresh }),
    [devices, states, tele, update, refreshedAt, now, refresh],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export type AlertTone = 'fail' | 'warn' | 'info';
export interface FleetAlert {
  key: string;
  tone: AlertTone;
  device: DeviceView;
  title: string;
  detail: string;
}

function dyn(t: TelemetrySnapshot | undefined, k: string): boolean | null {
  const v = t?.dynamic?.[k];
  return typeof v === 'boolean' ? v : null;
}

/** Things worth a glance, most severe first, derived only from live data. */
export function fleetAlerts(p: FleetPulse): FleetAlert[] {
  const out: FleetAlert[] = [];
  const latest = p.update?.apk?.version;
  for (const d of p.devices) {
    const name = d.description || d.number;
    const st = p.states.get(d.number);
    const t = p.tele.get(d.number);
    if (!isOnline(d.lastUpdate, p.now)) {
      out.push({ key: `off-${d.id}`, tone: 'fail', device: d, title: `${name} is offline`, detail: 'No check-in for over 15 minutes' });
      continue;
    }
    if (st && st.battery >= 0 && st.battery <= 15 && !st.charging) {
      out.push({ key: `bat-${d.id}`, tone: 'fail', device: d, title: `${name} battery ${st.battery}%`, detail: 'Not charging' });
    }
    if (dyn(t, 'writeSettingsGranted') === false) {
      out.push({ key: `w-${d.id}`, tone: 'warn', device: d, title: `${name}: write access off`, detail: 'Auto-rotate hidden until the shop PC re-grants it' });
    }
    if (dyn(t, 'wirelessDebuggingOn') === false) {
      out.push({ key: `adb-${d.id}`, tone: 'warn', device: d, title: `${name}: wireless ADB off`, detail: 'The shop PC cannot reach it' });
    }
    const v = st?.agentVersion;
    if (latest && v && v !== latest) {
      out.push({ key: `v-${d.id}`, tone: 'info', device: d, title: `${name} on agent ${v}`, detail: `Latest is ${latest}` });
    }
  }
  const rank: Record<AlertTone, number> = { fail: 0, warn: 1, info: 2 };
  return out.sort((a, b) => rank[a.tone] - rank[b.tone]);
}

/** Agent auto-update window (server default 20:30–10:30 local). */
export const UPDATE_WINDOW = { from: 20 * 60 + 30, to: 10 * 60 + 30 };

export function updateWindowState(now: number): { open: boolean; minutesToChange: number } {
  const d = new Date(now);
  const m = d.getHours() * 60 + d.getMinutes();
  const { from, to } = UPDATE_WINDOW;
  const open = m >= from || m < to;
  const target = open ? to : from;
  const diff = (target - m + 1440) % 1440;
  return { open, minutesToChange: diff };
}

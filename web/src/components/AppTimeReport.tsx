import { useEffect, useMemo, useState } from 'react';
import { getAppUsage, fmtDuration, dayStart, type AppUsageRow } from '../api/reports';
import type { DeviceView } from '../api/devices';
import { appColor, appColorMap } from '../ui/palette';

type Range = 'today' | 'yesterday' | '7d' | '30d';

const RANGES: { id: Range; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' },
];

function rangeBounds(r: Range): [number, number] {
  const now = Date.now();
  switch (r) {
    case 'today':
      return [dayStart(0), now];
    case 'yesterday':
      return [dayStart(1), dayStart(0)];
    case '7d':
      return [dayStart(6), now];
    case '30d':
      return [dayStart(29), now];
  }
}

/** Every local day in [from, to) as "yyyy-MM-dd", oldest first. */
function daysBetween(from: number, to: number): string[] {
  const out: string[] = [];
  const d = new Date(from);
  while (d.getTime() < to) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
    d.setDate(d.getDate() + 1);
  }
  return out;
}

interface AppTotal {
  pkg: string;
  label: string;
  seconds: number;
  sessions: number;
}

function totalsByApp(rows: AppUsageRow[]): AppTotal[] {
  const m = new Map<string, AppTotal>();
  for (const r of rows) {
    const t = m.get(r.pkg) ?? { pkg: r.pkg, label: r.label || r.pkg, seconds: 0, sessions: 0 };
    t.seconds += r.seconds;
    t.sessions += r.sessions;
    m.set(r.pkg, t);
  }
  return [...m.values()].sort((a, b) => b.seconds - a.seconds);
}

function csvEscape(v: string | number): string {
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Per-device app time: how long each app was in the foreground, from the agents' low-power
 * appUsage log. Used by the Reports page (whole fleet, device picker) and the device page
 * (one device, {@code fixedDevice}).
 */
export function AppTimeReport({ devices, fixedDevice }: { devices: DeviceView[]; fixedDevice?: string }) {
  const [range, setRange] = useState<Range>('today');
  const [device, setDevice] = useState<string>(fixedDevice ?? 'all');
  const [rows, setRows] = useState<AppUsageRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [from, to] = useMemo(() => rangeBounds(range), [range]);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    getAppUsage(from, to, device === 'all' ? undefined : device)
      .then((r) => !cancelled && setRows(r ?? []))
      .catch(() => !cancelled && setError('Could not load app time. The server may still be updating — try again in a minute.'));
    return () => {
      cancelled = true;
    };
  }, [from, to, device]);

  const name = (num: string) => {
    const d = devices.find((x) => x.number === num);
    return d?.description || num;
  };

  const apps = useMemo(() => totalsByApp(rows ?? []), [rows]);
  const colors = useMemo(() => appColorMap(apps.map((a) => a.pkg)), [apps]);
  const col = (pkg: string) => colors.get(pkg) ?? appColor(pkg);
  const total = apps.reduce((s, a) => s + a.seconds, 0);
  const sessions = apps.reduce((s, a) => s + a.sessions, 0);

  const perDevice = useMemo(() => {
    const m = new Map<string, AppUsageRow[]>();
    for (const r of rows ?? []) m.set(r.deviceNumber, [...(m.get(r.deviceNumber) ?? []), r]);
    return [...m.entries()]
      .map(([num, rs]) => ({ num, apps: totalsByApp(rs), total: rs.reduce((s, r) => s + r.seconds, 0) }))
      .sort((a, b) => b.total - a.total);
  }, [rows]);

  const days = useMemo(() => daysBetween(from, to), [from, to]);
  const topPkgs = apps.slice(0, 5).map((a) => a.pkg);
  const daily = useMemo(() => {
    return days.map((day) => {
      const rs = (rows ?? []).filter((r) => r.day === day);
      const seg = topPkgs.map((pkg) => rs.filter((r) => r.pkg === pkg).reduce((s, r) => s + r.seconds, 0));
      const other = rs.filter((r) => !topPkgs.includes(r.pkg)).reduce((s, r) => s + r.seconds, 0);
      return { day, seg, other, total: seg.reduce((s, v) => s + v, 0) + other };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, rows, apps]);
  const dayMax = Math.max(1, ...daily.map((d) => d.total));

  const exportCsv = () => {
    const lines = [['Device', 'Day', 'App', 'Package', 'Seconds', 'Minutes', 'Sessions'].join(',')];
    for (const r of rows ?? []) {
      lines.push(
        [name(r.deviceNumber), r.day, r.label || r.pkg, r.pkg, r.seconds, (r.seconds / 60).toFixed(1), r.sessions]
          .map(csvEscape)
          .join(','),
      );
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `app-time-${fixedDevice ? name(fixedDevice) : device === 'all' ? 'all-devices' : name(device)}-${range}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  return (
    <div className="atr">
      <div className="atr-bar">
        <div className="seg" role="tablist" aria-label="Period">
          {RANGES.map((r) => (
            <button key={r.id} className={range === r.id ? 'on' : ''} onClick={() => setRange(r.id)}>
              {r.label}
            </button>
          ))}
        </div>
        {!fixedDevice && (
          <select className="sel" id="atr-device" value={device} onChange={(e) => setDevice(e.target.value)} aria-label="Device">
            <option value="all">All devices</option>
            {devices.map((d) => (
              <option key={d.number} value={d.number}>
                {d.description || d.number}
              </option>
            ))}
          </select>
        )}
        <button className="btn btn-sm" onClick={exportCsv} disabled={!rows || rows.length === 0}>
          Export CSV
        </button>
      </div>

      {error && <div className="banner banner-alert">{error}</div>}

      {rows === null && !error ? (
        <div className="empty">
          <span className="spin" /> Loading app time…
        </div>
      ) : rows && rows.length === 0 ? (
        <div className="empty atr-empty">
          <span className="label">No app time recorded</span>
          Nothing logged for this period yet. Tablets report app time on each check-in once they run agent
          0.2.71 or newer with Usage access allowed (the shop PC grants it automatically after updates).
        </div>
      ) : rows ? (
        <>
          <div className="atr-kpis">
            <div className="atr-kpi">
              <span>SCREEN TIME</span>
              <b>{fmtDuration(total)}</b>
            </div>
            <div className="atr-kpi">
              <span>TOP APP</span>
              <b style={{ color: apps[0] ? col(apps[0].pkg) : undefined }}>{apps[0]?.label ?? '—'}</b>
            </div>
            <div className="atr-kpi">
              <span>{fixedDevice ? 'APPS USED' : 'MOST USED DEVICE'}</span>
              <b>{fixedDevice ? apps.length : perDevice[0] ? name(perDevice[0].num) : '—'}</b>
            </div>
            <div className="atr-kpi">
              <span>SESSIONS</span>
              <b>{sessions}</b>
            </div>
          </div>

          <div className={`atr-grid ${days.length > 1 || !fixedDevice ? '' : 'one'}`}>
            <section className="atr-card">
              <h3 className="atr-h">By app</h3>
              {apps.slice(0, 10).map((a, i) => (
                <div className="atr-app" key={a.pkg} title={a.pkg}>
                  <span className="atr-dot" style={{ background: col(a.pkg) }} />
                  <span className="atr-name">{a.label}</span>
                  <span className="atr-track">
                    <i
                      style={{
                        width: `${(a.seconds / Math.max(apps[0].seconds, 1)) * 100}%`,
                        background: col(a.pkg),
                        animationDelay: `${i * 60}ms`,
                      }}
                    />
                  </span>
                  <span className="atr-val">{fmtDuration(a.seconds)}</span>
                  <span className="atr-pct">{total ? Math.round((a.seconds / total) * 100) : 0}%</span>
                </div>
              ))}
            </section>

            {days.length > 1 ? (
              <section className="atr-card">
                <h3 className="atr-h">Daily trend</h3>
                <div className="atr-days" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
                  {daily.map((d, i) => (
                    <div className="atr-day" key={d.day} title={`${d.day} · ${fmtDuration(d.total)}`}>
                      <div className="atr-col" style={{ height: `${(d.total / dayMax) * 100}%`, animationDelay: `${i * 25}ms` }}>
                        {d.seg.map((v, j) =>
                          v > 0 ? <i key={j} style={{ flexGrow: v, background: col(topPkgs[j]) }} /> : null,
                        )}
                        {d.other > 0 && <i style={{ flexGrow: d.other, background: 'var(--faint)' }} />}
                      </div>
                      {(days.length <= 7 || i % 5 === 0 || i === days.length - 1) && (
                        <span className="atr-dl">{d.day.slice(8)}</span>
                      )}
                    </div>
                  ))}
                </div>
                <div className="atr-legend">
                  {apps.slice(0, 5).map((a) => (
                    <span key={a.pkg}>
                      <i style={{ background: col(a.pkg) }} />
                      {a.label}
                    </span>
                  ))}
                  {apps.length > 5 && (
                    <span>
                      <i style={{ background: 'var(--faint)' }} />
                      Other
                    </span>
                  )}
                </div>
              </section>
            ) : (
              !fixedDevice && (
                <section className="atr-card">
                  <h3 className="atr-h">By device</h3>
                  {perDevice.map((d) => (
                    <DeviceStack col={col} key={d.num} label={name(d.num)} apps={d.apps} total={d.total} max={perDevice[0].total} />
                  ))}
                </section>
              )
            )}
          </div>

          {!fixedDevice && days.length > 1 && (
            <section className="atr-card">
              <h3 className="atr-h">By device</h3>
              {perDevice.map((d) => (
                <DeviceStack col={col} key={d.num} label={name(d.num)} apps={d.apps} total={d.total} max={perDevice[0].total} />
              ))}
            </section>
          )}

          <section className="atr-card">
            <h3 className="atr-h">Detail</h3>
            <div className="atr-scroll">
              <table className="table atr-table">
                <thead>
                  <tr>
                    {!fixedDevice && <th>Device</th>}
                    <th>App</th>
                    <th className="num">Time</th>
                    <th className="num">Sessions</th>
                    <th className="num">Avg session</th>
                  </tr>
                </thead>
                <tbody>
                  {(fixedDevice ? [{ num: fixedDevice, apps }] : perDevice).flatMap((d) =>
                    d.apps.map((a) => (
                      <tr key={`${d.num}-${a.pkg}`}>
                        {!fixedDevice && <td>{name(d.num)}</td>}
                        <td>
                          <span className="atr-dot" style={{ background: col(a.pkg) }} /> {a.label}
                          <span className="atr-pkg">{a.pkg}</span>
                        </td>
                        <td className="num">{fmtDuration(a.seconds)}</td>
                        <td className="num">{a.sessions}</td>
                        <td className="num">{fmtDuration(a.seconds / Math.max(a.sessions, 1))}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

function DeviceStack({ label, apps, total, max, col }: { label: string; apps: AppTotal[]; total: number; max: number; col: (pkg: string) => string }) {
  return (
    <div className="atr-dev">
      <div className="atr-dev-h">
        <b>{label}</b>
        <span>{fmtDuration(total)}</span>
      </div>
      <div className="atr-stack" style={{ width: `${(total / Math.max(max, 1)) * 100}%` }}>
        {apps.map((a) => (
          <i key={a.pkg} title={`${a.label} · ${fmtDuration(a.seconds)}`} style={{ flexGrow: a.seconds, background: col(a.pkg) }} />
        ))}
      </div>
    </div>
  );
}

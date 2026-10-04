import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useTheme } from './theme';
import { UpdateBanner } from '../components/UpdateBanner';
import { ReloadPrompt } from '../components/ReloadPrompt';
import { useFleetPulse, fleetAlerts, updateWindowState, DEVICE_POLL_MS } from '../data/FleetPulse';
import { isOnline } from './status';
import { fmtRelative } from './format';
import {
  IconDashboard,
  IconDevices,
  IconConfig,
  IconApps,
  IconEnroll,
  IconSettings,
  IconSignOut,
  IconMenu,
  IconSun,
  IconMoon,
  IconReport,
  IconIndoor,
  IconSearch,
  IconBell,
  IconPlus,
  IconBolt,
} from './icons';

interface NavEntry {
  to: string;
  label: string;
  Icon: (p: { className?: string }) => ReactNode;
}

const NAV: NavEntry[] = [
  { to: '/dashboard', label: 'Overview', Icon: IconDashboard },
  { to: '/devices', label: 'Devices', Icon: IconDevices },
  { to: '/reports', label: 'Reports', Icon: IconReport },
  { to: '/indoor', label: 'Indoor map', Icon: IconIndoor },
  { to: '/apps', label: 'Apps', Icon: IconApps },
  { to: '/configs', label: 'Configurations', Icon: IconConfig },
  { to: '/enroll', label: 'Enroll', Icon: IconEnroll },
  { to: '/settings', label: 'Settings', Icon: IconSettings },
];

type Menu = 'alerts' | 'quick' | 'user' | null;

function fmtMinutes(m: number): string {
  const h = Math.floor(m / 60);
  return h ? `${h}h ${m % 60}m` : `${m}m`;
}

export function AppShell({
  title,
  children,
}: {
  /** Page label, shown only in the mobile top bar. */
  title?: string;
  children: ReactNode;
}) {
  const { user, signOut } = useAuth();
  const { theme, toggleTheme, density, setDensity } = useTheme();
  const navigate = useNavigate();
  const pulse = useFleetPulse();
  const [navOpen, setNavOpen] = useState(false);
  const [menu, setMenu] = useState<Menu>(null);
  const [q, setQ] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const toolsRef = useRef<HTMLDivElement>(null);

  // Ctrl/Cmd+K focuses search; Escape closes any open menu.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
        setSearchOpen(true);
      } else if (e.key === 'Escape') {
        setMenu(null);
        setSearchOpen(false);
      }
    };
    const onClick = (e: MouseEvent) => {
      if (toolsRef.current && !toolsRef.current.contains(e.target as Node)) {
        setMenu(null);
        setSearchOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onClick);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onClick);
    };
  }, []);

  const devices = pulse?.devices ?? [];
  const now = pulse?.now ?? Date.now();
  const online = devices.filter((d) => isOnline(d.lastUpdate, now)).length;
  const alerts = useMemo(() => (pulse ? fleetAlerts(pulse) : []), [pulse]);
  const serious = alerts.filter((a) => a.tone !== 'info').length;
  const lastSeen = devices.reduce((m, d) => Math.max(m, d.lastUpdate ?? 0), 0);
  const latestAgent = pulse?.update?.apk?.version;
  const onLatest = latestAgent ? [...(pulse?.states.values() ?? [])].filter((s) => s.agentVersion === latestAgent).length : 0;
  const ssids = new Map<string, number>();
  for (const t of pulse?.tele.values() ?? []) {
    const s = t.dynamic?.wifiSsid;
    if (typeof s === 'string' && s) ssids.set(s, (ssids.get(s) ?? 0) + 1);
  }
  const topSsid = [...ssids.entries()].sort((a, b) => b[1] - a[1])[0];
  const win = updateWindowState(now);
  const refreshPct = pulse?.refreshedAt ? Math.min(100, ((now - pulse.refreshedAt) / DEVICE_POLL_MS) * 100) : 0;

  const hits = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return { devs: devices.slice(0, 6), pages: [] as NavEntry[] };
    return {
      devs: devices
        .filter((d) => [d.description, d.number, d.serial, d.imei].some((v) => v?.toLowerCase().includes(s)))
        .slice(0, 8),
      pages: NAV.filter((n) => n.label.toLowerCase().includes(s)),
    };
  }, [q, devices]);

  const go = (to: string) => {
    setMenu(null);
    setSearchOpen(false);
    setQ('');
    setNavOpen(false);
    navigate(to);
  };
  const toggle = (m: Menu) => setMenu((cur) => (cur === m ? null : m));
  const who = user?.login || user?.name || 'admin';

  return (
    <div className="shell">
      <header className="cmdbar">
        <div className="cmdbar-row">
          <button className="cmd-icon cmd-menu" onClick={() => setNavOpen((v) => !v)} aria-label="Toggle navigation">
            <IconMenu />
          </button>
          <NavLink to="/dashboard" className="cmd-brand" aria-label="AMBIC Digital MDM home">
            <span className="cmd-mark">MDM</span>
            <span className="cmd-brand-tx">
              <small>AMBIC · CONTROL PLANE</small>
              <b>Device Fleet Command</b>
            </span>
          </NavLink>
          <span className="cmd-mobile-title">{title}</span>

          <div className="cmd-tools" ref={toolsRef}>
            <div className={`cmd-search ${searchOpen ? 'open' : ''}`}>
              <IconSearch className="ico" />
              <input
                ref={searchRef}
                id="cmd-search"
                type="search"
                placeholder="Search devices, pages…"
                value={q}
                onFocus={() => {
                  setSearchOpen(true);
                  setMenu(null);
                }}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    if (hits.devs[0]) go(`/devices/${encodeURIComponent(hits.devs[0].number)}`);
                    else if (hits.pages[0]) go(hits.pages[0].to);
                  }
                }}
                aria-label="Search devices and pages"
              />
              <kbd>Ctrl K</kbd>
              {searchOpen && (hits.devs.length > 0 || hits.pages.length > 0) && (
                <div className="cmd-pop cmd-search-pop">
                  {hits.devs.length > 0 && <div className="cmd-pop-h">DEVICES</div>}
                  {hits.devs.map((d) => {
                    const on = isOnline(d.lastUpdate, now);
                    const st = pulse?.states.get(d.number);
                    return (
                      <button key={d.id} className="cmd-pop-item" onClick={() => go(`/devices/${encodeURIComponent(d.number)}`)}>
                        <span className={`cmd-led ${on ? 'ok' : 'fail'}`} />
                        <span className="cmd-pop-main">
                          <b>{d.description || d.number}</b>
                          <small>
                            {on ? 'Online' : `Seen ${fmtRelative(d.lastUpdate)}`}
                            {st && st.battery >= 0 ? ` · ${st.battery}%` : ''}
                            {st?.agentVersion ? ` · ${st.agentVersion}` : ''}
                          </small>
                        </span>
                      </button>
                    );
                  })}
                  {hits.pages.length > 0 && <div className="cmd-pop-h">PAGES</div>}
                  {hits.pages.map((p) => (
                    <button key={p.to} className="cmd-pop-item" onClick={() => go(p.to)}>
                      <p.Icon className="ico" />
                      <span className="cmd-pop-main">
                        <b>{p.label}</b>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button className="cmd-live" onClick={() => go('/devices')} title="Devices checked in within 15 minutes">
              <i className={online === devices.length && devices.length ? 'ok' : online ? 'warn' : 'fail'} />
              <b>
                {online}/{devices.length}
              </b>
              <span>online</span>
            </button>

            <div className="cmd-anchor">
              <button className={`cmd-icon ${menu === 'alerts' ? 'on' : ''}`} onClick={() => toggle('alerts')} aria-label={`Alerts (${alerts.length})`}>
                <IconBell />
                {alerts.length > 0 && <span className={`cmd-badge ${serious ? 'hot' : ''}`}>{alerts.length}</span>}
              </button>
              {menu === 'alerts' && (
                <div className="cmd-pop cmd-pop-right cmd-alerts">
                  <div className="cmd-pop-h">ALERTS · LIVE</div>
                  {alerts.length === 0 ? (
                    <div className="cmd-pop-empty">All clear — every device online with access guards on.</div>
                  ) : (
                    alerts.slice(0, 12).map((a) => (
                      <button key={a.key} className={`cmd-pop-item al-${a.tone}`} onClick={() => go(`/devices/${encodeURIComponent(a.device.number)}`)}>
                        <span className="cmd-led" />
                        <span className="cmd-pop-main">
                          <b>{a.title}</b>
                          <small>{a.detail}</small>
                        </span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>

            <div className="cmd-anchor">
              <button className={`cmd-icon cmd-plus ${menu === 'quick' ? 'on' : ''}`} onClick={() => toggle('quick')} aria-label="Quick actions">
                <IconPlus />
              </button>
              {menu === 'quick' && (
                <div className="cmd-pop cmd-pop-right">
                  <div className="cmd-pop-h">QUICK ACTIONS</div>
                  <button className="cmd-pop-item" onClick={() => go('/enroll')}>
                    <IconEnroll className="ico" />
                    <span className="cmd-pop-main"><b>Enroll a device</b><small>QR, token or Lite</small></span>
                  </button>
                  <button className="cmd-pop-item" onClick={() => go('/reports')}>
                    <IconReport className="ico" />
                    <span className="cmd-pop-main"><b>App time report</b><small>Per device, per app</small></span>
                  </button>
                  <button className="cmd-pop-item" onClick={() => go('/apps')}>
                    <IconApps className="ico" />
                    <span className="cmd-pop-main"><b>Deploy an app</b><small>Library, APK, F-Droid</small></span>
                  </button>
                  <button className="cmd-pop-item" onClick={() => go('/settings')}>
                    <IconBolt className="ico" />
                    <span className="cmd-pop-main"><b>Updates &amp; rollout</b><small>{pulse?.update?.auto ? 'Automatic updates on' : 'Automatic updates off'}</small></span>
                  </button>
                  <button
                    className="cmd-pop-item"
                    onClick={() => {
                      pulse?.refresh();
                      setMenu(null);
                    }}
                  >
                    <IconDashboard className="ico" />
                    <span className="cmd-pop-main"><b>Refresh live data</b><small>Last refresh {pulse?.refreshedAt ? fmtRelative(pulse.refreshedAt) : '—'}</small></span>
                  </button>
                </div>
              )}
            </div>

            <button className="cmd-icon" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} title={theme === 'dark' ? 'Light mode' : 'Dark mode'}>
              {theme === 'dark' ? <IconSun /> : <IconMoon />}
            </button>

            <div className="cmd-anchor">
              <button className={`cmd-avatar ${menu === 'user' ? 'on' : ''}`} onClick={() => toggle('user')} aria-label="Account menu">
                {who.slice(0, 1).toUpperCase()}
              </button>
              {menu === 'user' && (
                <div className="cmd-pop cmd-pop-right">
                  <div className="cmd-pop-who">
                    <b>{who}</b>
                    <small>Administrator</small>
                  </div>
                  <div className="cmd-pop-row">
                    <span>Density</span>
                    <div className="seg">
                      <button className={density === 'comfortable' ? 'on' : ''} onClick={() => setDensity('comfortable')}>Comfortable</button>
                      <button className={density === 'compact' ? 'on' : ''} onClick={() => setDensity('compact')}>Compact</button>
                    </div>
                  </div>
                  <button className="cmd-pop-item" onClick={() => go('/settings')}>
                    <IconSettings className="ico" />
                    <span className="cmd-pop-main"><b>Settings</b></span>
                  </button>
                  <button className="cmd-pop-item" onClick={() => void signOut()}>
                    <IconSignOut className="ico" />
                    <span className="cmd-pop-main"><b>Sign out</b></span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        <nav className={`cmd-tabs ${navOpen ? 'open' : ''}`}>
          {NAV.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `cmd-tab ${isActive ? 'active' : ''}`} onClick={() => setNavOpen(false)}>
              <Icon className="ico" />
              <span>{label}</span>
            </NavLink>
          ))}
          <div className="cmd-strip" aria-label="Fleet status">
            <span title="Most recent device check-in">
              <i className="ok" />
              Last check-in {lastSeen ? fmtRelative(lastSeen) : '—'}
            </span>
            {latestAgent && (
              <span title="Devices on the latest agent release">
                Agent {latestAgent} · {onLatest}/{devices.length}
              </span>
            )}
            {topSsid && (
              <span title="Most common Wi-Fi network">
                Wi-Fi {topSsid[0]} · {topSsid[1]}/{devices.length}
              </span>
            )}
            {pulse?.update && (
              <span className={pulse.update.auto && win.open ? 'hot' : ''} title="Automatic agent update window (8:30 PM – 10:30 AM)">
                {!pulse.update.auto
                  ? 'Auto-update off'
                  : win.open
                    ? `Update window open · closes in ${fmtMinutes(win.minutesToChange)}`
                    : `Update window opens in ${fmtMinutes(win.minutesToChange)}`}
              </span>
            )}
          </div>
        </nav>
        <span className="cmd-refresh" style={{ width: `${refreshPct}%` }} aria-hidden="true" />
      </header>

      <main className="content route-enter">
        <ReloadPrompt />
        <UpdateBanner />
        {children}
      </main>
    </div>
  );
}

import { useState, type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useTheme } from './theme';
import { UpdateBanner } from '../components/UpdateBanner';
import { ReloadPrompt } from '../components/ReloadPrompt';
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
} from './icons';

interface NavEntry {
  to: string;
  label: string;
  Icon: (p: { className?: string }) => ReactNode;
}

const NAV: NavEntry[] = [
  { to: '/dashboard', label: 'Overview', Icon: IconDashboard },
  { to: '/devices', label: 'Devices', Icon: IconDevices },
  { to: '/configs', label: 'Configurations', Icon: IconConfig },
  { to: '/apps', label: 'Apps', Icon: IconApps },
  { to: '/enroll', label: 'Enroll', Icon: IconEnroll },
  { to: '/settings', label: 'Settings', Icon: IconSettings },
];

export function AppShell({
  title,
  children,
}: {
  /** Page label, shown only in the mobile top bar. */
  title?: string;
  children: ReactNode;
}) {
  const { user, signOut } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <div className="shell">
      <div
        className={`scrim ${open ? 'show' : ''}`}
        onClick={close}
        aria-hidden="true"
      />
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <p className="ais-eyebrow">AIS · DEVICE OPERATIONS</p>
          <span className="wordmark" aria-label="AIS Device Fleet powered by AMBIC Digital"><span className="bullet" aria-hidden="true" /><span><span className="mdm">AIS</span><span className="esh"> Device Fleet</span></span></span>
          <small className="ais-brand-note">secure fleet command</small>
        </div>
        <nav className="nav">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              onClick={close}
            >
              <Icon className="ico" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="sidebar-user">
            <span className="who">
              {user?.login || user?.name || 'admin@localhost'}
            </span>
          </div>
          <button
            className="btn btn-ghost"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? <IconSun className="ico" /> : <IconMoon className="ico" />}
            <span style={{ marginLeft: 8 }}>{theme === 'dark' ? 'Light' : 'Dark'}</span>
          </button>
          <button className="btn btn-ghost" onClick={() => void signOut()}>
            <IconSignOut className="ico" />
            <span style={{ marginLeft: 8 }}>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="ais-mdm-header"><div><span className="ais-eyebrow">OBSIDIAN CONTROL PLANE</span><strong>AMBIC DIGITAL MDM</strong></div><span className="ais-connection"><i /> EMBEDDED SECURE CONSOLE</span></header>
        <div className="rail-mobilebar">
          <button
            className="btn btn-ghost menu-btn"
            onClick={() => setOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            <IconMenu />
          </button>
          <span style={{ fontWeight: 600 }}>{title ?? 'AIS Device Fleet'}</span>
        </div>
        <main className="content route-enter"><ReloadPrompt /><UpdateBanner />{children}</main>
      </div>
    </div>
  );
}

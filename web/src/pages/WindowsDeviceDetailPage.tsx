import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AppShell } from '../ui/AppShell';
import { useToast } from '../ui/toast';
import { fmtDateTime, fmtRelative, orDash } from '../ui/format';
import {
  fmtMemory,
  getWindowsPc,
  sendWindowsCommand,
  windowsName,
  windowsState,
  type WindowsAction,
  type WindowsPc,
} from '../api/windows';

const ACTIONS: { id: WindowsAction; label: string; hint: string }[] = [
  { id: 'report', label: 'Refresh report', hint: 'Ask the PC to send fresh inventory now' },
  { id: 'restart-agent', label: 'Restart agent', hint: 'Restart the management service on the PC' },
  { id: 'admit', label: 'Approve PC', hint: 'Let a new PC join and receive its certificate' },
];

export function WindowsDeviceDetailPage() {
  const { id = '' } = useParams();
  const toast = useToast();
  const [pc, setPc] = useState<WindowsPc | null>(null);
  const [commands, setCommands] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await getWindowsPc(id);
      setPc(r.device);
      setCommands(r.commands);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this PC');
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);

  const run = async (a: WindowsAction) => {
    setBusy(a);
    try {
      await sendWindowsCommand(id, a);
      toast.push('ok', 'Command sent', 'The PC will act on it when it next checks in.');
      setTimeout(() => void load(), 4000);
    } catch (e) {
      toast.push('err', 'Command failed', e instanceof Error ? e.message : 'The command failed');
    } finally {
      setBusy(null);
    }
  };

  const st = pc ? windowsState(pc) : null;
  const rows: [string, string][] = pc
    ? [
        ['Windows', orDash(pc.osDescription)],
        ['Version', `${orDash(pc.osVersion)} ${pc.osArch}`.trim()],
        ['Model', `${orDash(pc.manufacturer)} ${pc.model}`.trim()],
        ['Serial', orDash(pc.serial)],
        ['Processor', `${orDash(pc.cpu)}${pc.cpuCores ? ` · ${pc.cpuCores} cores` : ''}`],
        ['Memory', pc.memoryMB ? fmtMemory(pc.memoryMB) : '—'],
        ['IP / MAC', `${orDash(pc.ip)} · ${orDash(pc.mac)}`],
        ['Signed-in user', orDash(pc.loggedInUser)],
        ['Domain', orDash(pc.domain)],
        ['Last contact', `${fmtDateTime(pc.lastContact)} (${fmtRelative(pc.lastContact)})`],
        ['Last boot', fmtDateTime(pc.lastBoot)],
        ['Updates', pc.pendingUpdates ? 'Updates pending' : orDash(pc.updateStatus)],
        ['Antivirus', pc.antivirus ? `${pc.antivirus.name}${pc.antivirus.active ? '' : ' (inactive)'}` : '—'],
        ['Installed apps', String(pc.appCount)],
      ]
    : [];

  return (
    <AppShell title={pc ? windowsName(pc) : 'Windows PC'}>
      <div className="dv-head">
        <Link to="/devices">← Devices</Link>
        <h1>{pc ? windowsName(pc) : 'Windows PC'}</h1>
        {st && <span className={`win-badge ${st.tone}`}>{st.label}</span>}
        {pc?.restartRequired && <span className="win-badge warn">Restart needed</span>}
      </div>
      {error && (
        <div className="panel">
          <div className="empty">
            <span className="label">Windows PC</span>
            {error}
          </div>
        </div>
      )}
      {pc && (
        <>
          <div className="panel win-block">
            <h3>Actions</h3>
            <div className="win-actions">
              {ACTIONS.filter(
                (a) => commands.includes(a.id) && (a.id !== 'admit' || pc.status === 'WaitingForAdmission'),
              ).map((a) => (
                <button key={a.id} className="btn" title={a.hint} disabled={busy !== null} onClick={() => void run(a.id)}>
                  {busy === a.id ? 'Sending…' : a.label}
                </button>
              ))}
              {commands.length === 0 && <span className="muted">Commands are not enabled on the Windows service.</span>}
            </div>
          </div>
          <div className="panel win-block">
            <h3>Details</h3>
            <dl className="win-facts">
              {rows.map(([k, v]) => (
                <div key={k} className="win-fact">
                  <dt className="muted">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          {pc.disks && pc.disks.length > 0 && (
            <div className="panel win-block">
              <h3>Drives</h3>
              {pc.disks.map((k) => (
                <div key={k.label} className="win-disk">
                  <strong>{k.label}</strong>
                  <span>
                    {k.usagePercent}% used · {k.remaining} free of {k.size} · {k.filesystem}
                  </span>
                  <span className="muted">BitLocker: {orDash(k.bitlockerStatus)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}

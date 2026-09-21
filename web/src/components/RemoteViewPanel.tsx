import { useEffect, useMemo, useState } from 'react';
import {
  getLatestSnapshots, snapshotUrl, startRemoteSession, stopRemoteSession,
  type RemoteKind, type RemoteSession, type RemoteSnapshotMeta,
} from '../api/remoteView';
import { useToast } from '../ui/toast';
import { fmtRelative } from '../ui/format';

const KINDS: Array<{ key: RemoteKind; label: string }> = [
  { key: 'screen', label: 'Screen' },
  { key: 'cameraFront', label: 'Front camera' },
  { key: 'cameraBack', label: 'Back camera' },
  { key: 'mic', label: 'Microphone' },
];

/** Admin-only, time-boxed latest-capture view. Bytes remain behind the private session-cookie API. */
export function RemoteViewPanel({ deviceId, isDeviceOwner }: { deviceId: string; isDeviceOwner: boolean | null | undefined }) {
  const toast = useToast();
  const [durationSec, setDurationSec] = useState(300);
  const [intervalSec, setIntervalSec] = useState(1);
  const [kinds, setKinds] = useState<RemoteKind[]>(['screen']);
  const [session, setSession] = useState<RemoteSession | null>(null);
  const [snapshots, setSnapshots] = useState<RemoteSnapshotMeta[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await getLatestSnapshots(deviceId);
        if (live) setSnapshots(next);
      } catch {
        // Remote capture is optional. Avoid repeated error toasts while polling a disconnected device.
      }
      if (live) timer = setTimeout(() => void poll(), session ? Math.max(intervalSec * 1000, 1000) : 10000);
    };
    void poll();
    return () => { live = false; clearTimeout(timer); };
  }, [deviceId, session, intervalSec]);

  const byKind = useMemo(() => new Map(snapshots.map((s) => [s.kind, s])), [snapshots]);

  function toggle(kind: RemoteKind) {
    setKinds((current) => current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind]);
  }

  async function start() {
    if (kinds.length === 0) {
      toast.push('err', 'Choose a capture source', 'Select at least one source.');
      return;
    }
    setBusy(true);
    try {
      const started = await startRemoteSession(deviceId, { durationSec, intervalSec, kinds });
      setSession(started);
      toast.push('ok', 'Remote session requested', 'Captures appear after the device receives the command.');
    } catch (e) {
      toast.push('err', 'Could not start remote session', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    setBusy(true);
    try {
      await stopRemoteSession(deviceId);
      setSession(null);
      toast.push('ok', 'Stop requested', 'The device stops at its next command check-in.');
    } catch (e) {
      toast.push('err', 'Could not stop remote session', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  }

  if (!isDeviceOwner) {
    return <p className="muted">Remote capture requires a Device Owner enrollment.</p>;
  }

  return (
    <div className="remote-view">
      <p className="note">Time-boxed snapshots only. Screen capture requires one-time Accessibility enablement on the device. Camera and microphone use display Android’s system privacy indicators.</p>
      <div className="upd-actions" style={{ marginBottom: 12 }}>
        <label>Duration <input type="number" min={30} max={1800} value={durationSec} disabled={busy || !!session} onChange={(e) => setDurationSec(Number(e.target.value) || 30)} /> sec</label>
        <label>Interval <input type="number" min={1} max={60} value={intervalSec} disabled={busy || !!session} onChange={(e) => setIntervalSec(Number(e.target.value) || 1)} /> sec</label>
      </div>
      <div className="upd-actions" style={{ marginBottom: 12 }}>
        {KINDS.map(({ key, label }) => <label key={key}><input type="checkbox" checked={kinds.includes(key)} disabled={busy || !!session} onChange={() => toggle(key)} /> {label}</label>)}
      </div>
      {session ? (
        <button className="btn btn-sm" disabled={busy} onClick={() => void stop()}>{busy ? 'Stopping…' : 'Stop session'}</button>
      ) : (
        <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void start()}>{busy ? 'Starting…' : 'Start remote session'}</button>
      )}
      <div style={{ marginTop: 18, display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
        {KINDS.map(({ key, label }) => {
          const snapshot = byKind.get(key);
          return <section className="panel" key={key} style={{ padding: 12 }}>
            <strong>{label}</strong>
            <small className="muted" style={{ display: 'block', margin: '4px 0 8px' }}>{snapshot ? fmtRelative(snapshot.capturedAt) : 'No capture yet'}</small>
            {snapshot && key === 'mic' && <audio controls src={snapshotUrl(deviceId, key, snapshot.capturedAt)} style={{ width: '100%' }} />}
            {snapshot && key !== 'mic' && <img alt={`Latest ${label.toLowerCase()} capture`} src={snapshotUrl(deviceId, key, snapshot.capturedAt)} style={{ display: 'block', width: '100%', maxHeight: 340, objectFit: 'contain', background: '#000' }} />}
          </section>;
        })}
      </div>
    </div>
  );
}

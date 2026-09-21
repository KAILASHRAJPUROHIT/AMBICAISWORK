import { useEffect, useMemo, useRef, useState } from 'react';
import {
  getLatestSnapshots, snapshotUrl, startRemoteSession, stopRemoteSession, sendRemoteInput,
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

/** Admin-only, time-boxed latest-capture view and full remote control. */
export function RemoteViewPanel({ deviceId, isDeviceOwner }: { deviceId: string; isDeviceOwner: boolean | null | undefined }) {
  const toast = useToast();
  const [durationSec, setDurationSec] = useState(300);
  const [intervalSec, setIntervalSec] = useState(0.5);
  const [kinds, setKinds] = useState<RemoteKind[]>(['screen']);
  const [session, setSession] = useState<RemoteSession | null>(null);
  const [snapshots, setSnapshots] = useState<RemoteSnapshotMeta[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number; time: number } | null>(null);
  const [ripple, setRipple] = useState<{ x: number; y: number; id: number } | null>(null);
  const [inputText, setInputText] = useState('');
  const imgRef = useRef<HTMLImageElement | null>(null);

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
      if (live) {
        const delayMs = session ? Math.max(Math.round(intervalSec * 1000), 250) : 10000;
        timer = setTimeout(() => void poll(), delayMs);
      }
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
      // Server expects integer seconds for protocol compatibility; round interval to 1 minimum for command payload
      const started = await startRemoteSession(deviceId, {
        durationSec,
        intervalSec: Math.max(1, Math.round(intervalSec)),
        kinds,
      });
      setSession(started);
      toast.push('ok', 'Remote session started', 'Live stream active. Click on screen to inject touch.');
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
      toast.push('ok', 'Stop requested', 'The device stops capture.');
    } catch (e) {
      toast.push('err', 'Could not stop remote session', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLImageElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setDragStart({ x, y, time: Date.now() });
  };

  const handleMouseUp = async (e: React.MouseEvent<HTMLImageElement>) => {
    if (!dragStart) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const endX = (e.clientX - rect.left) / rect.width;
    const endY = (e.clientY - rect.top) / rect.height;
    const dist = Math.hypot(endX - dragStart.x, endY - dragStart.y);
    const duration = Date.now() - dragStart.time;
    setDragStart(null);

    setRipple({ x: endX * 100, y: endY * 100, id: Date.now() });

    try {
      if (dist < 0.03) {
        await sendRemoteInput(deviceId, { action: 'tap', x: dragStart.x, y: dragStart.y });
      } else {
        await sendRemoteInput(deviceId, {
          action: 'swipe',
          x: dragStart.x,
          y: dragStart.y,
          endX,
          endY,
          durationMs: Math.max(duration, 200),
        });
      }
    } catch (err) {
      toast.push('err', 'Input injection failed', err instanceof Error ? err.message : '');
    }
  };

  const sendKey = async (key: 'back' | 'home' | 'recents' | 'notifications' | 'quicksettings' | 'power' | 'lock' | 'volume_up' | 'volume_down') => {
    try {
      await sendRemoteInput(deviceId, { action: 'key', key });
      toast.push('ok', 'Action dispatched', `Key: ${key}`);
    } catch (err) {
      toast.push('err', 'Key injection failed', err instanceof Error ? err.message : '');
    }
  };

  const handleSendText = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText) return;
    try {
      await sendRemoteInput(deviceId, { action: 'text', text: inputText });
      toast.push('ok', 'Text injected', inputText);
      setInputText('');
    } catch (err) {
      toast.push('err', 'Text injection failed', err instanceof Error ? err.message : '');
    }
  };

  if (!isDeviceOwner) {
    return <p className="muted">Remote capture requires a Device Owner enrollment.</p>;
  }

  return (
    <div className="remote-view">
      <p className="note">
        Live remote view and full device control. Click or drag directly on the screen to tap or swipe.
        Type text or click navigation buttons to control the device remotely.
      </p>
      <div className="upd-actions" style={{ marginBottom: 12, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <label>
          Duration{' '}
          <input
            type="number"
            min={30}
            max={1800}
            value={durationSec}
            disabled={busy || !!session}
            onChange={(e) => setDurationSec(Number(e.target.value) || 30)}
            style={{ width: 80 }}
          />{' '}
          sec
        </label>
        <label>
          Speed / Interval{' '}
          <select
            value={intervalSec}
            disabled={busy || !!session}
            onChange={(e) => setIntervalSec(Number(e.target.value))}
            style={{ padding: '4px 8px', borderRadius: 4 }}
          >
            <option value={0.25}>Ultra Fast (250ms / 4 fps)</option>
            <option value={0.5}>Smooth (500ms / 2 fps)</option>
            <option value={1}>Normal (1s / 1 fps)</option>
            <option value={2}>Eco (2s)</option>
            <option value={5}>Low Bandwidth (5s)</option>
          </select>
        </label>
      </div>

      <div className="upd-actions" style={{ marginBottom: 12, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {KINDS.map(({ key, label }) => (
          <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={kinds.includes(key)}
              disabled={busy || !!session}
              onChange={() => toggle(key)}
            />
            {label}
          </label>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
        {session ? (
          <button className="btn btn-sm" disabled={busy} onClick={() => void stop()}>
            {busy ? 'Stopping…' : 'Stop session'}
          </button>
        ) : (
          <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void start()}>
            {busy ? 'Starting…' : 'Start remote session'}
          </button>
        )}
      </div>

      {/* Global Device Control Bar */}
      <div
        className="panel"
        style={{
          padding: 12,
          marginBottom: 16,
          background: 'var(--bg-subtle, #1a1e24)',
          borderRadius: 8,
          border: '1px solid var(--border, #2d3748)',
        }}
      >
        <strong style={{ display: 'block', marginBottom: 8 }}>Device Remote Control</strong>
        <form onSubmit={handleSendText} style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="Type text to type into focused input on device…"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            style={{ flex: '1 1 240px', padding: '6px 10px', borderRadius: 4, border: '1px solid #4a5568', background: '#0d1117', color: '#fff' }}
          />
          <button type="submit" className="btn btn-sm btn-primary" disabled={!inputText}>
            Send Text
          </button>
        </form>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button className="btn btn-sm" onClick={() => void sendKey('back')} title="Back key">◀ Back</button>
          <button className="btn btn-sm" onClick={() => void sendKey('home')} title="Home key">⭘ Home</button>
          <button className="btn btn-sm" onClick={() => void sendKey('recents')} title="Recents key">▢ Recents</button>
          <button className="btn btn-sm" onClick={() => void sendKey('notifications')} title="Notification Shade">🔔 Notifications</button>
          <button className="btn btn-sm" onClick={() => void sendKey('quicksettings')} title="Quick Settings">⚙️ Quick Settings</button>
          <button className="btn btn-sm" onClick={() => void sendKey('power')} title="Power Menu">⚡ Power Menu</button>
          <button className="btn btn-sm" onClick={() => void sendKey('lock')} title="Lock screen">🔒 Lock</button>
          <button className="btn btn-sm" onClick={() => void sendKey('volume_down')} title="Volume Down">🔉 Vol -</button>
          <button className="btn btn-sm" onClick={() => void sendKey('volume_up')} title="Volume Up">🔊 Vol +</button>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
        {KINDS.map(({ key, label }) => {
          const snapshot = byKind.get(key);
          const isScreen = key === 'screen';
          return (
            <section className="panel" key={key} style={{ padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>{label}</strong>
                {isScreen && <span className="ub-ch" style={{ fontSize: '0.8em' }}>Interactive touch</span>}
              </div>
              <small className="muted" style={{ display: 'block', margin: '4px 0 8px' }}>
                {snapshot ? fmtRelative(snapshot.capturedAt) : 'No capture yet'}
              </small>

              {snapshot && key === 'mic' && (
                <audio controls src={snapshotUrl(deviceId, key, snapshot.capturedAt)} style={{ width: '100%' }} />
              )}

              {snapshot && key !== 'mic' && (
                <div style={{ position: 'relative', display: 'inline-block', width: '100%', overflow: 'hidden' }}>
                  <img
                    ref={isScreen ? imgRef : undefined}
                    alt={`Latest ${label.toLowerCase()} capture`}
                    src={snapshotUrl(deviceId, key, snapshot.capturedAt)}
                    onMouseDown={isScreen ? handleMouseDown : undefined}
                    onMouseUp={isScreen ? handleMouseUp : undefined}
                    draggable={false}
                    style={{
                      display: 'block',
                      width: '100%',
                      maxHeight: 380,
                      objectFit: 'contain',
                      background: '#000',
                      cursor: isScreen ? 'crosshair' : 'default',
                      userSelect: 'none',
                    }}
                  />
                  {isScreen && ripple && (
                    <span
                      key={ripple.id}
                      style={{
                        position: 'absolute',
                        left: `${ripple.x}%`,
                        top: `${ripple.y}%`,
                        width: 16,
                        height: 16,
                        borderRadius: '50%',
                        background: 'rgba(59, 130, 246, 0.7)',
                        border: '2px solid #fff',
                        transform: 'translate(-50%, -50%)',
                        pointerEvents: 'none',
                      }}
                    />
                  )}
                </div>
              )}

              {isScreen && !snapshot && (
                <div style={{ padding: '16px 8px', textAlign: 'center', background: 'var(--bg-subtle, #1a1a1a)', borderRadius: 6, marginTop: 8 }}>
                  <p style={{ margin: '0 0 6px', fontWeight: 500, color: 'var(--text, #fff)' }}>No screen capture yet</p>
                  <small className="muted">
                    Screen capture requires the <b>AMBIC MDM</b> Accessibility Service enabled in device <b>Settings &gt; Accessibility</b>.
                  </small>
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

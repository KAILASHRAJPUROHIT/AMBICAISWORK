import { useCallback, useEffect, useRef, useState } from 'react';
import { getUpdateStatus, type UpdateStatus } from '../api/updates';
import {
  getActiveRollout, createRollout, promoteRollout, cancelRollout, retryRollout,
  type ActiveRollout, type RolloutCounts, type RolloutDeviceStatus,
} from '../api/rollout';
import { searchDevices, type DeviceView } from '../api/devices';

const AGENT_PACKAGE = (import.meta.env.VITE_AGENT_PACKAGE as string) || 'com.mdmesh.agent';

const STATUS_LABEL: Record<RolloutDeviceStatus['status'], string> = {
  UPDATED: 'Updated',
  PENDING: 'Installing…',
  OUTSTANDING: 'Queued',
  INELIGIBLE: 'Not eligible',
};

/** A labelled progress bar for one cohort (canary or fleet) with per-device breakdown. */
function CohortBar({ label, c, devices }: { label: string; c: RolloutCounts; devices?: RolloutDeviceStatus[] }) {
  const denom = Math.max(c.total - c.ineligible, 1); // ineligible devices can't be updated — exclude
  const pct = Math.round((c.updated / denom) * 100);
  return (
    <div className="rollout-cohort">
      <div className="rollout-cohort-head">
        <span>{label}</span>
        <span className="mono">{c.updated}/{c.total - c.ineligible} updated</span>
      </div>
      <div className="rollout-track"><div className="rollout-fill" style={{ width: `${pct}%` }} /></div>
      <div className="rollout-legend">
        {c.pending > 0 && <span className="ub-warn">{c.pending} installing</span>}
        {c.outstanding > 0 && <span>{c.outstanding} queued</span>}
        {c.ineligible > 0 && <span className="muted">{c.ineligible} too old</span>}
      </div>
      {devices && devices.length > 0 && (
        <div className="rollout-devicelist" style={{ marginTop: 6 }}>
          {devices.map((d) => (
            <div key={d.deviceNumber} className="rollout-device" style={{ justifyContent: 'space-between' }}>
              <div>
                <span className="mono">{d.description || d.deviceNumber}</span>
                {d.description && <span className="muted" style={{ marginLeft: 8, fontSize: '0.85em' }}>({d.deviceNumber})</span>}
                {d.currentVersion && <span className="muted" style={{ marginLeft: 8, fontSize: '0.85em' }}>· v{d.currentVersion}</span>}
              </div>
              <span className={d.status === 'PENDING' ? 'ub-warn' : d.status === 'INELIGIBLE' ? 'muted' : d.status === 'UPDATED' ? 'ub-ch' : ''}>
                {STATUS_LABEL[d.status]}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Staged agent-APK rollout: pick a canary set, watch it land, then promote to the fleet. */
export function RolloutPanel() {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [rollout, setRollout] = useState<ActiveRollout | null>(null);
  const [picking, setPicking] = useState(false);
  const [devices, setDevices] = useState<DeviceView[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const on = useRef(true); // false after unmount — stops in-flight refreshes from re-arming the poll

  const refresh = useCallback(async () => {
    const r = await getActiveRollout().catch(() => null);
    if (!on.current) return;
    setRollout(r);
    const active = !!r && (r.stage === 'canary' || r.stage === 'fleet');
    clearTimeout(timer.current);
    if (active) timer.current = setTimeout(() => void refresh(), 10000); // poll while a rollout runs
  }, []);

  useEffect(() => {
    on.current = true;
    void getUpdateStatus().then((s) => { if (on.current) setStatus(s); });
    void refresh();
    return () => { on.current = false; clearTimeout(timer.current); };
  }, [refresh]);

  const openPicker = async () => {
    setErr(null);
    setPicking(true);
    try {
      const list = await searchDevices({ pageSize: 200 });
      setDevices(list.devices.items);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const toggle = (num: string) => setSelected((s) => {
    const next = new Set(s);
    if (next.has(num)) next.delete(num); else next.add(num);
    return next;
  });

  const apk = status?.apk;

  const start = async () => {
    if (!apk) return;
    setBusy(true); setErr(null);
    try {
      const created = await createRollout({
        targetVersion: apk.version,
        packageName: AGENT_PACKAGE,
        apkVersionCode: apk.versionCode,
        apkSha256: apk.sha256,
        canaryDeviceNumbers: Array.from(selected),
      });
      setRollout(created);
      setPicking(false);
      setSelected(new Set());
      void refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const promote = async () => {
    if (!rollout) return;
    const canary = rollout.progress.canary;
    const pendingCount = canary.total - canary.ineligible - canary.updated;
    if (pendingCount > 0) {
      if (!window.confirm(`Only ${canary.updated}/${canary.total - canary.ineligible} canary devices have updated. Force promote to fleet anyway?`)) {
        return;
      }
    } else {
      if (!window.confirm('Promote this update to the rest of the fleet?')) return;
    }
    setBusy(true); setErr(null);
    try { setRollout(await promoteRollout(rollout.id)); void refresh(); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  const retry = async () => {
    if (!rollout) return;
    setBusy(true); setErr(null);
    try { setRollout(await retryRollout(rollout.id)); void refresh(); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  const finish = async () => {
    if (!rollout) return;
    setBusy(true); setErr(null);
    try { await cancelRollout(rollout.id); setRollout(null); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  // Nothing to show: no active rollout and no mirrored APK to offer.
  const active = rollout && (rollout.stage === 'canary' || rollout.stage === 'fleet');
  if (!active && !(apk && apk.available)) return null;

  return (
    <section className="panel">
      <div className="panel-head"><h2 className="panel-title">Agent rollout</h2></div>

      {active && rollout && (
        <>
          <div className="set-row">
            <span className="k">Rolling out</span>
            <span className="v mono">
              v{rollout.targetVersion} · <span className="ub-ch">{rollout.stage}</span>
            </span>
          </div>
          <CohortBar label="Canary" c={rollout.progress.canary} devices={rollout.progress.canaryDevices} />
          {rollout.progress.fleet && <CohortBar label="Fleet" c={rollout.progress.fleet} devices={rollout.progress.fleetDevices ?? undefined} />}
          <div className="set-row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button
              className="btn btn-sm"
              onClick={() => void retry()}
              disabled={busy}
              title="Re-enqueue update commands and wake non-updated devices"
            >
              {busy ? 'Waking…' : 'Retry / Wake devices'}
            </button>
            {rollout.stage === 'canary' && (
              <button
                className="btn btn-sm btn-primary"
                onClick={() => void promote()}
                disabled={busy}
                title={rollout.progress.canary.updated < 1 ? 'Force promote to fleet' : 'Promote to fleet'}
              >
                Promote to fleet
              </button>
            )}
            <button className="btn btn-sm" onClick={() => void finish()} disabled={busy}>
              {rollout.stage === 'fleet' ? 'Finish' : 'Cancel'}
            </button>
          </div>
        </>
      )}

      {!active && apk && apk.available && !picking && (
        <div className="set-row">
          <span className="k">
            Agent v{apk.version} available
            <small>Push the new agent APK to devices in stages.</small>
          </span>
          <span className="v">
            <button className="btn btn-sm btn-primary" onClick={() => void openPicker()}>
              Roll out…
            </button>
          </span>
        </div>
      )}

      {!active && picking && (
        <>
          <p className="muted" style={{ margin: '0 0 8px' }}>
            Select the <b>canary</b> devices to update first (v{apk?.version}). You'll promote to the
            rest of the fleet once they're confirmed healthy.
          </p>
          <div className="rollout-devicelist">
            {devices.map((d) => (
              <label key={d.id} className="rollout-device">
                <input type="checkbox" checked={selected.has(d.number)} onChange={() => toggle(d.number)} />
                <span className="mono">{d.description || d.number}</span>
                {d.description && <span className="muted" style={{ marginLeft: 6 }}>({d.number})</span>}
              </label>
            ))}
            {devices.length === 0 && <span className="muted">No devices.</span>}
          </div>
          <div className="set-row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button className="btn btn-sm" onClick={() => { setPicking(false); setSelected(new Set()); }} disabled={busy}>
              Cancel
            </button>
            <button className="btn btn-sm btn-primary" onClick={() => void start()} disabled={busy || selected.size === 0}>
              {busy ? 'Starting…' : `Start canary (${selected.size})`}
            </button>
          </div>
        </>
      )}

      {err && <p className="ub-warn" style={{ marginTop: 8 }}>{err}</p>}
    </section>
  );
}

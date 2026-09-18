import { useCallback, useEffect, useRef, useState } from 'react';
import {
  listActiveAppRollouts, promoteAppRollout, cancelAppRollout,
  type AppRollout, type AppRolloutCounts, type AppRolloutDeviceStatus,
} from '../api/appRollout';

const STATUS_LABEL: Record<AppRolloutDeviceStatus['status'], string> = {
  UPDATED: 'Updated', PENDING: 'Installing…', OUTSTANDING: 'Queued', INELIGIBLE: 'Not eligible',
};

function CohortBar({ label, c, devices }: { label: string; c: AppRolloutCounts; devices: AppRolloutDeviceStatus[] }) {
  const denom = Math.max(c.total - c.ineligible, 1);
  const pct = Math.round((c.updated / denom) * 100);
  return (
    <div className="rollout-cohort">
      <div className="rollout-cohort-head">
        <span>{label}</span>
        <span className="mono">{c.updated}/{c.total - c.ineligible} updated</span>
      </div>
      <div className="rollout-track"><div className="rollout-fill" style={{ width: `${pct}%` }} /></div>
      <div className="rollout-devicelist" style={{ marginTop: 6 }}>
        {devices.map((d) => (
          <div key={d.deviceNumber} className="rollout-device" style={{ justifyContent: 'space-between' }}>
            <span className="mono">{d.deviceNumber}</span>
            <span className={d.status === 'PENDING' ? 'ub-warn' : d.status === 'INELIGIBLE' ? 'muted' : ''}>
              {STATUS_LABEL[d.status]}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** One Library-app rollout in progress — mirrors RolloutPanel's layout, but there can be several
 *  of these at once (one per app), and creation happens from DeployModal, not here. */
function OneRollout({ r, onChanged }: { r: AppRollout; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const promote = async () => {
    if (!window.confirm(`Promote ${r.displayName ?? r.packageName} to the rest of the fleet?`)) return;
    setBusy(true); setErr(null);
    try { await promoteAppRollout(r.id); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : ''); }
    finally { setBusy(false); }
  };
  const finish = async () => {
    setBusy(true); setErr(null);
    try { await cancelAppRollout(r.id); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : ''); }
    finally { setBusy(false); }
  };

  return (
    <div className="rollout-cohort" style={{ borderTop: '1px solid var(--border, #2a2a2a)', paddingTop: 12 }}>
      <div className="set-row">
        <span className="k">{r.displayName ?? r.packageName}</span>
        <span className="v mono">v{r.targetVersion} · <span className="ub-ch">{r.stage}</span></span>
      </div>
      <CohortBar label="Canary" c={r.progress.canary} devices={r.progress.canaryDevices} />
      {r.progress.fleet && r.progress.fleetDevices && (
        <CohortBar label="Fleet" c={r.progress.fleet} devices={r.progress.fleetDevices} />
      )}
      <div className="set-row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
        {r.stage === 'canary' && (
          <button
            className="btn btn-sm btn-primary"
            onClick={() => void promote()}
            disabled={busy || r.progress.canary.pending > 0 || r.progress.canary.outstanding > 0 || r.progress.canary.updated < 1}
            title="Enabled once every canary device has updated"
          >
            Promote to fleet
          </button>
        )}
        <button className="btn btn-sm" onClick={() => void finish()} disabled={busy}>
          {r.stage === 'fleet' ? 'Finish' : 'Cancel'}
        </button>
      </div>
      {err && <p className="ub-warn" style={{ marginTop: 8 }}>{err}</p>}
    </div>
  );
}

/** Every active Library-app rollout (started from "Deploy" → "Push to device(s)"), with progress
 *  and a per-device pending/updated breakdown. Polls while any rollout is in flight. */
export function AppRolloutStatus() {
  const [rollouts, setRollouts] = useState<AppRollout[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const on = useRef(true);

  const refresh = useCallback(async () => {
    const list = await listActiveAppRollouts().catch(() => []);
    if (!on.current) return;
    setRollouts(list);
    clearTimeout(timer.current);
    if (list.length > 0) timer.current = setTimeout(() => void refresh(), 10000);
  }, []);

  useEffect(() => {
    on.current = true;
    void refresh();
    return () => { on.current = false; clearTimeout(timer.current); };
  }, [refresh]);

  if (rollouts.length === 0) return null;

  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head"><h2 className="panel-title">Pending updates</h2></div>
      {rollouts.map((r) => <OneRollout key={r.id} r={r} onChanged={() => void refresh()} />)}
    </section>
  );
}

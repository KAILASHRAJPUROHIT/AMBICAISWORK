import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppShell } from '../ui/AppShell';
import { useToast } from '../ui/toast';
import { useDevices } from '../data/useDevices';
import { IndoorPlanCanvas, type PlanDevice, type PlanTool } from '../components/IndoorPlanCanvas';
import {
  EMPTY_PLAN, clearIndoorSurvey, deleteIndoorPoint, getIndoorMap, indoorFixOf, saveIndoorMap, shrinkImage,
  type IndoorFix, type IndoorMapState, type IndoorPlan,
} from '../api/indoor';
import { forceSync, listCommandHistory, queueCommand } from '../api/commands';
import { getTelemetry } from '../api/telemetry';
import type { DeviceView } from '../api/devices';
import { fmtRelative } from '../ui/format';

type Tab = 'plan' | 'survey' | 'live';

/** A position older than this is drawn grey: the device has not re-checked its place recently. */
const FIX_STALE_MS = 10 * 60_000;
/** Fewer surveyed points than this gives poor positions. */
const MIN_POINTS = 15;

function errText(e: unknown): string {
  return e instanceof Error ? e.message : 'Something went wrong';
}

export function IndoorPage() {
  const toast = useToast();
  const { devices } = useDevices();
  const [tab, setTab] = useState<Tab>('plan');
  const [map, setMap] = useState<IndoorMapState | null>(null);
  const [plan, setPlan] = useState<IndoorPlan>(EMPTY_PLAN);
  const [image, setImage] = useState<string | null>(null);
  const [imageChanged, setImageChanged] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const m = await getIndoorMap();
      setMap(m);
      setPlan(m.plan ?? EMPTY_PLAN);
      setImage(m.image);
      setImageChanged(false);
      setDirty(false);
      setLoadError(null);
    } catch (e) {
      setLoadError(errText(e));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const refreshPoints = useCallback(async () => {
    try {
      const m = await getIndoorMap();
      setMap((prev) => (prev ? { ...prev, points: m.points } : m));
    } catch { /* keep what is shown */ }
  }, []);

  const savedPlan = !!map?.plan;
  const edit = (p: IndoorPlan) => { setPlan(p); setDirty(true); };

  const save = async () => {
    if (!(plan.widthM > 0 && plan.heightM > 0)) { toast.push('err', 'Enter the store width and depth in metres'); return; }
    setSaving(true);
    try {
      await saveIndoorMap(plan, imageChanged ? image : undefined);
      toast.push('ok', 'Floor plan saved', 'Devices pick it up within about 10 minutes.');
      await load();
    } catch (e) {
      toast.push('err', 'Could not save the floor plan', errText(e));
    } finally {
      setSaving(false);
    }
  };

  const pickImage = async (file: File | undefined) => {
    if (!file) return;
    try {
      const data = await shrinkImage(file);
      setImage(data);
      setImageChanged(true);
      // Match the plan's depth to the picture's shape so distances are not stretched.
      const probe = new Image();
      probe.onload = () => {
        if (probe.width > 0) {
          const depth = Math.round((plan.widthM * probe.height) / probe.width * 10) / 10;
          setPlan((p) => ({ ...p, heightM: depth }));
        }
      };
      probe.src = data;
      setDirty(true);
    } catch (e) {
      toast.push('err', 'Could not use that picture', errText(e));
    }
  };

  return (
    <AppShell title="Indoor map">
      <div className="page-head">
        <div>
          <p className="ais-eyebrow">IN-STORE POSITIONING</p>
          <h1>Indoor map</h1>
          <p className="page-sub">Draw the store, walk it once with a tablet to teach it the Wi-Fi, then see where every device is.</p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Indoor map sections">
        {([['plan', '1 · Floor plan'], ['survey', '2 · Survey'], ['live', '3 · Where is it?']] as Array<[Tab, string]>).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>

      {loadError && <p className="err-text">{loadError}</p>}

      {tab === 'plan' && (
        <PlanTab
          plan={plan} image={image} dirty={dirty} saving={saving} savedPlan={savedPlan}
          onEdit={edit} onPickImage={pickImage} onRemoveImage={() => { setImage(null); setImageChanged(true); setDirty(true); }}
          onSave={save}
        />
      )}
      {tab === 'survey' && (
        <SurveyTab
          plan={plan} image={image} map={map} devices={devices} savedPlan={savedPlan && !dirty}
          onChanged={refreshPoints}
        />
      )}
      {tab === 'live' && <LiveTab plan={plan} image={image} devices={devices} savedPlan={savedPlan} pointCount={map?.points.length ?? 0} />}
    </AppShell>
  );
}

/* ----------------------------------------------------------------------------------------------- Floor plan */

function PlanTab(props: {
  plan: IndoorPlan; image: string | null; dirty: boolean; saving: boolean; savedPlan: boolean;
  onEdit: (p: IndoorPlan) => void; onPickImage: (f: File | undefined) => void; onRemoveImage: () => void; onSave: () => void;
}) {
  const { plan, image, onEdit } = props;
  const [tool, setTool] = useState<PlanTool>('view');
  const num = (v: string, fallback: number) => { const n = parseFloat(v); return Number.isFinite(n) ? n : fallback; };
  const tools: Array<[PlanTool, string, string]> = [
    ['view', 'Look', 'Just view the plan'],
    ['wall', 'Draw walls', 'Click corner to corner. Walls stop devices being placed on the other side.'],
    ['zone', 'Add zone', 'Click two opposite corners, then name it (Counter 2, Vault, Billing...).'],
    ['erase', 'Erase', 'Click a wall or zone to remove it.'],
  ];
  return (
    <section className="panel">
      <div className="panel-head"><h2 className="panel-title">Floor plan</h2></div>
      <div className="indoor-form">
        <label>Store width (m)
          <input id="indoor-width" type="number" min="1" step="0.5" value={plan.widthM}
            onChange={(e) => onEdit({ ...plan, widthM: num(e.target.value, plan.widthM) })} />
        </label>
        <label>Store depth (m)
          <input id="indoor-height" type="number" min="1" step="0.5" value={plan.heightM}
            onChange={(e) => onEdit({ ...plan, heightM: num(e.target.value, plan.heightM) })} />
        </label>
        <label title="Compass bearing of the top of the picture. 0 = the top of the picture points north.">
          Top of picture points to (° from north)
          <input id="indoor-north" type="number" min="0" max="359" step="5" value={plan.northDeg}
            onChange={(e) => onEdit({ ...plan, northDeg: ((num(e.target.value, plan.northDeg) % 360) + 360) % 360 })} />
        </label>
        <label>Floor plan picture
          <input id="indoor-image" type="file" accept="image/*" onChange={(e) => props.onPickImage(e.target.files?.[0])} />
        </label>
        {image && <button className="btn btn-sm" onClick={props.onRemoveImage}>Remove picture</button>}
      </div>
      <p className="muted">
        Measure the store's real width with a tape or a wall plan. Everything else (accuracy, zones, walking distance) is
        scaled from it. Changing width or depth after surveying moves the surveyed points, so set them first.
      </p>

      <div className="seg" role="group" aria-label="Plan tools" style={{ margin: '10px 0' }}>
        {tools.map(([k, label, hint]) => (
          <button key={k} className={tool === k ? 'on' : ''} title={hint} onClick={() => setTool(k)}>{label}</button>
        ))}
      </div>
      <IndoorPlanCanvas plan={plan} image={image} tool={tool} onPlanChange={onEdit} />

      <div className="indoor-lists">
        <div>
          <h3>Zones ({plan.zones.length})</h3>
          {plan.zones.length === 0 && <p className="muted">No zones yet. Add counters, rooms and the vault so positions have names.</p>}
          {plan.zones.map((z, i) => (
            <div key={`${z.name}-${i}`} className="set-row">
              <input aria-label={`Zone ${i + 1} name`} value={z.name}
                onChange={(e) => onEdit({ ...plan, zones: plan.zones.map((q, j) => (j === i ? { ...q, name: e.target.value } : q)) })} />
              <span className="muted">{z.w.toFixed(1)} × {z.h.toFixed(1)} m</span>
              <button className="btn btn-sm" onClick={() => onEdit({ ...plan, zones: plan.zones.filter((_, j) => j !== i) })}>Remove</button>
            </div>
          ))}
        </div>
        <div>
          <h3>Walls ({plan.walls.length})</h3>
          <p className="muted">Draw the outer walls only if devices can be outside them; draw interior walls and big fixtures that block movement.</p>
        </div>
      </div>

      <div className="upd-actions">
        <button className="btn btn-primary" disabled={!props.dirty || props.saving} onClick={props.onSave}>
          {props.saving ? 'Saving…' : 'Save floor plan'}
        </button>
        {!props.savedPlan && <span className="muted">Nothing is saved yet.</span>}
        {props.dirty && <span className="muted">Unsaved changes.</span>}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------------------------------------- Survey */

function SurveyTab(props: {
  plan: IndoorPlan; image: string | null; map: IndoorMapState | null; devices: DeviceView[];
  savedPlan: boolean; onChanged: () => Promise<void>;
}) {
  const toast = useToast();
  const { plan, image, map, devices } = props;
  const [deviceNumber, setDeviceNumber] = useState('');
  const [pending, setPending] = useState<{ x: number; y: number } | null>(null);
  const [samples, setSamples] = useState(3);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const points = map?.points ?? [];
  const dots = useMemo(() => points.map((p) => ({ id: p.id, x: p.x, y: p.y })), [points]);

  const record = async () => {
    if (!pending || !deviceNumber) return;
    setBusy(true);
    setStatus('Sending to the device…');
    try {
      const q = await queueCommand(deviceNumber, {
        type: 'device.indoorSurvey',
        requiresCapability: 'device.indoorSurvey',
        payload: JSON.stringify({ x: pending.x, y: pending.y, samples }),
      });
      await forceSync(deviceNumber).catch(() => undefined);
      setStatus('The device is scanning Wi-Fi. Keep it still for about 30 seconds…');
      const deadline = Date.now() + 150_000;
      while (alive.current && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 3000));
        const hist = await listCommandHistory(deviceNumber, Date.now() - 600_000).catch(() => []);
        const mine = hist.find((h) => String(h.id) === String(q.id));
        if (mine && (mine.status === 'done' || mine.status === 'DONE')) {
          toast.push('ok', 'Point recorded', `${pending.x.toFixed(1)}, ${pending.y.toFixed(1)} m`);
          setStatus(null);
          await props.onChanged();
          return;
        }
        if (mine && /fail|unsupported|expired/i.test(mine.status)) {
          toast.push('err', 'The device could not record this point', mine.detail ?? mine.status);
          setStatus(mine.detail ?? mine.status);
          return;
        }
      }
      setStatus('The device has not answered yet. Check that it is online, then try again.');
    } catch (e) {
      toast.push('err', 'Could not send the survey command', errText(e));
      setStatus(null);
    } finally {
      setBusy(false);
    }
  };

  const removePoint = async (id: number) => {
    try { await deleteIndoorPoint(id); await props.onChanged(); } catch (e) { toast.push('err', 'Could not remove the point', errText(e)); }
  };
  const clearAll = async () => {
    if (!window.confirm('Delete the whole survey? Devices will lose their in-store position until you survey again.')) return;
    try { await clearIndoorSurvey(); await props.onChanged(); } catch (e) { toast.push('err', 'Could not clear the survey', errText(e)); }
  };

  if (!props.savedPlan) {
    return <section className="panel"><p className="muted">Save the floor plan first (step 1). Surveying uses the saved plan.</p></section>;
  }
  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Survey the store</h2>
        <span className="muted">{points.length} point{points.length === 1 ? '' : 's'} recorded</span>
      </div>
      <ol className="indoor-steps">
        <li>Carry a tablet (or the phone) and this page (a phone works) around the store.</li>
        <li>Stand somewhere, tap that spot on the plan below, and press <strong>Record here</strong>. Hold the device still while it scans.</li>
        <li>Repeat roughly every 2 metres along aisles and around counters. {MIN_POINTS}+ points for a small shop; more means better positions. Re-survey after moving fixtures.</li>
      </ol>
      <div className="indoor-form">
        <label>Device doing the survey
          <select id="indoor-survey-device" value={deviceNumber} onChange={(e) => setDeviceNumber(e.target.value)}>
            <option value="">Choose a device…</option>
            {devices.map((d) => <option key={d.id} value={d.number}>{d.description || d.number}</option>)}
          </select>
        </label>
        <label>Scans to average
          <select id="indoor-samples" value={samples} onChange={(e) => setSamples(Number(e.target.value))}>
            <option value={1}>1 (quick)</option><option value={3}>3 (recommended)</option><option value={5}>5 (most stable)</option>
          </select>
        </label>
      </div>
      <IndoorPlanCanvas plan={plan} image={image} tool="point" onPick={(x, y) => setPending({ x, y })} surveyPoints={dots} pending={pending} />
      <div className="upd-actions" style={{ marginTop: 10 }}>
        <button className="btn btn-primary" disabled={!pending || !deviceNumber || busy} onClick={record}>
          {busy ? 'Recording…' : pending ? `Record here (${pending.x.toFixed(1)}, ${pending.y.toFixed(1)} m)` : 'Tap a spot on the plan'}
        </button>
        <button className="btn btn-sm" disabled={points.length === 0} onClick={clearAll}>Delete whole survey</button>
        {points.length > 0 && points.length < MIN_POINTS && <span className="muted">Add more points for steadier positions.</span>}
      </div>
      {status && <p className="muted" role="status">{status}</p>}
      {points.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary>Recorded points</summary>
          <div className="indoor-points">
            {points.map((p) => (
              <div key={p.id} className="set-row">
                <span className="mono">{p.x.toFixed(1)}, {p.y.toFixed(1)} m</span>
                <span className="muted">{Object.keys(safeJson(p.rssi)).length} networks · {fmtRelative(p.createdAt)}</span>
                <button className="btn btn-sm" onClick={() => void removePoint(p.id)}>Remove</button>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function safeJson(s: string): Record<string, number> {
  try { return JSON.parse(s) as Record<string, number>; } catch { return {}; }
}

/* ------------------------------------------------------------------------------------------------- Live */

interface LiveRow { device: DeviceView; fix: IndoorFix | null }

function LiveTab(props: { plan: IndoorPlan; image: string | null; devices: DeviceView[]; savedPlan: boolean; pointCount: number }) {
  const toast = useToast();
  const { plan, image, devices } = props;
  const [rows, setRows] = useState<LiveRow[]>([]);
  const [locating, setLocating] = useState<string | null>(null);
  const [updated, setUpdated] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    const out = await Promise.all(devices.map(async (device): Promise<LiveRow> => {
      const t = await getTelemetry(device.number).catch(() => null);
      return { device, fix: indoorFixOf(t?.dynamic) };
    }));
    setRows(out);
    setUpdated(Date.now());
  }, [devices]);

  useEffect(() => {
    if (devices.length === 0) return;
    void refresh();
    const t = window.setInterval(() => { void refresh(); }, 15_000);
    return () => window.clearInterval(t);
  }, [devices, refresh]);

  const locate = async (d: DeviceView) => {
    setLocating(d.number);
    try {
      await queueCommand(d.number, { type: 'device.indoorLocate', requiresCapability: 'device.indoorLocate' });
      await forceSync(d.number).catch(() => undefined);
      toast.push('ok', `Locating ${d.description || d.number}`, 'The position updates here within about a minute.');
      window.setTimeout(() => { void refresh(); }, 25_000);
    } catch (e) {
      toast.push('err', 'Could not start locating', errText(e));
    } finally {
      setLocating(null);
    }
  };

  const dots: PlanDevice[] = rows.filter((r) => r.fix).map((r) => ({
    id: r.device.id,
    x: r.fix!.x,
    y: r.fix!.y,
    spreadM: r.fix!.spreadM,
    label: r.device.description || r.device.number.slice(0, 8),
    stale: Date.now() - r.fix!.at > FIX_STALE_MS,
  }));

  if (!props.savedPlan) {
    return <section className="panel"><p className="muted">Create and save a floor plan first (step 1).</p></section>;
  }
  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Where is it?</h2>
        <span className="muted">{updated ? `updated ${fmtRelative(updated)}` : 'loading…'}</span>
      </div>
      {props.pointCount < MIN_POINTS && (
        <p className="muted">Only {props.pointCount} surveyed point{props.pointCount === 1 ? '' : 's'}. Positions will be rough until the store is surveyed (step 2).</p>
      )}
      <IndoorPlanCanvas plan={plan} image={image} tool="view" devices={dots} />
      <div className="indoor-live-list">
        {rows.map(({ device, fix }) => {
          const stale = fix ? Date.now() - fix.at > FIX_STALE_MS : false;
          return (
            <div key={device.id} className="set-row">
              <strong>{device.description || device.number}</strong>
              <span>
                {fix
                  ? <>{fix.zone ? <strong>{fix.zone}</strong> : 'No zone'} · ±{fix.spreadM.toFixed(1)} m · <span style={stale ? { color: 'var(--warn, #d9822b)' } : undefined}>{fmtRelative(fix.at)}{stale ? ' (stale)' : ''}</span></>
                  : <span className="muted">No in-store position yet</span>}
              </span>
              <button className="btn btn-sm" disabled={locating === device.number} onClick={() => void locate(device)}>
                {locating === device.number ? 'Asking…' : 'Locate in store'}
              </button>
            </div>
          );
        })}
        {devices.length === 0 && <p className="muted">No devices enrolled.</p>}
      </div>
      <p className="muted">
        A device only appears here after it has downloaded the plan and heard Wi-Fi networks it was surveyed against.
        The shaded circle shows how unsure the position is. Grey means the position is older than 10 minutes.
      </p>
    </section>
  );
}

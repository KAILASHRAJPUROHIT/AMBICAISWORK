import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {
  listGeofences, createGeofence, deleteGeofence, type Geofence,
} from '../api/geofences';
import { useToast } from '../ui/toast';

/**
 * Circular geofences: draw a center + radius on the map, name it, save. Reuses LocationMap's
 * Leaflet + OpenStreetMap setup (circleMarkers, not markers, to dodge the bundler icon-path
 * issue; a layerGroup cleared/redrawn per render; the invalidateSize() flex-layout fix).
 * Add/delete only — no edit-in-place, matching AlertRulesPanel's convention.
 */
export function GeofencePanel() {
  const toast = useToast();
  const [geofences, setGeofences] = useState<Geofence[] | null>(null);
  const [name, setName] = useState('');
  const [draft, setDraft] = useState<{ lat: number; lon: number; radiusMeters: number } | null>(null);
  const [busy, setBusy] = useState(false);

  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const draftCircleRef = useRef<L.Circle | null>(null);

  async function load() {
    try {
      setGeofences(await listGeofences());
    } catch {
      setGeofences([]);
    }
  }

  useEffect(() => { void load(); }, []);

  // Map setup — once.
  useEffect(() => {
    const el = elRef.current;
    if (!el || mapRef.current) return;
    const map = L.map(el, { worldCopyJump: true }).setView([20, 0], 3);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    // Click to place/move the draft geofence's center; default radius 200m, adjustable below.
    map.on('click', (e: L.LeafletMouseEvent) => {
      setDraft((prev) => ({ lat: e.latlng.lat, lon: e.latlng.lng, radiusMeters: prev?.radiusMeters ?? 200 }));
    });
    mapRef.current = map;
    setTimeout(() => map.invalidateSize(), 0);
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // Redraw saved geofences + the in-progress draft on every change.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();
    (geofences ?? []).forEach((g) => {
      L.circle([g.centerLat, g.centerLon], {
        radius: g.radiusMeters,
        color: g.enabled === false ? '#8993a0' : '#3b82f6',
        fillColor: g.enabled === false ? '#8993a0' : '#3b82f6',
        fillOpacity: 0.15,
        weight: 2,
      })
        .bindPopup(`${g.name} — ${Math.round(g.radiusMeters)} m radius`)
        .addTo(layer);
    });
  }, [geofences]);

  // Draft circle: a separate layer (not cleared by the redraw above) so it survives while typing.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (draftCircleRef.current) {
      map.removeLayer(draftCircleRef.current);
      draftCircleRef.current = null;
    }
    if (draft) {
      draftCircleRef.current = L.circle([draft.lat, draft.lon], {
        radius: draft.radiusMeters,
        color: '#16a34a',
        fillColor: '#16a34a',
        fillOpacity: 0.2,
        weight: 2,
        dashArray: '4 4',
      }).addTo(map);
    }
  }, [draft]);

  async function save() {
    if (!draft) {
      toast.push('err', 'No area drawn', 'Click the map to place a geofence center first.');
      return;
    }
    if (!name.trim()) {
      toast.push('err', 'Name required', '');
      return;
    }
    setBusy(true);
    try {
      await createGeofence({
        name: name.trim(),
        centerLat: draft.lat,
        centerLon: draft.lon,
        radiusMeters: draft.radiusMeters,
      });
      setName('');
      setDraft(null);
      toast.push('ok', 'Geofence added', '');
      await load();
    } catch (e) {
      toast.push('err', 'Failed to add geofence', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  }

  async function remove(id?: number) {
    if (id == null) return;
    setBusy(true);
    try {
      await deleteGeofence(id);
      await load();
    } catch (e) {
      toast.push('err', 'Failed to remove geofence', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Geofences</h2>
      </div>
      <p className="au-note">
        Click the map to place a geofence, adjust its radius, name it, and save. Devices crossing
        the boundary record a check-in event and can notify an admin alert rule.
      </p>

      <div ref={elRef} className="loc-map" style={{ marginBottom: 12 }} />

      {draft && (
        <div className="upd-actions" style={{ marginBottom: 12 }}>
          <input
            type="text" placeholder="Geofence name"
            value={name} onChange={(e) => setName(e.target.value)} disabled={busy}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Radius (m)
            <input
              type="number" min={10} step={10}
              value={draft.radiusMeters}
              onChange={(e) => setDraft({ ...draft, radiusMeters: Number(e.target.value) || 10 })}
              disabled={busy}
              style={{ width: 90 }}
            />
          </label>
          <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void save()}>
            {busy ? 'Saving…' : 'Save geofence'}
          </button>
          <button className="btn btn-sm" disabled={busy} onClick={() => setDraft(null)}>
            Cancel
          </button>
        </div>
      )}

      {geofences && geofences.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Name</th><th>Radius</th><th /></tr>
          </thead>
          <tbody>
            {geofences.map((g) => (
              <tr key={g.id}>
                <td>{g.name}</td>
                <td className="mono">{Math.round(g.radiusMeters)} m</td>
                <td>
                  <button className="btn btn-sm" disabled={busy} onClick={() => void remove(g.id)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {geofences && geofences.length === 0 && !draft && (
        <p className="muted">No geofences configured yet — click the map to add one.</p>
      )}
    </section>
  );
}

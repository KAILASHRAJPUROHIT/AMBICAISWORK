import { useRef, useState } from 'react';
import { searchDevices } from '../api/devices';
import { uploadWallpaper, pushWallpaperToAll, pushKioskAccentToAll, type WallpaperTarget } from '../api/wallpaper';
import { useToast } from '../ui/toast';

async function allDeviceIds(): Promise<number[]> {
  const r = await searchDevices({ pageSize: 1000 });
  return r.devices.items.map((d) => d.id);
}

/** Fleet-wide wallpaper (home/lock screen) and kiosk accent colour push. Settings-page panel,
 *  same visual pattern as the Admin passcode row above it. */
export function WallpaperPanel() {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null);
  const [target, setTarget] = useState<WallpaperTarget>('both');
  const [uploading, setUploading] = useState(false);
  const [pushingWallpaper, setPushingWallpaper] = useState(false);
  const [accent, setAccent] = useState('#7C5CFC');
  const [pushingAccent, setPushingAccent] = useState(false);

  async function onFile(file: File) {
    setUploading(true);
    setFileName(file.name);
    setUploadedUrl(null);
    try {
      const url = await uploadWallpaper(file);
      setUploadedUrl(url);
      toast.push('ok', 'Wallpaper ready', 'Hosted — push it to the fleet below.');
    } catch (e) {
      toast.push('err', 'Upload failed', e instanceof Error ? e.message : '');
      setFileName(null);
    } finally {
      setUploading(false);
    }
  }

  async function pushWallpaper() {
    if (!uploadedUrl) return;
    setPushingWallpaper(true);
    try {
      const ids = await allDeviceIds();
      if (ids.length === 0) { toast.push('err', 'No devices', 'No enrolled devices to push to.'); return; }
      const res = await pushWallpaperToAll(ids, uploadedUrl, target);
      toast.push('ok', 'Wallpaper queued', `${res.queued} device${res.queued === 1 ? '' : 's'}${res.skipped.length ? `, ${res.skipped.length} skipped` : ''}.`);
    } catch (e) {
      toast.push('err', 'Push failed', e instanceof Error ? e.message : '');
    } finally {
      setPushingWallpaper(false);
    }
  }

  async function pushAccent() {
    setPushingAccent(true);
    try {
      const ids = await allDeviceIds();
      if (ids.length === 0) { toast.push('err', 'No devices', 'No enrolled devices to push to.'); return; }
      const res = await pushKioskAccentToAll(ids, accent);
      toast.push('ok', 'Accent colour queued', `${res.queued} device${res.queued === 1 ? '' : 's'} — devices not currently in kiosk mode won't show a visible change until they are.`);
    } catch (e) {
      toast.push('err', 'Push failed', e instanceof Error ? e.message : '');
    } finally {
      setPushingAccent(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2 className="panel-title">Wallpaper &amp; kiosk accent</h2></div>

      <div className="set-row">
        <span className="k">
          Wallpaper
          <small>
            Pushed to every enrolled device's home and/or lock screen. Behind the kiosk launcher
            it's mostly invisible during normal use, but shows during boot, transitions and
            (if allowed) the lock screen.
          </small>
        </span>
        <span className="v wide-actions">
          <div className="upd-actions">
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onFile(f);
                e.target.value = '';
              }}
            />
            <button className="btn btn-sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? 'Uploading…' : fileName ? `✓ ${fileName}` : 'Choose image…'}
            </button>
            <select className="sel" value={target} onChange={(e) => setTarget(e.target.value as WallpaperTarget)}>
              <option value="both">Home + lock screen</option>
              <option value="home">Home screen only</option>
              <option value="lock">Lock screen only</option>
            </select>
            <button
              className="btn btn-sm btn-primary"
              onClick={() => void pushWallpaper()}
              disabled={!uploadedUrl || pushingWallpaper}
            >
              {pushingWallpaper ? 'Pushing…' : 'Push to all devices'}
            </button>
          </div>
        </span>
      </div>

      <div className="set-row">
        <span className="k">
          Kiosk accent colour
          <small>
            Colours the kiosk status bar and exit menu icon on every device currently in kiosk
            mode — applied live, no app re-selection needed.
          </small>
        </span>
        <span className="v wide-actions">
          <div className="upd-actions">
            <input
              type="color"
              value={accent}
              onChange={(e) => setAccent(e.target.value)}
              style={{ width: 48, height: 32, padding: 2 }}
            />
            <input className="input mono" value={accent} onChange={(e) => setAccent(e.target.value)} style={{ width: 110 }} />
            <button className="btn btn-sm btn-primary" onClick={() => void pushAccent()} disabled={pushingAccent}>
              {pushingAccent ? 'Pushing…' : 'Push to all devices'}
            </button>
          </div>
        </span>
      </div>
    </section>
  );
}

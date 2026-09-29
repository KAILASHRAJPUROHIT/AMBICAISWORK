import { useEffect, useRef, useState } from 'react';
import {
  getClientBranding,
  saveClientBranding,
  uploadClientBrandingImage,
  type BrandingSlot,
} from '../api/settings';
import { useToast } from '../ui/toast';

interface SlotState {
  url: string | null;
  uploading: boolean;
}

/**
 * Client branding: the customer's own name and logo, shown on the devices MDMesh manages.
 * AMBIC DIGITAL stays the product brand; this is the client's mark on their hardware.
 *
 * Images are stored by the server and delivered to every device on its next check-in, so a
 * save here takes effect fleet-wide without a per-device push.
 */
export function ClientBrandingPanel() {
  // `useToast()` returns a fresh wrapper object each render, so depend on the stable `push`
  // callback instead - depending on the wrapper would re-run the load effect every render.
  const { push } = useToast();

  const [name, setName] = useState('');
  const [logo, setLogo] = useState<SlotState>({ url: null, uploading: false });
  const [mark, setMark] = useState<SlotState>({ url: null, uploading: false });
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getClientBranding()
      .then((b) => {
        if (cancelled) return;
        setName(b.clientName ?? '');
        setLogo({ url: b.clientLogoUrl, uploading: false });
        setMark({ url: b.clientMarkUrl, uploading: false });
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : 'Could not load current branding.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onPick(file: File | undefined, kind: BrandingSlot) {
    if (!file) return;
    const set = kind === 'logo' ? setLogo : setMark;
    const previous = kind === 'logo' ? logo : mark;
    set({ url: previous.url, uploading: true });
    try {
      const url = await uploadClientBrandingImage(file, kind);
      set({ url, uploading: false });
      push('ok', 'Image uploaded', 'Save branding to publish it to the fleet.');
    } catch (e) {
      set({ url: previous.url, uploading: false });
      push('err', 'Upload failed', e instanceof Error ? e.message : '');
    }
  }

  async function save() {
    setSaving(true);
    try {
      await saveClientBranding({ name: name.trim(), logoUrl: logo.url ?? '', markUrl: mark.url ?? '' });
      push('ok', 'Branding saved', 'Devices pick it up on their next check-in.');
    } catch (e) {
      push('err', 'Save failed', e instanceof Error ? e.message : '');
    } finally {
      setSaving(false);
    }
  }

  const busy = saving || logo.uploading || mark.uploading;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Client branding</h2>
      </div>

      <div className="set-row">
        <span className="k">
          Client name
          <small>
            AMBIC DIGITAL owns this product. The name and logo here are your client's own mark, shown on the kiosk,
            idle screen and agent screen of every managed device. Delivered on the next device check-in.
          </small>
        </span>
        <span className="v wide-actions">
          <input
            id="client-name"
            className="input"
            type="text"
            value={name}
            maxLength={120}
            placeholder="e.g. Aradhana Jewellers"
            aria-label="Client name"
            onChange={(e) => setName(e.target.value)}
          />
        </span>
      </div>

      <ImageRow
        id="client-logo"
        label="Logo (with name)"
        hint="Shown beside the clock on the kiosk home screen and large on the idle screen."
        slot={logo}
        onPick={(f) => void onPick(f, 'logo')}
      />
      <ImageRow
        id="client-mark"
        label="Emblem (no text)"
        hint="Standalone mark for small spaces. Used when there is no full logo."
        slot={mark}
        onPick={(f) => void onPick(f, 'mark')}
      />

      <div className="set-row">
        <span className="k">
          Publish
          {loadError && <small>{loadError} You can still set the fields above and save.</small>}
        </span>
        <span className="v wide-actions">
          <div className="upd-actions">
            <button className="btn btn-sm btn-primary" onClick={() => void save()} disabled={busy}>
              {saving ? 'Saving…' : 'Save branding'}
            </button>
            <button
              className="btn btn-sm"
              onClick={() => {
                setName('');
                setLogo({ url: null, uploading: false });
                setMark({ url: null, uploading: false });
              }}
              disabled={busy}
              title="Empty the form. Press Save branding to remove the branding from devices."
            >
              Clear
            </button>
          </div>
        </span>
      </div>
    </section>
  );
}

function ImageRow({
  id,
  label,
  hint,
  slot,
  onPick,
}: {
  id: string;
  label: string;
  hint: string;
  slot: SlotState;
  onPick: (file: File | undefined) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="set-row">
      <span className="k">
        {label}
        <small>{hint} PNG, up to 4 MB.</small>
      </span>
      <span className="v wide-actions">
        <div className="upd-actions">
          <span className="brand-preview" aria-hidden={!slot.url}>
            {slot.url ? <img src={slot.url} alt={label} /> : <em>No image</em>}
          </span>
          <input
            id={id}
            ref={ref}
            type="file"
            accept="image/png"
            hidden
            onChange={(e) => {
              onPick(e.target.files?.[0]);
              e.target.value = '';
            }}
          />
          <button className="btn btn-sm" onClick={() => ref.current?.click()} disabled={slot.uploading}>
            {slot.uploading ? 'Uploading…' : slot.url ? 'Replace image…' : 'Choose image…'}
          </button>
        </div>
      </span>
    </div>
  );
}

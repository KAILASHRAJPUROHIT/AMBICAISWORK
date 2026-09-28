import { useEffect, useRef, useState } from 'react';
import {
  getClientBranding,
  saveClientBranding,
  uploadClientBrandingImage,
  type BrandingSlot,
} from '../api/settings';
import { useToast } from '../ui/toast';

type SlotState = { fileName: string | null; url: string | null; uploading: boolean };

const blank = (): SlotState => ({ fileName: null, url: null, uploading: false });

/**
 * Client branding — the customer's own name and logo, shown on the devices MDMesh manages.
 * AMBIC DIGITAL stays the product brand; this is the client's mark on their hardware.
 *
 * Images are stored by the server and delivered to every device on its next check-in, so a
 * save here takes effect fleet-wide without a per-device push. Settings-page panel, same
 * visual pattern as the wallpaper and kiosk-accent panel.
 */
export function ClientBrandingPanel() {
  const toast = useToast();
  const logoRef = useRef<HTMLInputElement>(null);
  const markRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState('');
  const [logo, setLogo] = useState<SlotState>(blank());
  const [mark, setMark] = useState<SlotState>(blank());
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const b = await getClientBranding();
        if (cancelled) return;
        setName(b.clientName ?? '');
        setLogo({ fileName: null, url: b.clientLogoUrl, uploading: false });
        setMark({ fileName: null, url: b.clientMarkUrl, uploading: false });
      } catch (e) {
        if (!cancelled) {
          toast.push('err', 'Could not load branding', e instanceof Error ? e.message : '');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [toast]);

  async function onPick(file: File | undefined, kind: BrandingSlot) {
    if (!file) return;
    const set = kind === 'logo' ? setLogo : setMark;
    set({ fileName: file.name, url: null, uploading: true });
    try {
      const url = await uploadClientBrandingImage(file, kind);
      set({ fileName: file.name, url, uploading: false });
      toast.push('ok', 'Image uploaded', 'Save branding to publish it to the fleet.');
    } catch (e) {
      set(blank());
      toast.push('err', 'Upload failed', e instanceof Error ? e.message : '');
    }
  }

  const dirty =
    logo.url !== null || mark.url !== null || logo.fileName !== null || mark.fileName !== null;

  async function save() {
    setSaving(true);
    try {
      await saveClientBranding({
        name: name.trim(),
        logoUrl: logo.url ?? '',
        markUrl: mark.url ?? '',
      });
      toast.push('ok', 'Branding saved', 'Devices pick it up on their next check-in.');
    } catch (e) {
      toast.push('err', 'Save failed', e instanceof Error ? e.message : '');
    } finally {
      setSaving(false);
    }
  }

  function clearAll() {
    setName('');
    setLogo(blank());
    setMark(blank());
  }

  if (loading) return null;

  return (
    <section className="card" aria-labelledby="client-branding-heading">
      <h2 id="client-branding-heading">Client branding</h2>
      <p className="hint">
        AMBIC DIGITAL owns this product. The name and logo below are your client&rsquo;s own
        mark, shown on the kiosk, idle screen and agent screen of every managed device.
        Delivered automatically on the next device check-in.
      </p>

      <label className="field">
        <span>Client name</span>
        <input
          type="text"
          value={name}
          maxLength={120}
          placeholder="e.g. Aradhana Jewellers"
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <div className="branding-slots">
        <BrandingSlot
          label="Logo (with name)"
          hint="Shown beside the clock on the kiosk home screen."
          state={logo}
          inputRef={logoRef}
          onPick={(f) => onPick(f, 'logo')}
        />
        <BrandingSlot
          label="Emblem (no text)"
          hint="Standalone mark for small spaces and the agent screen."
          state={mark}
          inputRef={markRef}
          onPick={(f) => onPick(f, 'mark')}
        />
      </div>

      <div className="row">
        <button type="button" onClick={save} disabled={saving || (logo.uploading || mark.uploading)}>
          {saving ? 'Saving…' : 'Save branding'}
        </button>
        <button type="button" className="secondary" onClick={clearAll} disabled={saving}>
          Clear
        </button>
        {dirty && !saving && <span className="hint">Unsaved changes</span>}
      </div>
    </section>
  );
}

function BrandingSlot({
  label,
  hint,
  state,
  inputRef,
  onPick,
}: {
  label: string;
  hint: string;
  state: SlotState;
  inputRef: React.RefObject<HTMLInputElement>;
  onPick: (file: File | undefined) => void;
}) {
  return (
    <div className="branding-slot">
      <div className="branding-preview">
        {state.url
          ? <img src={`${state.url}?t=${encodeURIComponent(state.url)}`} alt={label} />
          : <span className="hint">No image</span>}
      </div>
      <div className="branding-slot-body">
        <strong>{label}</strong>
        <span className="hint">{hint}</span>
        <input
          ref={inputRef}
          type="file"
          accept="image/png"
          onChange={(e) => onPick(e.target.files?.[0])}
        />
        <span className="hint">
          {state.uploading ? 'Uploading…' : state.fileName ?? 'PNG, up to 4 MB'}
        </span>
      </div>
    </div>
  );
}

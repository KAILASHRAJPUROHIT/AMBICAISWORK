import { useEffect, useState } from 'react';
import { DEFAULT_QUIET_HOURS, getGuardQuietHours, saveGuardQuietHours } from '../api/settings';
import { useToast } from '../ui/toast';

/** "22:00-08:00" -> ["22:00", "08:00"]; anything else -> the defaults. */
function split(v: string): [string, string] {
  const m = /^(\d\d:\d\d)-(\d\d:\d\d)$/.exec(v);
  return m ? [m[1], m[2]] : ['22:00', '08:00'];
}

/**
 * Shop-closed hours for the tablets' offline protection. Normally a tablet with no internet for 10 minutes shows a full-screen
 * "contact administrator" message and after 30 minutes locks down. When the shop switches its router off at night that would
 * lock every tablet by morning, so during these hours a tablet that is sitting still is left alone. A tablet that is being
 * carried away is still protected, and the countdown restarts when the shop opens.
 */
export function GuardHoursPanel() {
  const toast = useToast();
  const [enabled, setEnabled] = useState(true);
  const [from, setFrom] = useState('22:00');
  const [to, setTo] = useState('08:00');
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    getGuardQuietHours().then((v) => {
      if (!live) return;
      setSaved(v);
      setEnabled(v.toLowerCase() !== 'off');
      const [a, b] = split(v.toLowerCase() === 'off' ? DEFAULT_QUIET_HOURS : v);
      setFrom(a); setTo(b);
    }).catch(() => undefined);
    return () => { live = false; };
  }, []);

  const value = enabled ? `${from}-${to}` : 'off';
  const dirty = saved !== null && value !== saved;

  const save = async () => {
    setBusy(true);
    try {
      await saveGuardQuietHours(value);
      setSaved(value);
      toast.push('ok', 'Shop hours saved', 'Tablets pick this up on their next check-in.');
    } catch (e) {
      toast.push('err', 'Could not save the shop hours', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="set-row">
      <span className="k">
        Shop closed hours (offline protection)
        <small>
          While the shop is closed, a tablet that stays put is not blocked or locked for having no internet, so a router switched
          off overnight does not lock the tablets by morning. A tablet that is carried away is still protected.
        </small>
      </span>
      <span className="v wide-actions">
        <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <input id="guard-hours-on" type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Use shop hours
        </label>
        <input id="guard-hours-from" type="time" aria-label="Shop closes at" value={from} disabled={!enabled} onChange={(e) => setFrom(e.target.value)} />
        <span>to</span>
        <input id="guard-hours-to" type="time" aria-label="Shop opens at" value={to} disabled={!enabled} onChange={(e) => setTo(e.target.value)} />
        <button className="btn btn-sm btn-primary" disabled={!dirty || busy || (enabled && (!from || !to))} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </span>
    </div>
  );
}

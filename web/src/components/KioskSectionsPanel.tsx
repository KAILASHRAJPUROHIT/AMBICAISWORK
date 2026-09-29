import { useEffect, useState } from 'react';
import {
  getKioskSections,
  saveKioskSections,
  KIOSK_SECTIONS,
  type KioskSectionKey,
  type KioskSectionMap,
} from '../api/settings';
import { forceSync } from '../api/commands';
import { useDevices } from '../data/useDevices';
import { useToast } from '../ui/toast';

const allOn = (): KioskSectionMap =>
  Object.fromEntries(KIOSK_SECTIONS.map((s) => [s.key, true])) as KioskSectionMap;

/**
 * Switch tablet sections on and off for the whole fleet. A section that is off disappears from every
 * managed tablet: the kiosk redraws as soon as the tablet checks in, and this panel asks every
 * device to check in straight away, so it normally takes a few seconds.
 *
 * The admin menu button is intentionally not listed: it can never be hidden.
 */
export function KioskSectionsPanel() {
  const { push } = useToast();
  const { devices } = useDevices();
  const [sections, setSections] = useState<KioskSectionMap>(allOn());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<KioskSectionKey | null>(null);

  useEffect(() => {
    let cancelled = false;
    getKioskSections()
      .then((s) => !cancelled && setSections(s))
      .catch((e) => !cancelled && setLoadError(e instanceof Error ? e.message : 'Could not load the current switches.'));
    return () => {
      cancelled = true;
    };
  }, []);

  async function set(key: KioskSectionKey, on: boolean) {
    if (sections[key] === on || busy) return;
    const next = { ...sections, [key]: on };
    setSections(next); // optimistic
    setBusy(key);
    try {
      await saveKioskSections(next);
      // Ask every tablet to check in now so the change shows up within seconds, not at the next wake-up.
      const results = await Promise.allSettled(devices.map((d) => forceSync(d.number)));
      const reached = results.filter((r) => r.status === 'fulfilled').length;
      const label = KIOSK_SECTIONS.find((s) => s.key === key)?.label ?? key;
      push(
        'ok',
        `${label} ${on ? 'shown' : 'hidden'}`,
        devices.length ? `Asked ${reached} of ${devices.length} tablets to update now.` : 'Tablets update on their next check-in.',
      );
    } catch (e) {
      setSections(sections); // roll back
      push('err', 'Could not save', e instanceof Error ? e.message : '');
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Kiosk sections</h2>
      </div>
      {loadError && (
        <div className="set-row">
          <span className="k">
            Current switches
            <small>{loadError} Everything is shown until this loads.</small>
          </span>
        </div>
      )}
      {KIOSK_SECTIONS.map((s) => (
        <div className="set-row" key={s.key}>
          <span className="k">
            {s.label}
            <small>{s.hint}</small>
          </span>
          <span className="v">
            <span className="seg" role="group" aria-label={s.label}>
              <button className={sections[s.key] ? 'on' : ''} disabled={busy !== null} onClick={() => void set(s.key, true)}>
                On
              </button>
              <button className={!sections[s.key] ? 'on' : ''} disabled={busy !== null} onClick={() => void set(s.key, false)}>
                Off
              </button>
            </span>
          </span>
        </div>
      ))}
      <div className="set-row">
        <span className="k">
          Always available
          <small>The admin menu button (passcode protected) is never hidden, so you can always reach the tablet's settings.</small>
        </span>
      </div>
    </section>
  );
}

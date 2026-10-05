import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fmtRelative, orDash } from '../ui/format';
import { getWindowsStatus, listWindowsPcs, windowsName, windowsState, type WindowsPc } from '../api/windows';

/** Windows PCs, listed beside the tablets. Hidden entirely when the Windows service is not set up. */
export function WindowsSection({ query }: { query: string }) {
  const navigate = useNavigate();
  const [pcs, setPcs] = useState<WindowsPc[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const s = await getWindowsStatus();
        if (!s.configured) {
          if (alive) setPcs(null);
          return;
        }
        const r = await listWindowsPcs();
        if (alive) {
          setPcs(r.devices);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Could not load Windows PCs');
      }
    };
    void load();
    const t = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (pcs === null && !error) return null;
  const q = query.trim().toLowerCase();
  const shown = (pcs ?? []).filter(
    (d) => !q || `${d.hostname} ${d.nickname} ${d.ip} ${d.loggedInUser}`.toLowerCase().includes(q),
  );

  return (
    <section className="panel win-section" aria-label="Windows PCs">
      <div className="dv-head">
        <h2>Windows PCs</h2>
        <span className="dv-count">
          {shown.length} total · {shown.filter((d) => d.online).length} online
        </span>
      </div>
      {error ? (
        <div className="empty">
          <span className="label">Windows service</span>
          {error}
        </div>
      ) : shown.length === 0 ? (
        <div className="empty">
          <span className="label">No Windows PCs</span>
          None match.
        </div>
      ) : (
        <div className="win-list">
          {shown.map((d) => {
            const st = windowsState(d);
            return (
              <button
                key={d.id}
                type="button"
                className="win-row"
                onClick={() => navigate(`/windows/${encodeURIComponent(d.id)}`)}
              >
                <span className={`win-dot ${st.tone}`} aria-hidden="true" />
                <span className="win-main">
                  <strong>{windowsName(d)}</strong>
                  <span className="muted">
                    {orDash(d.osDescription)} · {orDash(d.model)} · {orDash(d.loggedInUser)}
                  </span>
                </span>
                <span className={`win-badge ${st.tone}`}>{st.label}</span>
                <span className="muted win-seen">{fmtRelative(d.lastContact)}</span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

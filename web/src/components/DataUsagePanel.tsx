import { useEffect, useState } from 'react';
import { listDataUsage, type DataUsageSnapshot } from '../api/deviceDataUsage';
import { fmtBytes, fmtRelative, fmtDateTime } from '../ui/format';

export function DataUsagePanel({ device }: { device: { number: string } }) {
  const [snapshots, setSnapshots] = useState<DataUsageSnapshot[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setErr(null);
    try {
      setSnapshots(await listDataUsage(device.number));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load data usage');
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [device.number]);

  const latest = snapshots?.[0];

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Data usage</h2>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {snapshots && snapshots.length > 0 && (
            <span className="muted">latest {fmtRelative(latest?.capturedAt)}</span>
          )}
          <button className="btn" onClick={() => void load()}>Refresh</button>
        </div>
      </div>
      {err && <p className="err-text">{err}</p>}
      {!snapshots && !err && <p className="muted">Loading data usage…</p>}
      {snapshots && snapshots.length === 0 && (
        <p className="muted">No data usage reported yet — requires Usage Access enabled on the device.</p>
      )}
      {latest && (
        <dl className="state-grid">
          <div><dt>Mobile (today)</dt><dd>{fmtBytes(latest.mobileRxBytes + latest.mobileTxBytes)}</dd></div>
          <div><dt>Wi-Fi (today)</dt><dd>{fmtBytes(latest.wifiRxBytes + latest.wifiTxBytes)}</dd></div>
        </dl>
      )}
      {snapshots && snapshots.length > 1 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Captured</th><th>Mobile</th><th>Wi-Fi</th>
            </tr>
          </thead>
          <tbody>
            {snapshots.slice(0, 20).map((s) => (
              <tr key={s.id ?? s.capturedAt}>
                <td>{fmtDateTime(s.capturedAt)}</td>
                <td>{fmtBytes(s.mobileRxBytes + s.mobileTxBytes)}</td>
                <td>{fmtBytes(s.wifiRxBytes + s.wifiTxBytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

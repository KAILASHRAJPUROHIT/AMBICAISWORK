import { AppShell } from '../ui/AppShell';
import { useDevices } from '../data/useDevices';
import { AppTimeReport } from '../components/AppTimeReport';

export function ReportsPage() {
  const { devices } = useDevices();
  return (
    <AppShell title="Reports">
      <div className="page-head">
        <div>
          <p className="ais-eyebrow">REPORTS</p>
          <h1>App time</h1>
          <p className="page-sub">How long each app was on screen, per tablet — from the agents' low-power usage log.</p>
        </div>
      </div>
      <section className="panel atr-panel">
        <AppTimeReport devices={devices} />
      </section>
    </AppShell>
  );
}

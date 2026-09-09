import { useEffect, useState } from 'react';
import {
  listAlertRules, createAlertRule, deleteAlertRule, type AlertRule,
} from '../api/alertRules';
import { EVENT_VERBS } from '../pages/DashboardPage';
import { useToast } from '../ui/toast';

/** Customer-scoped webhook/email admin-alert rules: notify a URL and/or an inbox whenever a
 *  matching device event fires (e.g. "lowBattery", or blank for any event). */
export function AlertRulesPanel() {
  const toast = useToast();
  const [rules, setRules] = useState<AlertRule[] | null>(null);
  const [eventType, setEventType] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setRules(await listAlertRules());
    } catch {
      setRules([]);
    }
  }

  useEffect(() => { void load(); }, []);

  async function add() {
    if (!webhookUrl.trim() && !email.trim()) {
      toast.push('err', 'Nothing to notify', 'Enter a webhook URL and/or an email address.');
      return;
    }
    setBusy(true);
    try {
      await createAlertRule({
        eventType: eventType || undefined,
        webhookUrl: webhookUrl.trim() || undefined,
        email: email.trim() || undefined,
      });
      setEventType(''); setWebhookUrl(''); setEmail('');
      toast.push('ok', 'Alert rule added', '');
      await load();
    } catch (e) {
      toast.push('err', 'Failed to add rule', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  }

  async function remove(id?: number) {
    if (id == null) return;
    setBusy(true);
    try {
      await deleteAlertRule(id);
      await load();
    } catch (e) {
      toast.push('err', 'Failed to remove rule', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Admin alerts</h2>
      </div>
      <p className="au-note">
        Notify a webhook and/or an email address whenever a matching device event fires.
        Leave "Event" blank to match every event type.
      </p>

      {rules && rules.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Event</th><th>Webhook</th><th>Email</th><th /></tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id}>
                <td>{r.eventType ? (EVENT_VERBS[r.eventType] ?? r.eventType) : 'Any event'}</td>
                <td className="mono">{r.webhookUrl || '—'}</td>
                <td className="mono">{r.email || '—'}</td>
                <td>
                  <button className="btn btn-sm" disabled={busy} onClick={() => void remove(r.id)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rules && rules.length === 0 && <p className="muted">No alert rules configured yet.</p>}

      <div className="upd-actions" style={{ marginTop: 12 }}>
        <select value={eventType} onChange={(e) => setEventType(e.target.value)} disabled={busy}>
          <option value="">Any event</option>
          {Object.entries(EVENT_VERBS).map(([key, label]) => (
            <option key={key} value={key}>{label} ({key})</option>
          ))}
        </select>
        <input
          type="text" placeholder="Webhook URL"
          value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} disabled={busy}
        />
        <input
          type="email" placeholder="Email address"
          value={email} onChange={(e) => setEmail(e.target.value)} disabled={busy}
        />
        <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void add()}>
          {busy ? 'Adding…' : 'Add rule'}
        </button>
      </div>
    </section>
  );
}

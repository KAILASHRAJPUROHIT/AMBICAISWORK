import { useEffect, useState } from 'react';
import { clearSmtp, getSmtp, saveSmtp, testSmtp, type SmtpSecurity, type SmtpView } from '../api/smtp';
import { fmtRelative } from '../ui/format';

const PRESETS: { label: string; host: string; port: number; security: SmtpSecurity; hint: string }[] = [
  { label: 'Gmail', host: 'smtp.gmail.com', port: 587, security: 'starttls', hint: 'Use the full Gmail address as the user name and a Google "app password" (not the normal password).' },
  { label: 'Amazon SES (Mumbai)', host: 'email-smtp.ap-south-1.amazonaws.com', port: 587, security: 'starttls', hint: 'Use the SES SMTP user name and password, and a sender address verified in SES.' },
];

const ERRORS: Record<string, string> = {
  'error.smtp.host.invalid': 'Enter the mail server address (no spaces).',
  'error.smtp.port.invalid': 'The port must be between 1 and 65535.',
  'error.smtp.security.invalid': 'Choose how the connection is secured.',
  'error.smtp.from.invalid': 'The "from" address is not a valid email address.',
  'error.smtp.save.failed': 'The settings could not be saved on the server.',
};

/**
 * Outgoing email for the sign-in and tablet-unlock codes. The sign-in "allowed computers" check only works while the server can
 * send email, so it is configured here and tested here. The password is write-only.
 */
export function SmtpPanel() {
  const [view, setView] = useState<SmtpView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [host, setHost] = useState('');
  const [port, setPort] = useState(587);
  const [security, setSecurity] = useState<SmtpSecurity>('starttls');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fromAddress, setFromAddress] = useState('');
  const [busy, setBusy] = useState<'save' | 'test' | 'clear' | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const apply = (v: SmtpView) => {
    setView(v);
    if (v.host) {
      setHost(v.host); setPort(v.port ?? 587); setSecurity(v.security ?? 'starttls');
      setUsername(v.username ?? ''); setFromAddress(v.fromAddress ?? '');
    }
  };

  useEffect(() => {
    getSmtp().then(apply).catch((e) => setError(e instanceof Error ? e.message : 'Unavailable'));
  }, []);

  const problem = (e: unknown) => (e instanceof Error ? ERRORS[e.message] ?? e.message : 'Failed');

  async function save() {
    setBusy('save'); setNote(null);
    try {
      apply(await saveSmtp({ host, port, security, username, password, fromAddress }));
      setPassword('');
      setNote({ ok: true, text: 'Saved. Use "Send test email" to check it.' });
    } catch (e) {
      setNote({ ok: false, text: problem(e) });
    } finally {
      setBusy(null);
    }
  }

  async function test() {
    setBusy('test'); setNote(null);
    try {
      const r = await testSmtp();
      setNote({ ok: r.ok, text: r.ok ? `Test email sent to ${r.sentTo}. Check that inbox.` : `Could not send: ${r.message}` });
    } catch (e) {
      setNote({ ok: false, text: problem(e) });
    } finally {
      setBusy(null);
    }
  }

  async function clear() {
    if (!window.confirm('Remove the email settings saved here? The server\'s own settings (if any) apply again.')) return;
    setBusy('clear'); setNote(null);
    try {
      apply(await clearSmtp());
      setHost(''); setUsername(''); setFromAddress(''); setPassword('');
    } catch (e) {
      setNote({ ok: false, text: problem(e) });
    } finally {
      setBusy(null);
    }
  }

  const status = !view ? null
    : view.configured
      ? { ok: true, text: `Email is set up (${view.source === 'console' ? 'saved here' : 'from the server settings'}). Codes go to ${view.recipient}.` }
      : { ok: false, text: 'Email is NOT set up, so new computers are not asked for a sign-in code and locked tablets cannot be unlocked by code.' };

  return (
    <div className="set-row" style={{ alignItems: 'flex-start' }}>
      <span className="k">
        Outgoing email
        <small>Needed to send the sign-in code for new computers and the tablet unlock code to {view?.recipient || 'the owner'}.</small>
        {status && (
          <small style={{ color: status.ok ? 'var(--ok, #22c55e)' : 'var(--warn, #f59e0b)', fontWeight: 600 }}>{status.text}</small>
        )}
      </span>
      <span className="v" style={{ display: 'grid', gap: 8, justifyItems: 'stretch', minWidth: 300, maxWidth: 440 }}>
        {error && <span className="muted">{error}</span>}
        <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {PRESETS.map((p) => (
            <button key={p.label} className="btn btn-sm" onClick={() => { setHost(p.host); setPort(p.port); setSecurity(p.security); setNote({ ok: true, text: p.hint }); }}>
              {p.label}
            </button>
          ))}
        </span>
        <input className="input" placeholder="Mail server, e.g. smtp.gmail.com" value={host} onChange={(e) => setHost(e.target.value)} aria-label="Mail server" />
        <span style={{ display: 'flex', gap: 8 }}>
          <input className="input" type="number" min={1} max={65535} value={port} onChange={(e) => setPort(Number(e.target.value))} aria-label="Port" style={{ width: 90 }} />
          <select value={security} onChange={(e) => setSecurity(e.target.value as SmtpSecurity)} aria-label="Connection security" style={{ flex: 1, padding: '6px 10px', borderRadius: 6 }}>
            <option value="starttls">STARTTLS (port 587)</option>
            <option value="ssl">SSL/TLS (port 465)</option>
            <option value="none">None (port 25, not recommended)</option>
          </select>
        </span>
        <input className="input" placeholder="User name" autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} aria-label="User name" />
        <input
          className="input" type="password" autoComplete="new-password"
          placeholder={view?.hasPassword ? 'Password saved (type to change)' : 'Password'}
          value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Password"
        />
        <input className="input" placeholder="Send from (optional, defaults to the user name)" value={fromAddress} onChange={(e) => setFromAddress(e.target.value)} aria-label="Send from address" />
        <span style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-sm btn-primary" disabled={busy !== null || !host.trim()} onClick={() => void save()}>{busy === 'save' ? 'Saving…' : 'Save'}</button>
          <button className="btn btn-sm" disabled={busy !== null || !view?.configured} onClick={() => void test()}>{busy === 'test' ? 'Sending…' : 'Send test email'}</button>
          {view?.source === 'console' && <button className="btn btn-sm" disabled={busy !== null} onClick={() => void clear()}>Remove</button>}
        </span>
        {note && <span style={{ color: note.ok ? 'var(--ok, #22c55e)' : 'var(--bad, #ef4444)', fontSize: 13 }}>{note.text}</span>}
        {view?.updatedAt ? <small className="muted">Last saved {fmtRelative(view.updatedAt)}{view.updatedBy ? ` by ${view.updatedBy}` : ''}</small> : null}
      </span>
    </div>
  );
}

import { useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../api/client';
import { isOtpChallenge } from '../api/auth';
import { Wordmark } from '../ui/Wordmark';

export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { from?: string; passwordChanged?: boolean } | null;
  const from = state?.from ?? '/dashboard';

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Set when this computer is new: the code was emailed to this (partly hidden) address. */
  const [otpSentTo, setOtpSentTo] = useState<string | null>(null);
  const [otp, setOtp] = useState('');

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const u = await signIn(username, password, otpSentTo ? otp : undefined);
      if (isOtpChallenge(u)) {
        setOtpSentTo(u.sentTo);
        setOtp('');
        return;
      }
      // First-login: the seeded admin must set its own password before reaching the console.
      navigate(u.passwordReset ? '/set-password' : from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.httpStatus === 0) {
        setError('Cannot reach the server. Check that it is running.');
      } else if (err instanceof ApiError && err.message === 'error.otp.invalid') {
        setError('That code is wrong or has expired. Check the latest email, or go back and ask for a new one.');
      } else if (err instanceof ApiError && err.message === 'error.otp.rate.limited') {
        setError('Too many codes were requested. Wait an hour, or ask an administrator to add this computer.');
      } else if (err instanceof ApiError && err.message === 'error.otp.mail.failed') {
        setError('The sign-in code could not be emailed. Check the server email settings.');
      } else if (err instanceof ApiError && err.message === 'error.device.fingerprint.missing') {
        setError('This browser could not identify the computer. Use a current Chrome or Edge over HTTPS.');
      } else {
        setError('Wrong login or password');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card route-enter" onSubmit={onSubmit}>
        <Wordmark />
        <div className="login-head">
          <h1>Sign in to AMBIC Digital MDM</h1>
          <p>Device fleet command console.</p>
        </div>

        {otpSentTo ? (
          <>
            <div className="login-ok">
              This computer is new. A 6-digit code was emailed to {otpSentTo}. Enter it to sign in; the computer is then remembered.
            </div>
            <label className="field">
              <span className="label">Sign-in code</span>
              <input
                className="input"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                required
                autoFocus
              />
            </label>
            <button type="button" className="btn btn-sm" onClick={() => { setOtpSentTo(null); setOtp(''); setError(null); }}>
              Start again
            </button>
          </>
        ) : (
        <>
        <label className="field">
          <span className="label">Login</span>
          <input
            className="input"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </label>

        <label className="field">
          <span className="label">Password</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        </>
        )}

        {state?.passwordChanged && !error && (
          <div className="login-ok">Password updated — sign in with your new password.</div>
        )}
        {error && <div className="login-err">{error}</div>}

        <button
          className="btn btn-primary btn-block"
          type="submit"
          disabled={busy}
        >
          {busy ? 'Signing in…' : otpSentTo ? 'Verify code' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}

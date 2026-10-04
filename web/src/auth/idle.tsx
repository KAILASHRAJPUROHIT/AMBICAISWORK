import { useEffect, useRef, useState } from 'react';

/**
 * Automatic sign-out after a period with no mouse, keyboard, touch or scroll activity.
 * The default is 30 seconds (the owner's rule); Settings > Security can change it for this browser.
 * Activity is also stamped in localStorage, so reopening or reloading a console tab that was left idle
 * longer than the limit signs out straight away instead of resuming the session.
 */
const IDLE_KEY = 'hmdm.admin.idleSeconds';
const ACTIVE_KEY = 'hmdm.admin.lastActive';
export const DEFAULT_IDLE_SECONDS = 30;
export const MIN_IDLE_SECONDS = 15;
export const MAX_IDLE_SECONDS = 3600;
/** The warning appears this many seconds before the sign-out. */
const WARN_SECONDS = 10;

export function getIdleSeconds(): number {
  try {
    const n = Number(localStorage.getItem(IDLE_KEY));
    if (Number.isFinite(n) && n >= MIN_IDLE_SECONDS && n <= MAX_IDLE_SECONDS) return Math.round(n);
  } catch { /* storage unavailable */ }
  return DEFAULT_IDLE_SECONDS;
}

export function setIdleSeconds(seconds: number): number {
  const v = Math.min(MAX_IDLE_SECONDS, Math.max(MIN_IDLE_SECONDS, Math.round(seconds) || DEFAULT_IDLE_SECONDS));
  try { localStorage.setItem(IDLE_KEY, String(v)); } catch { /* storage unavailable */ }
  return v;
}

function stampActive(now: number) {
  try { localStorage.setItem(ACTIVE_KEY, String(now)); } catch { /* storage unavailable */ }
}
function lastStamp(): number {
  try { return Number(localStorage.getItem(ACTIVE_KEY)) || 0; } catch { return 0; }
}

const EVENTS = ['pointerdown', 'pointermove', 'mousedown', 'keydown', 'wheel', 'touchstart', 'scroll'] as const;

/** Runs while `active`. Calls `onTimeout` once when the limit passes; returns the seconds left once the warning is due, else null. */
export function useIdleLogout(active: boolean, onTimeout: () => void): number | null {
  const [left, setLeft] = useState<number | null>(null);
  const last = useRef(Date.now());
  const cb = useRef(onTimeout);
  cb.current = onTimeout;
  // Only a session RESTORED on page load can be stale; a fresh sign-in must never be judged by an old stamp.
  const firstRun = useRef(true);

  useEffect(() => {
    const restored = firstRun.current;
    firstRun.current = false;
    if (!active) { setLeft(null); return; }
    const limitMs = () => getIdleSeconds() * 1000;
    // A tab that was idle past the limit (closed, asleep, left on another screen) does not resume.
    const stamp = lastStamp();
    last.current = Date.now();
    if (restored && stamp && Date.now() - stamp >= limitMs()) { cb.current(); return; }

    let lastWrite = 0;
    const onActivity = () => {
      const now = Date.now();
      last.current = now;
      if (now - lastWrite > 1000) { lastWrite = now; stampActive(now); }
    };
    stampActive(Date.now());
    EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true, capture: true }));

    // A 1-second poll against wall-clock time: browsers slow background timers, so a single long setTimeout could fire late.
    const timer = setInterval(() => {
      const idleMs = Date.now() - Math.max(last.current, lastStamp());
      const remaining = Math.ceil((limitMs() - idleMs) / 1000);
      if (remaining <= 0) { setLeft(null); clearInterval(timer); cb.current(); }
      else setLeft(remaining <= WARN_SECONDS ? remaining : null);
    }, 1000);

    return () => {
      EVENTS.forEach((e) => window.removeEventListener(e, onActivity, { capture: true }));
      clearInterval(timer);
    };
  }, [active]);

  return left;
}

export function IdleWarning({ seconds }: { seconds: number }) {
  return (
    <div
      role="alert"
      style={{
        position: 'fixed', left: '50%', bottom: 24, transform: 'translateX(-50%)', zIndex: 10000,
        padding: '12px 18px', borderRadius: 10, background: '#111827', color: '#fff',
        boxShadow: '0 8px 30px rgba(0,0,0,0.35)', fontWeight: 600,
      }}
    >
      Signing out in {seconds}s because of inactivity. Move the mouse or press a key to stay signed in.
    </div>
  );
}

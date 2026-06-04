import { useEffect, useRef } from 'react';

const TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes
const WARNING_MS = 14 * 60 * 1000; // Warn after 14 minutes

export function useSessionTimeout(user: any, logout: () => void) {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warningRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!user) return;

    const resetTimers = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (warningRef.current) clearTimeout(warningRef.current);

      warningRef.current = setTimeout(() => {
        alert("Your session will expire in 1 minute due to inactivity.");
      }, WARNING_MS);

      timeoutRef.current = setTimeout(() => {
        alert("Session expired due to inactivity.");
        logout();
      }, TIMEOUT_MS);
    };

    const events = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart'];
    events.forEach(event => document.addEventListener(event, resetTimers));

    resetTimers();

    return () => {
      events.forEach(event => document.removeEventListener(event, resetTimers));
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (warningRef.current) clearTimeout(warningRef.current);
    };
  }, [user, logout]);
}

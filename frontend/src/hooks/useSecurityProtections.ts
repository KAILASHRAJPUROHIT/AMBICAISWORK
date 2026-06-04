import { useEffect } from 'react';
import { getHeaders } from '../api/client';

export function useSecurityProtections(user: any) {
  useEffect(() => {
    if (!user) return;

    // 1. Disable Right Click
    const handleContextMenu = (e: MouseEvent) => {
      e.preventDefault();
    };

    // 2. Block Shortcuts (Ctrl+P, Ctrl+S, PrintScreen)
    const handleKeyDown = async (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
      const cmdOrCtrl = isMac ? e.metaKey : e.ctrlKey;
      
      let attemptType = '';

      if (e.key === 'PrintScreen' || (cmdOrCtrl && e.shiftKey && (e.key === 'S' || e.key === 's' || e.key === '3' || e.key === '4'))) {
        attemptType = 'SCREEN_CAPTURE_ATTEMPT';
        e.preventDefault();
      } else if (cmdOrCtrl && (e.key === 'p' || e.key === 'P')) {
        attemptType = 'PRINT_ATTEMPT';
        e.preventDefault();
      } else if (cmdOrCtrl && (e.key === 's' || e.key === 'S')) {
        attemptType = 'EXPORT_ATTEMPT';
        e.preventDefault();
      }

      if (attemptType) {
        // Log to backend
        try {
          await fetch(`${window.location.origin}/api/audit/security-violation`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ type: attemptType })
          });
        } catch (error) {
           console.error("Failed to log security violation", error);
        }
      }
    };

    // 3. Visibility Blur (when window loses focus)
    const handleVisibilityChange = () => {
      if (document.hidden) {
        document.body.classList.add('blur-sm', 'grayscale', 'opacity-50');
      } else {
        document.body.classList.remove('blur-sm', 'grayscale', 'opacity-50');
      }
    };

    const handleBlur = () => {
        document.body.classList.add('blur-sm', 'grayscale', 'opacity-50');
    };

    const handleFocus = () => {
        document.body.classList.remove('blur-sm', 'grayscale', 'opacity-50');
    };

    document.addEventListener('contextmenu', handleContextMenu);
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);
    window.addEventListener('focus', handleFocus);

    // 4. Add Watermark
    const watermarkId = 'security-watermark';
    let watermark = document.getElementById(watermarkId);
    if (!watermark) {
      watermark = document.createElement('div');
      watermark.id = watermarkId;
      watermark.className = 'fixed inset-0 pointer-events-none z-[9999] opacity-5 flex flex-wrap items-center justify-center overflow-hidden';
      
      const text = `${user.name} | ${user.employee_id} | ${new Date().toISOString().split('T')[0]}`;
      const html = Array(50).fill(`<span class="m-8 transform -rotate-45 text-xl font-black">${text}</span>`).join('');
      watermark.innerHTML = html;
      document.body.appendChild(watermark);
    }

    return () => {
      document.removeEventListener('contextmenu', handleContextMenu);
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
      window.removeEventListener('focus', handleFocus);
      if (watermark) watermark.remove();
      document.body.classList.remove('blur-sm', 'grayscale', 'opacity-50');
    };
  }, [user]);
}

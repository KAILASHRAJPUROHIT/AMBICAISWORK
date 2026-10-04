/**
 * A stable fingerprint of THIS computer and browser, used for the console's allowed-computers list.
 * Browsers do not expose a hardware serial number, so it is built from what they do expose about the machine
 * (CPU threads, memory, screen, graphics card, time zone, canvas rendering) plus a random id kept in this browser.
 * Only a hash leaves the browser, and the server stores a hash of that.
 */
const ID_KEY = 'hmdm.device.id';

function localId(): string {
  try {
    let id = localStorage.getItem(ID_KEY);
    if (!id) {
      const b = crypto.getRandomValues(new Uint8Array(16));
      id = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
      localStorage.setItem(ID_KEY, id);
    }
    return id;
  } catch {
    return 'no-storage';
  }
}

function graphics(): string {
  try {
    const c = document.createElement('canvas');
    const gl = (c.getContext('webgl') || c.getContext('experimental-webgl')) as WebGLRenderingContext | null;
    if (!gl) return 'no-webgl';
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    return ext ? `${gl.getParameter(ext.UNMASKED_VENDOR_WEBGL)}|${gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)}` : String(gl.getParameter(gl.RENDERER));
  } catch {
    return 'webgl-error';
  }
}

function canvasTrait(): string {
  try {
    const c = document.createElement('canvas');
    c.width = 220; c.height = 40;
    const g = c.getContext('2d');
    if (!g) return 'no-canvas';
    g.textBaseline = 'top';
    g.font = '16px Arial';
    g.fillStyle = '#f60';
    g.fillRect(2, 2, 90, 24);
    g.fillStyle = '#069';
    g.fillText('AMBIC MDM \u2713 fingerprint', 4, 8);
    return c.toDataURL().slice(-80);
  } catch {
    return 'canvas-error';
  }
}

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (x) => x.toString(16).padStart(2, '0')).join('');
}

export async function deviceFingerprint(): Promise<string> {
  const n = navigator as Navigator & { deviceMemory?: number };
  const traits = [
    n.platform, String(n.hardwareConcurrency ?? ''), String(n.deviceMemory ?? ''), String(n.maxTouchPoints ?? ''),
    `${screen.width}x${screen.height}x${screen.colorDepth}`, Intl.DateTimeFormat().resolvedOptions().timeZone,
    graphics(), canvasTrait(), localId(),
  ].join('||');
  return sha256Hex(traits);
}

/** A readable name for the list in Settings, e.g. "Windows · Chrome". */
export function deviceLabel(): string {
  const ua = navigator.userAgent;
  const os = /Windows/.test(ua) ? 'Windows' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : 'Computer';
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
  return `${os} · ${browser}`;
}

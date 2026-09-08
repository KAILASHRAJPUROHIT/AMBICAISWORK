// expo/fetch supports streaming response bodies, required for SSE in RN
import { fetch as streamFetch } from 'expo/fetch';

const BASE = 'https://aradhana-gold-monitor.onrender.com';

export type GoldVariant = {
  key: string;
  label: string;
  purityFactor: number;
  rate: number;
  rateExact: number;
  rateWithGst?: number;
};

export type PublishedGold = {
  rate22kt: number;
  rate24kt: number;
  unit: string;
  label: string;
  atIst: string;
  high: number;
  low: number;
  status: string;
  confidence: number;
  variants?: GoldVariant[];
};

export type PublishedSilver = {
  pure: number;
  pureLabel: string;
  ornament: number;
  ornamentLabel: string;
  unit: string;
  atIst: string;
  status: string;
  confidence: number;
};

export type RateSnapshot = {
  ok: boolean;
  published: PublishedGold;
  silver?: { published?: PublishedSilver };
};

export async function fetchRateSnapshot(): Promise<RateSnapshot> {
  const res = await fetch(`${BASE}/api/rate`);
  if (!res.ok) throw new Error(`Rate server responded ${res.status}`);
  const json = (await res.json()) as RateSnapshot;
  if (!json.ok || !json.published) throw new Error('Rate payload unavailable');
  return json;
}

export function find18kt(snap: RateSnapshot): GoldVariant | undefined {
  return snap.published.variants?.find((v) => v.key === '18kt');
}

/**
 * Subscribe to the monitor's per-second SSE feed (/api/stream).
 * Returns an unsubscribe function. Auto-reconnects with backoff;
 * falls back to 1s polling of /api/rate while the stream is down.
 */
export function subscribeRates(handlers: {
  onData: (snap: RateSnapshot) => void;
  onStatus?: (connected: boolean) => void;
}): () => void {
  let disposed = false;
  let controller: AbortController | null = null;
  let retry = 0;
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  const startPolling = () => {
    if (pollTimer || disposed) return;
    handlers.onStatus?.(false);
    pollTimer = setInterval(async () => {
      try {
        const snap = await fetchRateSnapshot();
        if (!disposed) handlers.onData(snap);
      } catch {
        // keep polling silently
      }
    }, 1000);
  };

  const stopPolling = () => {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  const connect = async () => {
    while (!disposed) {
      controller = new AbortController();
      try {
        const res = await streamFetch(`${BASE}/api/stream`, {
          headers: { Accept: 'text/event-stream' },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        stopPolling();
        handlers.onStatus?.(true);
        retry = 0;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { done, value } = await reader.read();
          if (done || disposed) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() ?? '';
          for (const block of blocks) {
            const data = block
              .split('\n')
              .filter((l) => l.startsWith('data:'))
              .map((l) => l.slice(5).trim())
              .join('');
            if (!data) continue;
            try {
              const snap = JSON.parse(data) as RateSnapshot;
              if (!disposed && snap?.published) handlers.onData(snap);
            } catch {
              // ignore malformed frame
            }
          }
        }
        throw new Error('stream ended');
      } catch {
        if (disposed) return;
        handlers.onStatus?.(false);
        startPolling();
        await new Promise((r) => setTimeout(r, 500 * Math.pow(2, Math.min(retry++, 6))));
      }
    }
  };

  void connect();

  return () => {
    disposed = true;
    controller?.abort();
    stopPolling();
  };
}

export function formatInr(n: number): string {
  const hasFraction = Math.abs(n % 1) > 1e-9;
  return n.toLocaleString('en-IN', {
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: hasFraction ? 2 : 0,
  });
}

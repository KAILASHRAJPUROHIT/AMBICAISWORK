import { useEffect, useState } from 'react';

import { subscribeRates, type RateSnapshot } from '@/services/rates';

/** Shared per-second live rate subscription for UI cards. */
export function useLiveRates() {
  const [snap, setSnap] = useState<RateSnapshot | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribeRates({
      onData: setSnap,
      onStatus: setConnected,
    });
    return unsubscribe;
  }, []);

  return { snap, connected };
}

import { useEffect, useRef, useState } from 'react';
import { liveStreamUrl } from '../api/remoteView';

/** Packet header: type(1) | ptsUs(8) | length(4). Types: 1 config (JSON), 5 PCM (16-bit little-endian mono). */
const HEADER = 13;
/** Audio is scheduled this far ahead of "now": enough to ride out network jitter, small enough to feel live. */
const JITTER_S = 0.18;
/** If playback ever falls this far behind real time, old audio is skipped rather than played late. */
const MAX_LAG_S = 0.7;

/**
 * Live microphone of the tablet, played as it arrives (Web Audio). Nothing is recorded or saved in the browser.
 * The stream keeps reconnecting while the session runs, so a short network drop ends in a small gap, not a dead player.
 */
export function LiveAudioPlayer({ deviceId, nonce }: { deviceId: string; nonce: number }) {
  const [status, setStatus] = useState('Connecting…');
  const [level, setLevel] = useState(0);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const gainRef = useRef<GainNode | null>(null);

  useEffect(() => {
    if (gainRef.current) gainRef.current.gain.value = muted ? 0 : volume;
  }, [muted, volume]);

  useEffect(() => {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) {
      setStatus('This browser cannot play live audio. Use a current Chrome or Edge.');
      return;
    }
    const ac = new AbortController();
    const ctx = new AudioCtx({ latencyHint: 'interactive' });
    const gain = ctx.createGain();
    gain.gain.value = muted ? 0 : volume;
    gain.connect(ctx.destination);
    gainRef.current = gain;
    void ctx.resume().catch(() => undefined);

    let sampleRate = 16000;
    let nextT = 0;
    let lastPacketAt = 0;
    let bytesIn = 0;
    let peak = 0;
    const tick = setInterval(() => {
      setLevel(peak);
      peak = 0;
      const quiet = lastPacketAt === 0 || Date.now() - lastPacketAt > 3000;
      setStatus(quiet ? 'Waiting for the tablet microphone…' : `Listening live · ${Math.round((bytesIn * 8) / 1000 / 2)} kbps`);
      bytesIn = 0;
      if (ctx.state === 'suspended') void ctx.resume().catch(() => undefined);
    }, 500);

    const play = (pcm: Uint8Array) => {
      const n = Math.floor(pcm.length / 2);
      if (n === 0) return;
      const view = new DataView(pcm.buffer, pcm.byteOffset, n * 2);
      const buf = ctx.createBuffer(1, n, sampleRate);
      const ch = buf.getChannelData(0);
      for (let i = 0; i < n; i++) {
        const v = view.getInt16(i * 2, true) / 32768;
        ch[i] = v;
        const a = v < 0 ? -v : v;
        if (a > peak) peak = a;
      }
      const now = ctx.currentTime;
      if (nextT - now > MAX_LAG_S) return;                 // too far behind: skip this packet to catch up
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(gain);
      const at = Math.max(now + JITTER_S, nextT);
      src.start(at);
      nextT = at + n / sampleRate;
    };

    (async () => {
      while (!ac.signal.aborted) {
        try {
          const res = await fetch(liveStreamUrl(deviceId, 'audio', nonce), { credentials: 'include', signal: ac.signal });
          if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
          const reader = res.body.getReader();
          let pending = new Uint8Array(0);
          nextT = 0;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            if (!value) continue;
            const joined = new Uint8Array(pending.length + value.length);
            joined.set(pending, 0);
            joined.set(value, pending.length);
            pending = joined;
            let pos = 0;
            while (pending.length - pos >= HEADER) {
              const type = pending[pos]!;
              const len = ((pending[pos + 9]! << 24) | (pending[pos + 10]! << 16) | (pending[pos + 11]! << 8) | pending[pos + 12]!) >>> 0;
              if (pending.length - pos - HEADER < len) break;
              const payload = pending.subarray(pos + HEADER, pos + HEADER + len);
              if (type === 1) {
                try {
                  const cfg = JSON.parse(new TextDecoder().decode(payload)) as { sr?: number };
                  if (cfg.sr && cfg.sr >= 8000 && cfg.sr <= 48000) sampleRate = cfg.sr;
                } catch { /* keep the default rate */ }
              } else if (type === 5) {
                lastPacketAt = Date.now();
                bytesIn += payload.length;
                play(payload);
              }
              pos += HEADER + len;
            }
            pending = pending.slice(pos);
          }
        } catch {
          if (ac.signal.aborted) return;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    })();

    return () => {
      ac.abort();
      clearInterval(tick);
      gainRef.current = null;
      void ctx.close().catch(() => undefined);
    };
    // The volume/mute state is applied through gainRef so changing it must not restart the stream.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId, nonce]);

  return (
    <div className="live-audio" style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span aria-hidden="true" style={{ width: 10, height: 10, borderRadius: '50%', background: status.startsWith('Listening') ? '#22c55e' : '#f59e0b', flex: 'none' }} />
        <span role="status">{status}</span>
      </div>
      <div aria-label="Microphone level" style={{ height: 8, borderRadius: 4, background: 'rgba(148,163,184,0.25)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${Math.min(100, Math.round(level * 140))}%`, background: '#22c55e', transition: 'width 120ms linear' }} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button type="button" className="btn btn-sm" onClick={() => setMuted((m) => !m)}>{muted ? 'Unmute' : 'Mute'}</button>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Volume
          <input type="range" min={0} max={1} step={0.05} value={volume} onChange={(e) => setVolume(Number(e.target.value))} />
        </label>
      </div>
    </div>
  );
}

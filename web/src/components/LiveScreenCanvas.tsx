import { useEffect, useRef, useState } from 'react';
import { liveStreamUrl, type RemoteKind } from '../api/remoteView';

/** Packet header: type(1) | ptsUs(8) | length(4). Types: 1 codec config, 2 keyframe, 3 delta. */
const HEADER = 13;

/** avc1.PPCCLL from the first SPS NAL (type 7) found in an Annex-B buffer. */
function codecFromAnnexB(data: Uint8Array): string | null {
  for (let i = 0; i + 4 < data.length; i++) {
    if (data[i] === 0 && data[i + 1] === 0 && (data[i + 2] === 1 || (data[i + 2] === 0 && data[i + 3] === 1))) {
      const nal = i + (data[i + 2] === 1 ? 3 : 4);
      if ((data[nal] & 0x1f) === 7 && nal + 3 < data.length) {
        const h = (b: number) => b.toString(16).padStart(2, '0');
        return `avc1.${h(data[nal + 1])}${h(data[nal + 2])}${h(data[nal + 3])}`;
      }
    }
  }
  return null;
}

/**
 * Live H.264 screen, decoded with WebCodecs and painted to a canvas. Pointer handlers receive
 * events from the canvas, so callers can map clicks to relative device coordinates.
 */
export function LiveScreenCanvas({
  deviceId, kind = 'screen', nonce, onMouseDown, onMouseUp,
}: {
  deviceId: string;
  kind?: RemoteKind;
  nonce: number;
  onMouseDown?: (e: React.MouseEvent<HTMLElement>) => void;
  onMouseUp?: (e: React.MouseEvent<HTMLElement>) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState('Connecting…');
  const [fps, setFps] = useState(0);
  const [diag, setDiag] = useState('');

  useEffect(() => {
    if (typeof VideoDecoder === 'undefined') {
      setStatus('This browser cannot play live video (WebCodecs needed - use current Chrome or Edge over HTTPS).');
      return;
    }
    const ac = new AbortController();
    let decoder: VideoDecoder | null = null;
    let configured = false;
    let frames = 0;
    const c = { rx: 0, dec: 0, out: 0, err: '', tablet: '' };
    const diagTimer = setInterval(() => setDiag(`tablet: ${c.tablet || 'no stats yet'} | rx ${c.rx} dec ${c.dec} out ${c.out}${c.err ? ' | ERR ' + c.err : ''}`), 1000);
    let rotation = 0;
    let mirror = false;
    const fpsTimer = setInterval(() => { setFps(frames); frames = 0; }, 1000);

    const makeDecoder = () => new VideoDecoder({
      output: (frame) => {
        const canvas = canvasRef.current;
        if (canvas) {
          const swap = rotation === 90 || rotation === 270;
          const cw = swap ? frame.displayHeight : frame.displayWidth;
          const ch = swap ? frame.displayWidth : frame.displayHeight;
          if (canvas.width !== cw || canvas.height !== ch) {
            canvas.width = cw;
            canvas.height = ch;
          }
          const ctx = canvas.getContext('2d');
          if (ctx) {
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.translate(cw / 2, ch / 2);
            if (mirror) ctx.scale(-1, 1);
            ctx.rotate((rotation * Math.PI) / 180);
            ctx.drawImage(frame, -frame.displayWidth / 2, -frame.displayHeight / 2);
          }
          frames++; c.out++;
          setStatus('');
        }
        frame.close();
      },
      error: (e) => { configured = false; c.err = String(e && e.message ? e.message : e).slice(0, 80); },
    });

    const run = async () => {
      while (!ac.signal.aborted) {
        try {
          const res = await fetch(liveStreamUrl(deviceId, kind, nonce), { credentials: 'include', signal: ac.signal });
          if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
          const reader = res.body.getReader();
          let buf = new Uint8Array(0);
          let needKey = true;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            const merged = new Uint8Array(buf.length + value.length);
            merged.set(buf); merged.set(value, buf.length);
            buf = merged;
            let pos = 0;
            while (buf.length - pos >= HEADER) {
              const dv = new DataView(buf.buffer, buf.byteOffset + pos);
              const type = dv.getUint8(0);
              const pts = Number(dv.getBigUint64(1));
              const len = dv.getUint32(9);
              if (buf.length - pos - HEADER < len) break;
              const payload = buf.subarray(pos + HEADER, pos + HEADER + len);
              pos += HEADER + len;
              if (type === 4) { // camera orientation hint from the tablet
                try {
                  const m = JSON.parse(new TextDecoder().decode(payload));
                  if (m.rotation !== undefined) rotation = Number(m.rotation) || 0;
                  if (m.mirror !== undefined) mirror = !!m.mirror;
                  if (m.enc_fps !== undefined) c.tablet = `${m.enc_fps} fps ${m.kbps} kbps backlog ${m.backlog_kb}KB upfail ${m.upload_fail}`;
                } catch { /* ignore a malformed hint */ }
                continue;
              }
              c.rx++;
              if (type === 1) continue; // SPS/PPS also ride in front of every keyframe
              if (type === 2) {
                if (!configured) {
                  const codec = codecFromAnnexB(payload);
                  if (!codec) continue;
                  decoder?.close();
                  decoder = makeDecoder();
                  decoder.configure({ codec, optimizeForLatency: true, hardwareAcceleration: 'prefer-hardware', avc: { format: 'annexb' } } as VideoDecoderConfig);
                  configured = true;
                }
                needKey = false;
              }
              if (needKey || !configured || !decoder || decoder.state !== 'configured') continue;
              // Never let decode lag build up: if the queue is deep, wait for the next keyframe.
              if (decoder.decodeQueueSize > 40 && type === 3) { needKey = true; continue; }
              c.dec++;
              decoder.decode(new EncodedVideoChunk({ type: type === 2 ? 'key' : 'delta', timestamp: pts, data: payload }));
            }
            buf = buf.slice(pos);
          }
        } catch (e) {
          if (ac.signal.aborted) return;
        }
        if (!ac.signal.aborted) {
          setStatus('Waiting for the tablet…');
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    };
    void run();

    return () => {
      ac.abort();
      clearInterval(fpsTimer);
      clearInterval(diagTimer);
      try { decoder?.close(); } catch { /* already closed */ }
    };
  }, [deviceId, kind, nonce]);

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <canvas
        ref={canvasRef}
        width={1280}
        height={800}
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
        style={{ display: 'block', width: '100%', maxHeight: 520, objectFit: 'contain', background: '#000', cursor: 'crosshair', userSelect: 'none' }}
      />
      {status && (
        <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: '#cbd5e1', fontSize: 14, textAlign: 'center', padding: 16, pointerEvents: 'none' }}>
          {status}
        </div>
      )}
      {diag && <div style={{ position: 'absolute', left: 8, bottom: 8, right: 8, fontSize: 11, color: '#cbd5e1', background: 'rgba(0,0,0,.55)', padding: '2px 6px', borderRadius: 4, pointerEvents: 'none' }}>{diag}</div>}
      {!status && <span style={{ position: 'absolute', right: 8, top: 8, fontSize: 12, color: '#94a3b8', background: 'rgba(0,0,0,.5)', padding: '2px 6px', borderRadius: 4 }}>{fps} fps</span>}
    </div>
  );
}

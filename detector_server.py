"""
Persistent WebSocket jewellery-detection service for the RSC2 gimbal hunt/
tracker hybrid: the phone streams preview frames here, this returns
normalized bounding boxes from Grounding DINO (the same detector already
proven for post-capture segmentation in sam_locate.py -- see
tools/benchmark_yolo_world.py for why YOLO-World was rejected: 0/20 hits
on real jewellery photos vs DINO's 12/12 across 2-25% size and every
corner, at ~280-300ms warm latency on this machine's RTX 5070).

Architecture (per the agreed detector/tracker hybrid):
  - This process is the "eyes" -- acquisition and periodic re-correction,
    NOT the fast per-frame control loop. The phone's own local tracker
    (OpenCV KCF, seeded from a box this returns) owns frame-to-frame
    following and drives the gimbal at preview speed; this only needs to
    run at whatever rate DINO can sustain (~3 fps warm).
  - Never queue frames: only the MOST RECENTLY RECEIVED frame is ever
    processed. If frames 101-104 arrive while 100 is still being detected,
    101-103 are discarded and only 104 is processed next -- same
    STRATEGY_KEEP_ONLY_LATEST philosophy CameraX's own ImageAnalysis uses,
    applied end-to-end across the network hop too.
  - Every response carries the frame_id and the ORIGINAL capture
    timestamp it was computed from, so the phone can judge staleness
    itself (a detection describing where the camera pointed 300ms ago is
    dangerous to steer directly from once the gimbal has moved since).
  - This process owns detection only. It never computes or sends PAN/TILT/
    ZOOM values -- that keeps network jitter completely separate from the
    phone's own real-time control loop, per the agreed design.
"""
import asyncio
import base64
import json
import logging
import time

import cv2
import numpy as np
import websockets

import sam_locate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("detector_server")

PORT = 8765
BOX_THRESHOLD = 0.20


def decode_jpeg_b64(jpeg_b64: str):
    raw = base64.b64decode(jpeg_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def detect(bgr) -> dict:
    """Runs Grounding DINO on one frame, returns the single best jewellery
    box (already sorted by DINO's own confidence-adjacent ranking inside
    _dino_boxes -- see that function's doc comment) as a normalized dict,
    or detected=False if nothing crossed BOX_THRESHOLD."""
    h, w = bgr.shape[:2]
    boxes = sam_locate._dino_boxes(bgr, expect=1, box_threshold=BOX_THRESHOLD)
    if not boxes:
        return {"detected": False}
    x0, y0, x1, y1 = boxes[0]
    return {
        "detected": True,
        "x": x0 / w,
        "y": y0 / h,
        "w": (x1 - x0) / w,
        "h": (y1 - y0) / h,
    }


async def handle_connection(websocket):
    peer = websocket.remote_address
    log.info(f"Client connected: {peer}")
    latest = {"frame_id": -1, "timestamp": 0, "image": None}
    last_processed_id = -1
    stop = asyncio.Event()

    async def receiver():
        nonlocal latest
        try:
            async for message in websocket:
                try:
                    msg = json.loads(message)
                    frame_id = int(msg["frame_id"])
                    timestamp = int(msg["timestamp"])
                    image = decode_jpeg_b64(msg["jpeg_b64"])
                    if image is None:
                        continue
                    # Overwrite unconditionally -- this IS the drop-stale-
                    # frames behaviour: only the most recent arrival is ever
                    # kept, whatever was here before (processed or not) is
                    # discarded.
                    latest = {"frame_id": frame_id, "timestamp": timestamp, "image": image}
                except Exception as e:
                    log.warning(f"Bad frame from {peer}: {e}")
        finally:
            stop.set()

    async def processor():
        nonlocal last_processed_id
        loop = asyncio.get_event_loop()
        while not stop.is_set():
            if latest["frame_id"] == last_processed_id or latest["image"] is None:
                await asyncio.sleep(0.01)
                continue
            frame_id = latest["frame_id"]
            timestamp = latest["timestamp"]
            image = latest["image"]
            last_processed_id = frame_id
            t0 = time.time()
            try:
                # DINO's torch call is blocking/synchronous -- run it off
                # the event loop so receiving new frames (and dropping
                # stale ones) keeps working while inference is in flight.
                result = await loop.run_in_executor(None, detect, image)
            except Exception as e:
                log.exception(f"Detection failed for frame {frame_id}")
                result = {"detected": False, "error": str(e)}
            latency_ms = (time.time() - t0) * 1000
            result["frame_id"] = frame_id
            result["capture_timestamp"] = timestamp
            result["server_latency_ms"] = round(latency_ms, 1)
            try:
                await websocket.send(json.dumps(result))
            except websockets.exceptions.ConnectionClosed:
                break
            log.info(f"frame={frame_id} detected={result.get('detected')} "
                      f"latency={latency_ms:.0f}ms")

    await asyncio.gather(receiver(), processor())
    log.info(f"Client disconnected: {peer}")


async def main():
    log.info("Warming up Grounding DINO (first call downloads/loads weights)...")
    warm = np.zeros((640, 640, 3), dtype=np.uint8)
    t0 = time.time()
    sam_locate._dino_boxes(warm, expect=1, box_threshold=BOX_THRESHOLD)
    log.info(f"Warm-up done in {time.time()-t0:.1f}s")

    log.info(f"Listening on ws://0.0.0.0:{PORT}")
    async with websockets.serve(handle_connection, "0.0.0.0", PORT, max_size=10 * 1024 * 1024):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

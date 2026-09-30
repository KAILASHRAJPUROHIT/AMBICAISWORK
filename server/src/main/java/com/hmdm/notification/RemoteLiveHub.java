package com.hmdm.notification;

import javax.inject.Singleton;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory relay for live remote-view H.264 video. The agent pushes framed packets, an admin's
 * browser pulls them as a byte stream. Nothing is persisted. Per device the hub keeps the codec
 * config plus every packet since the last keyframe (at most about one second of video), so a viewer
 * joining mid-stream starts cleanly on a keyframe, and a slow viewer skips forward to the newest
 * keyframe instead of building latency.
 *
 * <p>Packet framing (identical on both legs): type(1: 1=config, 2=key, 3=delta, 4=meta JSON) | ptsUs(8, BE) |
 * length(4, BE) | payload.</p>
 */
@Singleton
public class RemoteLiveHub {

    public static final int HEADER = 13;
    private static final int MAX_GOP_PACKETS = 900;

    public static final class Batch {
        public final List<byte[]> packets;
        public final long cursor;

        Batch(List<byte[]> packets, long cursor) {
            this.packets = packets;
            this.cursor = cursor;
        }
    }

    private static final class Slot {
        final Object lock = new Object();
        byte[] config;
        byte[] meta;
        final ArrayList<byte[]> gop = new ArrayList<>();
        long baseSeq = 1;   // sequence number of gop.get(0)
        long nextSeq = 1;   // sequence number the next packet will get
        long updatedAt;
    }

    private final ConcurrentHashMap<String, Slot> slots = new ConcurrentHashMap<>();

    /** @param type 1 config, 2 key, 3 delta, 4 meta; {@code framed} is the complete packet including header. */
    public void publish(String deviceNumber, int type, byte[] framed) {
        Slot slot = slots.computeIfAbsent(deviceNumber, k -> new Slot());
        synchronized (slot.lock) {
            if (type == 1) {
                slot.config = framed;
            } else if (type == 4) {
                slot.meta = framed;
            } else {
                if (type == 2 || slot.gop.size() >= MAX_GOP_PACKETS) {
                    slot.gop.clear();
                    slot.baseSeq = slot.nextSeq;
                }
                if (type == 2 || !slot.gop.isEmpty()) {
                    slot.gop.add(framed);
                    slot.nextSeq++;
                } // a delta with no keyframe before it is undecodable - drop it
            }
            slot.updatedAt = System.currentTimeMillis();
            slot.lock.notifyAll();
        }
        if (slots.size() > 256) {
            long cutoff = System.currentTimeMillis() - 10 * 60_000L;
            slots.entrySet().removeIf(e -> e.getValue().updatedAt < cutoff);
        }
    }

    /** Sticky packets a new viewer needs first (meta, then codec config); empty if none yet. */
    public List<byte[]> stickyPackets(String deviceNumber) {
        List<byte[]> out = new ArrayList<>(2);
        Slot slot = slots.get(deviceNumber);
        if (slot == null) return out;
        synchronized (slot.lock) {
            if (slot.meta != null) out.add(slot.meta);
            if (slot.config != null) out.add(slot.config);
        }
        return out;
    }

    /** Where a new viewer starts: the beginning of the current GOP (a keyframe). */
    public long startCursor(String deviceNumber) {
        Slot slot = slots.computeIfAbsent(deviceNumber, k -> new Slot());
        synchronized (slot.lock) {
            return slot.baseSeq;
        }
    }

    /** Blocks until packets at or after {@code cursor} exist; null on timeout. A lagging cursor jumps to the newest keyframe. */
    public Batch awaitNext(String deviceNumber, long cursor, long timeoutMs) throws InterruptedException {
        Slot slot = slots.computeIfAbsent(deviceNumber, k -> new Slot());
        long deadline = System.currentTimeMillis() + timeoutMs;
        synchronized (slot.lock) {
            while (true) {
                if (cursor < slot.baseSeq) cursor = slot.baseSeq;
                if (cursor < slot.nextSeq) {
                    int from = (int) (cursor - slot.baseSeq);
                    List<byte[]> out = new ArrayList<>(slot.gop.subList(from, slot.gop.size()));
                    return new Batch(out, slot.nextSeq);
                }
                long left = deadline - System.currentTimeMillis();
                if (left <= 0) return null;
                slot.lock.wait(left);
            }
        }
    }
}

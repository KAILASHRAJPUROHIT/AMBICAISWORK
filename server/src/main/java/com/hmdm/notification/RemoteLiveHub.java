package com.hmdm.notification;

import javax.inject.Singleton;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory relay for live remote-view video: the agent pushes JPEG frames, an admin's browser pulls
 * them as an MJPEG stream. Frames are never persisted - only the newest one per device is kept, and a
 * slow viewer simply skips to the newest frame instead of building a backlog.
 */
@Singleton
public class RemoteLiveHub {

    public static final class Frame {
        public final byte[] jpeg;
        public final long seq;

        Frame(byte[] jpeg, long seq) {
            this.jpeg = jpeg;
            this.seq = seq;
        }
    }

    private static final class Slot {
        final Object lock = new Object();
        byte[] jpeg;
        long seq;
        long updatedAt;
    }

    private final ConcurrentHashMap<String, Slot> slots = new ConcurrentHashMap<>();

    public void publish(String deviceNumber, byte[] jpeg) {
        Slot slot = slots.computeIfAbsent(deviceNumber, k -> new Slot());
        synchronized (slot.lock) {
            slot.jpeg = jpeg;
            slot.seq++;
            slot.updatedAt = System.currentTimeMillis();
            slot.lock.notifyAll();
        }
        if (slots.size() > 256) {
            long cutoff = System.currentTimeMillis() - 10 * 60_000L;
            slots.entrySet().removeIf(e -> e.getValue().updatedAt < cutoff);
        }
    }

    /** Blocks until a frame newer than {@code lastSeq} exists; null when nothing arrives within the timeout. */
    public Frame awaitNext(String deviceNumber, long lastSeq, long timeoutMs) throws InterruptedException {
        Slot slot = slots.computeIfAbsent(deviceNumber, k -> new Slot());
        long deadline = System.currentTimeMillis() + timeoutMs;
        synchronized (slot.lock) {
            while (slot.seq <= lastSeq) {
                long left = deadline - System.currentTimeMillis();
                if (left <= 0) return null;
                slot.lock.wait(left);
            }
            return new Frame(slot.jpeg, slot.seq);
        }
    }

    /** Sequence of the newest frame, so a new viewer starts from "now" rather than a stale image. */
    public long currentSeq(String deviceNumber) {
        Slot slot = slots.get(deviceNumber);
        if (slot == null) return 0;
        synchronized (slot.lock) {
            return slot.seq;
        }
    }
}

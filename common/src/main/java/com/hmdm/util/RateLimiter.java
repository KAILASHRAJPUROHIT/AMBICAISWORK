package com.hmdm.util;

import java.util.Deque;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedDeque;

/**
 * <p>A minimal in-memory sliding-window rate limiter, keyed by an arbitrary string (typically a
 * client IP). No external dependency, no persistence — restarts reset all counters, which is
 * acceptable for its purpose (slowing down brute-force credential guessing against a single
 * public endpoint, not a durable audit trail).</p>
 *
 * <p>Not distributed: if the server ever runs as more than one instance behind a load balancer,
 * each instance tracks its own counters independently. Fine for this deployment's single-instance
 * shape; would need a shared store (e.g. the database or Redis) to hold across instances.</p>
 */
public class RateLimiter {

    private final int maxAttempts;
    private final long windowMillis;
    private final ConcurrentHashMap<String, Deque<Long>> attempts = new ConcurrentHashMap<>();

    public RateLimiter(int maxAttempts, long windowMillis) {
        this.maxAttempts = maxAttempts;
        this.windowMillis = windowMillis;
    }

    /**
     * Records one attempt for {@code key} and reports whether it should be allowed. Prunes
     * timestamps older than the window on every call, so memory doesn't grow unbounded for a
     * key that stops being used.
     */
    public boolean tryAcquire(String key) {
        long now = System.currentTimeMillis();
        Deque<Long> timestamps = attempts.computeIfAbsent(key, k -> new ConcurrentLinkedDeque<>());
        synchronized (timestamps) {
            while (!timestamps.isEmpty() && now - timestamps.peekFirst() > windowMillis) {
                timestamps.pollFirst();
            }
            if (timestamps.size() >= maxAttempts) {
                return false;
            }
            timestamps.addLast(now);
            return true;
        }
    }
}

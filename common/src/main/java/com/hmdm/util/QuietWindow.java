package com.hmdm.util;

import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The shop-closed hours ({@code settings.guardQuietHours}): {@code HH:MM-HH:MM} (may wrap past midnight), {@code off}, or
 * empty for the default 22:00-08:00. The devices apply the same window to their offline protection; the server uses it so a
 * router switched off overnight does not raise "device stopped reporting" alerts for every tablet each night.
 */
public final class QuietWindow {

    public static final String DEFAULT = "22:00-08:00";
    private static final Pattern FORMAT = Pattern.compile("^([01]\\d|2[0-3]):([0-5]\\d)-([01]\\d|2[0-3]):([0-5]\\d)$");

    private final boolean enabled;
    private final int startMin;
    private final int endMin;

    private QuietWindow(boolean enabled, int startMin, int endMin) {
        this.enabled = enabled;
        this.startMin = startMin;
        this.endMin = endMin;
    }

    /** An unreadable value falls back to the default rather than switching the protection off. */
    public static QuietWindow parse(String raw) {
        String v = raw == null ? "" : raw.trim();
        if ("off".equalsIgnoreCase(v)) return new QuietWindow(false, 0, 0);
        Matcher m = FORMAT.matcher(v);
        if (!m.matches()) m = FORMAT.matcher(DEFAULT);
        m.matches();
        return new QuietWindow(true,
                Integer.parseInt(m.group(1)) * 60 + Integer.parseInt(m.group(2)),
                Integer.parseInt(m.group(3)) * 60 + Integer.parseInt(m.group(4)));
    }

    public boolean isEnabled() { return enabled; }

    public boolean containsMinute(int minuteOfDay) {
        if (!enabled) return false;
        return startMin <= endMin
                ? minuteOfDay >= startMin && minuteOfDay < endMin
                : minuteOfDay >= startMin || minuteOfDay < endMin;
    }

    /** True when {@code nowMillis}, on the clock of {@code zone}, is inside the shop-closed window. */
    public boolean isQuiet(long nowMillis, ZoneId zone) {
        ZonedDateTime t = Instant.ofEpochMilli(nowMillis).atZone(zone);
        return containsMinute(t.getHour() * 60 + t.getMinute());
    }

    /** Epoch millis of the most recent moment the window ended at or before {@code nowMillis}; 0 when disabled. */
    public long lastEnd(long nowMillis, ZoneId zone) {
        if (!enabled) return 0L;
        ZonedDateTime now = Instant.ofEpochMilli(nowMillis).atZone(zone);
        ZonedDateTime end = now.toLocalDate().atTime(endMin / 60, endMin % 60).atZone(zone);
        if (end.isAfter(now)) end = end.minusDays(1);
        return end.toInstant().toEpochMilli();
    }
}

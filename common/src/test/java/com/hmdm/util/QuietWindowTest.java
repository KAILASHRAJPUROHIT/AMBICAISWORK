package com.hmdm.util;

import org.junit.Test;

import java.time.ZoneId;
import java.time.ZonedDateTime;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class QuietWindowTest {
    private static final ZoneId IST = ZoneId.of("Asia/Kolkata");

    private static long at(int day, int hour, int minute) {
        return ZonedDateTime.of(2026, 10, day, hour, minute, 0, 0, IST).toInstant().toEpochMilli();
    }

    @Test
    public void overnightWindowWrapsPastMidnight() {
        QuietWindow q = QuietWindow.parse("22:00-08:00");
        assertTrue(q.isQuiet(at(5, 23, 0), IST));
        assertTrue(q.isQuiet(at(5, 2, 30), IST));
        assertFalse(q.isQuiet(at(5, 8, 0), IST));
        assertFalse(q.isQuiet(at(5, 14, 0), IST));
    }

    @Test
    public void emptyAndJunkUseTheDefaultAndOffDisables() {
        assertTrue(QuietWindow.parse(null).isQuiet(at(5, 23, 0), IST));
        assertTrue(QuietWindow.parse("").isQuiet(at(5, 23, 0), IST));
        assertTrue(QuietWindow.parse("garbage").isQuiet(at(5, 23, 0), IST));
        QuietWindow off = QuietWindow.parse("off");
        assertFalse(off.isEnabled());
        assertFalse(off.isQuiet(at(5, 23, 0), IST));
        assertEquals(0L, off.lastEnd(at(5, 12, 0), IST));
    }

    @Test
    public void lastEndIsThisMorningOrYesterdaysMorning() {
        QuietWindow q = QuietWindow.parse("22:00-08:00");
        assertEquals(at(5, 8, 0), q.lastEnd(at(5, 8, 30), IST));
        assertEquals(at(5, 8, 0), q.lastEnd(at(5, 20, 0), IST));
        assertEquals(at(4, 8, 0), q.lastEnd(at(5, 7, 0), IST));
    }
}

package com.hmdm.task;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.Settings;
import com.hmdm.util.QuietWindow;
import com.hmdm.persistence.domain.SilentCandidate;
import com.hmdm.persistence.mapper.DeviceSilentMapper;
import com.hmdm.service.AlertDispatcher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.ZoneId;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Raises a {@code deviceSilent} event (and any matching admin alert rule) when an enrolled device has not checked in for
 * {@code MDM_SILENT_MINUTES} (default 45; devices check in at least every 15 minutes), and a {@code deviceBack} event when
 * it reports again. Each device alerts once per outage, not on every run.
 *
 * <p>The shop's closed hours (Settings, {@code guardQuietHours}, default 22:00-08:00 on the clock of {@code MDM_SHOP_TZ},
 * default Asia/Kolkata) are excluded: a router switched off overnight is normal, so nothing is flagged while the shop is
 * closed, and the time since the shop opened (not since last night) is what counts in the morning.</p>
 */
@Singleton
public class DeviceSilentTask implements Runnable {

    private static final Logger logger = LoggerFactory.getLogger(DeviceSilentTask.class);
    private static final long MINUTE_MS = 60_000L;
    private static final int DEFAULT_MINUTES = 45;

    private final DeviceSilentMapper mapper;
    private final AgentCommandDAO commandDAO;
    private final AlertDispatcher alertDispatcher;
    private final UnsecureDAO unsecureDAO;

    @Inject
    public DeviceSilentTask(DeviceSilentMapper mapper, AgentCommandDAO commandDAO, AlertDispatcher alertDispatcher,
                            UnsecureDAO unsecureDAO) {
        this.unsecureDAO = unsecureDAO;
        this.mapper = mapper;
        this.commandDAO = commandDAO;
        this.alertDispatcher = alertDispatcher;
    }

    @Override
    public void run() {
        try {
            long now = System.currentTimeMillis();
            long cutoff = now - minutes() * MINUTE_MS;

            Set<String> already = new HashSet<String>(mapper.listSilentNumbers());
            List<SilentCandidate> stale = mapper.listStale(cutoff);
            ZoneId zone = zone();
            Map<Integer, QuietWindow> windows = new HashMap<Integer, QuietWindow>();
            for (SilentCandidate c : stale) {
                if (already.contains(c.getDeviceNumber())) continue;
                QuietWindow quiet = windowFor(windows, c.getCustomerId());
                if (quiet.isQuiet(now, zone)) continue; // shop closed: silence is expected
                long since = Math.max(c.getLastUpdate() == null ? 0L : c.getLastUpdate(), quiet.lastEnd(now, zone));
                if (since >= cutoff) continue; // the shop only just opened: give the tablets time to reconnect
                mapper.markSilent(c.getDeviceNumber(), now);
                String detail = "no check-in since " + c.getLastUpdate();
                commandDAO.insertEvent(c.getDeviceNumber(), "deviceSilent", now, detail);
                if (c.getCustomerId() != null) {
                    alertDispatcher.dispatch(c.getCustomerId(), "deviceSilent", c.getDeviceNumber(), detail);
                }
            }
            for (SilentCandidate c : mapper.listRecovered(cutoff)) {
                mapper.clearSilent(c.getDeviceNumber());
                commandDAO.insertEvent(c.getDeviceNumber(), "deviceBack", now, "reporting again");
                if (c.getCustomerId() != null) {
                    alertDispatcher.dispatch(c.getCustomerId(), "deviceBack", c.getDeviceNumber(), "reporting again");
                }
            }
        } catch (Exception e) {
            logger.warn("device silent check failed", e); // the next run retries
        }
    }

    private QuietWindow windowFor(Map<Integer, QuietWindow> cache, Integer customerId) {
        if (customerId == null) return QuietWindow.parse(null);
        QuietWindow w = cache.get(customerId);
        if (w == null) {
            Settings settings = unsecureDAO.getSettings(customerId);
            w = QuietWindow.parse(settings == null ? null : settings.getGuardQuietHours());
            cache.put(customerId, w);
        }
        return w;
    }

    private static ZoneId zone() {
        String v = System.getProperty("MDM_SHOP_TZ", System.getenv("MDM_SHOP_TZ"));
        try {
            return ZoneId.of(v == null || v.trim().isEmpty() ? "Asia/Kolkata" : v.trim());
        } catch (Exception e) {
            return ZoneId.of("Asia/Kolkata");
        }
    }

    private static int minutes() {
        String v = System.getProperty("MDM_SILENT_MINUTES", System.getenv("MDM_SILENT_MINUTES"));
        try {
            int m = v == null ? DEFAULT_MINUTES : Integer.parseInt(v.trim());
            return m >= 20 ? m : DEFAULT_MINUTES;
        } catch (NumberFormatException e) {
            return DEFAULT_MINUTES;
        }
    }
}

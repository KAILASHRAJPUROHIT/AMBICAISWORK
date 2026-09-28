package com.hmdm.task;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.AgentCommandDAO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Daily cleanup of the device_event timeline, which otherwise grows forever -- and grows faster
 * since agents log activity (app usage, screen/Wi-Fi changes; agent v0.2.71+).
 *
 * <ul>
 *   <li>{@code logcat} blobs (~3.8KB each, crash diagnostics only) are kept 7 days. Agents up to
 *       v0.2.70 uploaded one on every check-in, so this also clears that backlog.</li>
 *   <li>Everything else is kept {@code MDM_EVENT_RETENTION_DAYS} days (default 90).</li>
 * </ul>
 */
@Singleton
public class DeviceEventRetentionTask implements Runnable {

    private static final Logger logger = LoggerFactory.getLogger(DeviceEventRetentionTask.class);
    private static final long DAY_MS = 24L * 60 * 60 * 1000;
    private static final int LOGCAT_RETENTION_DAYS = 7;
    private static final int DEFAULT_RETENTION_DAYS = 90;

    private final AgentCommandDAO commandDAO;

    @Inject
    public DeviceEventRetentionTask(AgentCommandDAO commandDAO) {
        this.commandDAO = commandDAO;
    }

    @Override
    public void run() {
        try {
            long now = System.currentTimeMillis();
            int logcat = commandDAO.purgeEventsOfType("logcat", now - LOGCAT_RETENTION_DAYS * DAY_MS);
            int days = retentionDays();
            int rest = commandDAO.purgeEventsOlderThan(now - days * DAY_MS);
            logger.info("device_event retention: removed {} logcat (>{}d) and {} other (>{}d) events",
                    logcat, LOGCAT_RETENTION_DAYS, rest, days);
        } catch (Exception e) {
            logger.warn("device_event retention failed", e); // next daily run retries
        }
    }

    private static int retentionDays() {
        String v = System.getProperty("MDM_EVENT_RETENTION_DAYS", System.getenv("MDM_EVENT_RETENTION_DAYS"));
        try {
            int d = v == null ? DEFAULT_RETENTION_DAYS : Integer.parseInt(v.trim());
            return d >= LOGCAT_RETENTION_DAYS ? d : DEFAULT_RETENTION_DAYS;
        } catch (NumberFormatException e) {
            return DEFAULT_RETENTION_DAYS;
        }
    }
}

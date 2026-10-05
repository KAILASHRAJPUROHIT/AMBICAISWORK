package com.hmdm.task;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.domain.SilentCandidate;
import com.hmdm.persistence.mapper.DeviceSilentMapper;
import com.hmdm.service.AlertDispatcher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Raises a {@code deviceSilent} event (and any matching admin alert rule) when an enrolled device has not checked in for
 * {@code MDM_SILENT_MINUTES} (default 45; devices check in at least every 15 minutes), and a {@code deviceBack} event when
 * it reports again. Each device alerts once per outage, not on every run.
 */
@Singleton
public class DeviceSilentTask implements Runnable {

    private static final Logger logger = LoggerFactory.getLogger(DeviceSilentTask.class);
    private static final long MINUTE_MS = 60_000L;
    private static final int DEFAULT_MINUTES = 45;

    private final DeviceSilentMapper mapper;
    private final AgentCommandDAO commandDAO;
    private final AlertDispatcher alertDispatcher;

    @Inject
    public DeviceSilentTask(DeviceSilentMapper mapper, AgentCommandDAO commandDAO, AlertDispatcher alertDispatcher) {
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
            for (SilentCandidate c : stale) {
                if (already.contains(c.getDeviceNumber())) continue;
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

package com.hmdm.task;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.mapper.DeviceSilentMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Daily cleanup of the location breadcrumb trail ({@code device_location}), which otherwise grows without limit.
 * Fixes older than {@code MDM_LOCATION_RETENTION_DAYS} (default 90, minimum 7) are deleted.
 */
@Singleton
public class LocationRetentionTask implements Runnable {

    private static final Logger logger = LoggerFactory.getLogger(LocationRetentionTask.class);
    private static final long DAY_MS = 24L * 60 * 60 * 1000;
    private static final int DEFAULT_DAYS = 90;
    private static final int MIN_DAYS = 7;

    private final DeviceSilentMapper mapper;

    @Inject
    public LocationRetentionTask(DeviceSilentMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public void run() {
        try {
            int days = days();
            int removed = mapper.deleteLocationsOlderThan(System.currentTimeMillis() - days * DAY_MS);
            logger.info("device_location retention: removed {} fixes older than {} days", removed, days);
        } catch (Exception e) {
            logger.warn("device_location retention failed", e); // next daily run retries
        }
    }

    private static int days() {
        String v = System.getProperty("MDM_LOCATION_RETENTION_DAYS", System.getenv("MDM_LOCATION_RETENTION_DAYS"));
        try {
            int d = v == null ? DEFAULT_DAYS : Integer.parseInt(v.trim());
            return d >= MIN_DAYS ? d : DEFAULT_DAYS;
        } catch (NumberFormatException e) {
            return DEFAULT_DAYS;
        }
    }
}

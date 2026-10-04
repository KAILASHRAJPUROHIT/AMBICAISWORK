package com.hmdm.service;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.domain.Geofence;
import com.hmdm.persistence.mapper.GeofenceMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * Evaluates a device's freshly check-in-reported location against its customer's enabled
 * {@link Geofence}s, and records enter/exit transitions. Called synchronously from
 * {@code AgentResource#checkin()} right after the location fix is persisted — kept fast
 * (haversine distance, one row read/write per geofence) since it runs on the check-in request
 * thread; notification itself is handed off to {@link AlertDispatcher}, which is already async.
 */
@Singleton
public class GeofenceEvaluator {

    private static final Logger logger = LoggerFactory.getLogger(GeofenceEvaluator.class);
    private static final double EARTH_RADIUS_METERS = 6_371_000.0;
    private static final long MAX_FIX_AGE_MS = 30L * 60_000L;

    private final GeofenceMapper geofenceMapper;
    private final AgentCommandDAO commandDAO;
    private final AlertDispatcher alertDispatcher;

    @Inject
    public GeofenceEvaluator(GeofenceMapper geofenceMapper, AgentCommandDAO commandDAO,
                              AlertDispatcher alertDispatcher) {
        this.geofenceMapper = geofenceMapper;
        this.commandDAO = commandDAO;
        this.alertDispatcher = alertDispatcher;
    }

    /**
     * Never throws — a lookup/evaluation failure is logged only, since this must never fail
     * (or meaningfully slow down) the check-in it's called from.
     */
    public void evaluate(int customerId, String deviceNumber, double lat, double lon) {
        evaluate(customerId, deviceNumber, lat, lon, null, null);
    }

    /**
     * Same as above, but aware of fix quality. A fix older than {@link #MAX_FIX_AGE_MS} is ignored (a stale position
     * says nothing about where the device is now), and an EXIT is only recorded when the device is outside the
     * fence by more than the fix's own accuracy, so GPS/network jitter at the edge cannot flap enter/exit alerts.
     */
    public void evaluate(int customerId, String deviceNumber, double lat, double lon,
                         Double accuracyMeters, Long capturedAtMillis) {
        if (capturedAtMillis != null && capturedAtMillis > 0
                && System.currentTimeMillis() - capturedAtMillis > MAX_FIX_AGE_MS) {
            return;
        }
        try {
            List<Geofence> geofences = geofenceMapper.listEnabled(customerId);
            for (Geofence g : geofences) {
                evaluateOne(g, deviceNumber, lat, lon, accuracyMeters == null ? 0.0 : accuracyMeters);
            }
        } catch (Exception e) {
            logger.warn("Geofence evaluation failed for device {}: {}", deviceNumber, e.getMessage());
        }
    }

    private void evaluateOne(Geofence g, String deviceNumber, double lat, double lon, double accuracyMeters) {
        double dist = distanceMeters(g.getCenterLat(), g.getCenterLon(), lat, lon);
        Boolean wasInside = geofenceMapper.getState(g.getId(), deviceNumber);
        boolean nowInside = dist <= g.getRadiusMeters();
        if (wasInside != null && wasInside && !nowInside && dist - accuracyMeters <= g.getRadiusMeters()) {
            return; // might still be inside once the fix's uncertainty is allowed for
        }
        if (wasInside != null && wasInside == nowInside) {
            return; // no transition
        }
        geofenceMapper.upsertState(g.getId(), deviceNumber, nowInside, System.currentTimeMillis());
        if (wasInside == null && !nowInside) {
            return; // first-ever fix, already outside — not a transition worth an event
        }
        String eventType = nowInside ? "geofence.enter" : "geofence.exit";
        String detail = g.getName();
        commandDAO.insertEvent(deviceNumber, eventType, System.currentTimeMillis(), detail);
        alertDispatcher.dispatch(g.getCustomerId(), eventType, deviceNumber, detail);
    }

    /** Great-circle distance between two lat/lon points, in meters (haversine formula). */
    private static double distanceMeters(double lat1, double lon1, double lat2, double lon2) {
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return EARTH_RADIUS_METERS * c;
    }
}

package com.hmdm.persistence.domain;

import java.io.Serializable;

/**
 * A customer-scoped circular geofence. Evaluated against every check-in that carries a fresh
 * location fix ({@link GeofenceEvaluator}); enter/exit transitions are recorded as
 * {@code device_event} rows and fanned out through the existing {@link AlertRule} notifier.
 * Circle-only — polygon support is a deliberate scope cut, not an oversight.
 */
public class Geofence implements Serializable {

    private static final long serialVersionUID = 1L;

    private Integer id;
    private int customerId;
    private String name;
    private double centerLat;
    private double centerLon;
    private double radiusMeters;
    private boolean enabled = true;
    private long createdAt;

    public Geofence() {
    }

    public Integer getId() {
        return id;
    }

    public void setId(Integer id) {
        this.id = id;
    }

    public int getCustomerId() {
        return customerId;
    }

    public void setCustomerId(int customerId) {
        this.customerId = customerId;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public double getCenterLat() {
        return centerLat;
    }

    public void setCenterLat(double centerLat) {
        this.centerLat = centerLat;
    }

    public double getCenterLon() {
        return centerLon;
    }

    public void setCenterLon(double centerLon) {
        this.centerLon = centerLon;
    }

    public double getRadiusMeters() {
        return radiusMeters;
    }

    public void setRadiusMeters(double radiusMeters) {
        this.radiusMeters = radiusMeters;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public long getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(long createdAt) {
        this.createdAt = createdAt;
    }
}

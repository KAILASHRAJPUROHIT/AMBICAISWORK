package com.hmdm.persistence.domain;

import java.io.Serializable;

/**
 * One agent-reported data-usage snapshot (table {@code device_data_usage}). Each row is the
 * device's cumulative cellular/Wi-Fi bytes for the local day starting at {@code windowStart},
 * as of {@code capturedAt} — a running total, not a delta between rows.
 */
public class DeviceDataUsage implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;
    private String deviceNumber;
    private long mobileRxBytes;
    private long mobileTxBytes;
    private long wifiRxBytes;
    private long wifiTxBytes;
    private long windowStart;
    private long capturedAt;
    private long recordedAt;

    public DeviceDataUsage() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getDeviceNumber() {
        return deviceNumber;
    }

    public void setDeviceNumber(String deviceNumber) {
        this.deviceNumber = deviceNumber;
    }

    public long getMobileRxBytes() {
        return mobileRxBytes;
    }

    public void setMobileRxBytes(long mobileRxBytes) {
        this.mobileRxBytes = mobileRxBytes;
    }

    public long getMobileTxBytes() {
        return mobileTxBytes;
    }

    public void setMobileTxBytes(long mobileTxBytes) {
        this.mobileTxBytes = mobileTxBytes;
    }

    public long getWifiRxBytes() {
        return wifiRxBytes;
    }

    public void setWifiRxBytes(long wifiRxBytes) {
        this.wifiRxBytes = wifiRxBytes;
    }

    public long getWifiTxBytes() {
        return wifiTxBytes;
    }

    public void setWifiTxBytes(long wifiTxBytes) {
        this.wifiTxBytes = wifiTxBytes;
    }

    public long getWindowStart() {
        return windowStart;
    }

    public void setWindowStart(long windowStart) {
        this.windowStart = windowStart;
    }

    public long getCapturedAt() {
        return capturedAt;
    }

    public void setCapturedAt(long capturedAt) {
        this.capturedAt = capturedAt;
    }

    public long getRecordedAt() {
        return recordedAt;
    }

    public void setRecordedAt(long recordedAt) {
        this.recordedAt = recordedAt;
    }
}

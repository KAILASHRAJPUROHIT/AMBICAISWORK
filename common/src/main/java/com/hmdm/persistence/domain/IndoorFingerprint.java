package com.hmdm.persistence.domain;

import java.io.Serializable;

/** One surveyed point: where it is on the plan (metres) and the Wi-Fi signal strengths heard there (JSON BSSID -> dBm). */
public class IndoorFingerprint implements Serializable {
    private static final long serialVersionUID = 1L;
    private Integer id;
    private Integer customerId;
    private Double x;
    private Double y;
    private String rssi;
    private Double mag;
    private Long createdAt;
    private String createdBy;

    public Integer getId() { return id; }
    public void setId(Integer v) { this.id = v; }
    public Integer getCustomerId() { return customerId; }
    public void setCustomerId(Integer v) { this.customerId = v; }
    public Double getX() { return x; }
    public void setX(Double v) { this.x = v; }
    public Double getY() { return y; }
    public void setY(Double v) { this.y = v; }
    public String getRssi() { return rssi; }
    public void setRssi(String v) { this.rssi = v; }
    public Double getMag() { return mag; }
    public void setMag(Double v) { this.mag = v; }
    public Long getCreatedAt() { return createdAt; }
    public void setCreatedAt(Long v) { this.createdAt = v; }
    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String v) { this.createdBy = v; }
}

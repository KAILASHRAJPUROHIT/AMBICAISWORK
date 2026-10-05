package com.hmdm.persistence.domain;

import java.io.Serializable;

/** A device and the time of its last check-in, used to decide whether it has stopped reporting. */
public class SilentCandidate implements Serializable {
    private static final long serialVersionUID = 1L;
    private String deviceNumber;
    private Integer customerId;
    private Long lastUpdate;

    public String getDeviceNumber() { return deviceNumber; }
    public void setDeviceNumber(String v) { this.deviceNumber = v; }
    public Integer getCustomerId() { return customerId; }
    public void setCustomerId(Integer v) { this.customerId = v; }
    public Long getLastUpdate() { return lastUpdate; }
    public void setLastUpdate(Long v) { this.lastUpdate = v; }
}

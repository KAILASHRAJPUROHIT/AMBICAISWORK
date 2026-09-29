package com.hmdm.persistence.domain;

import java.io.Serializable;

/** Latest sales leaderboard for one customer, exactly as normalised at ingest (JSON text). */
public class LeaderboardSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private Integer customerId;
    private String businessDate;
    private String generatedAt;
    private String payload;
    private Long receivedAt;

    public Integer getCustomerId() { return customerId; }
    public void setCustomerId(Integer v) { this.customerId = v; }
    public String getBusinessDate() { return businessDate; }
    public void setBusinessDate(String v) { this.businessDate = v; }
    public String getGeneratedAt() { return generatedAt; }
    public void setGeneratedAt(String v) { this.generatedAt = v; }
    public String getPayload() { return payload; }
    public void setPayload(String v) { this.payload = v; }
    public Long getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Long v) { this.receivedAt = v; }
}

package com.hmdm.persistence.domain;

/** One-time, short-lived OAuth anti-forgery state. Only its SHA-256 digest is persisted. */
public class FrpOAuthState {
    private Integer id;
    private String stateHash;
    private int customerId;
    private Integer userId;
    private long expiresAt;
    private Long consumedAt;

    public Integer getId() { return id; }
    public void setId(Integer id) { this.id = id; }
    public String getStateHash() { return stateHash; }
    public void setStateHash(String stateHash) { this.stateHash = stateHash; }
    public int getCustomerId() { return customerId; }
    public void setCustomerId(int customerId) { this.customerId = customerId; }
    public Integer getUserId() { return userId; }
    public void setUserId(Integer userId) { this.userId = userId; }
    public long getExpiresAt() { return expiresAt; }
    public void setExpiresAt(long expiresAt) { this.expiresAt = expiresAt; }
    public Long getConsumedAt() { return consumedAt; }
    public void setConsumedAt(Long consumedAt) { this.consumedAt = consumedAt; }
}

package com.hmdm.persistence.domain;

/** A browser/computer allowed to sign in to the console as one user. Only a digest of its fingerprint is stored. */
public class ConsoleTrustedDevice {
    private Integer id;
    private int userId;
    private String fingerprintHash;
    private String label;
    private String userAgent;
    private String ipAddress;
    private long createdAt;
    private long lastSeenAt;

    public Integer getId() { return id; }
    public void setId(Integer id) { this.id = id; }
    public int getUserId() { return userId; }
    public void setUserId(int userId) { this.userId = userId; }
    public String getFingerprintHash() { return fingerprintHash; }
    public void setFingerprintHash(String fingerprintHash) { this.fingerprintHash = fingerprintHash; }
    public String getLabel() { return label; }
    public void setLabel(String label) { this.label = label; }
    public String getUserAgent() { return userAgent; }
    public void setUserAgent(String userAgent) { this.userAgent = userAgent; }
    public String getIpAddress() { return ipAddress; }
    public void setIpAddress(String ipAddress) { this.ipAddress = ipAddress; }
    public long getCreatedAt() { return createdAt; }
    public void setCreatedAt(long createdAt) { this.createdAt = createdAt; }
    public long getLastSeenAt() { return lastSeenAt; }
    public void setLastSeenAt(long lastSeenAt) { this.lastSeenAt = lastSeenAt; }
}

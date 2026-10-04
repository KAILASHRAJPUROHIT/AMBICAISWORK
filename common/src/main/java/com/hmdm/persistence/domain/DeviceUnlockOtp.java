package com.hmdm.persistence.domain;

/** A one-time code that lets an administrator lift a tablet's offline lockdown. Stored only as a salted digest. */
public class DeviceUnlockOtp {
    private Integer id;
    private String deviceNumber;
    private String salt;
    private String codeHash;
    private long createdAt;
    private long expiresAt;
    private int attempts;
    private Long usedAt;

    public Integer getId() { return id; }
    public void setId(Integer id) { this.id = id; }
    public String getDeviceNumber() { return deviceNumber; }
    public void setDeviceNumber(String deviceNumber) { this.deviceNumber = deviceNumber; }
    public String getSalt() { return salt; }
    public void setSalt(String salt) { this.salt = salt; }
    public String getCodeHash() { return codeHash; }
    public void setCodeHash(String codeHash) { this.codeHash = codeHash; }
    public long getCreatedAt() { return createdAt; }
    public void setCreatedAt(long createdAt) { this.createdAt = createdAt; }
    public long getExpiresAt() { return expiresAt; }
    public void setExpiresAt(long expiresAt) { this.expiresAt = expiresAt; }
    public int getAttempts() { return attempts; }
    public void setAttempts(int attempts) { this.attempts = attempts; }
    public Long getUsedAt() { return usedAt; }
    public void setUsedAt(Long usedAt) { this.usedAt = usedAt; }
}

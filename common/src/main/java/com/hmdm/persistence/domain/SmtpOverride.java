package com.hmdm.persistence.domain;

/**
 * Outgoing-email settings entered in the console. When present they take the place of the server's SMTP_* environment
 * values. The password is stored encrypted ({@link #passwordEnc}); {@link #password} only ever holds it in memory.
 */
public class SmtpOverride {
    private String host;
    private int port;
    /** "ssl", "starttls" or "none". */
    private String security;
    private String username;
    private String passwordEnc;
    private String fromAddress;
    private long updatedAt;
    private String updatedBy;
    /** Decrypted password, filled in by the DAO; never persisted and never sent to the console. */
    private transient String password;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }
    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
    public String getSecurity() { return security; }
    public void setSecurity(String security) { this.security = security; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPasswordEnc() { return passwordEnc; }
    public void setPasswordEnc(String passwordEnc) { this.passwordEnc = passwordEnc; }
    public String getFromAddress() { return fromAddress; }
    public void setFromAddress(String fromAddress) { this.fromAddress = fromAddress; }
    public long getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(long updatedAt) { this.updatedAt = updatedAt; }
    public String getUpdatedBy() { return updatedBy; }
    public void setUpdatedBy(String updatedBy) { this.updatedBy = updatedBy; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
}

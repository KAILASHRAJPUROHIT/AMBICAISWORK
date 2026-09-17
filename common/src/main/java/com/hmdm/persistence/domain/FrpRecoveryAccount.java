package com.hmdm.persistence.domain;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.io.Serializable;

/** A Google account verified by OAuth and approved as an EFRP recovery account for one customer. */
@JsonIgnoreProperties(ignoreUnknown = true)
public class FrpRecoveryAccount implements Serializable {
    private Integer id;
    private int customerId;
    private String googleUserId;
    private String email;
    private Integer connectedByUserId;
    private long connectedAt;

    public Integer getId() { return id; }
    public void setId(Integer id) { this.id = id; }
    public int getCustomerId() { return customerId; }
    public void setCustomerId(int customerId) { this.customerId = customerId; }
    public String getGoogleUserId() { return googleUserId; }
    public void setGoogleUserId(String googleUserId) { this.googleUserId = googleUserId; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public Integer getConnectedByUserId() { return connectedByUserId; }
    public void setConnectedByUserId(Integer connectedByUserId) { this.connectedByUserId = connectedByUserId; }
    public long getConnectedAt() { return connectedAt; }
    public void setConnectedAt(long connectedAt) { this.connectedAt = connectedAt; }
}

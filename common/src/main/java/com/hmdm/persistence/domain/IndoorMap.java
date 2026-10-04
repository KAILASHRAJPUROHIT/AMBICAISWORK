package com.hmdm.persistence.domain;

import java.io.Serializable;

/**
 * A customer's indoor floor plan: the plan geometry as JSON text (size in metres, walls, named zones, north offset)
 * and the plan picture as a data URL. The picture is for the console only and is never sent to devices.
 */
public class IndoorMap implements Serializable {
    private static final long serialVersionUID = 1L;
    private Integer customerId;
    private String plan;
    private String image;
    private Long updatedAt;

    public Integer getCustomerId() { return customerId; }
    public void setCustomerId(Integer v) { this.customerId = v; }
    public String getPlan() { return plan; }
    public void setPlan(String v) { this.plan = v; }
    public String getImage() { return image; }
    public void setImage(String v) { this.image = v; }
    public Long getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Long v) { this.updatedAt = v; }
}

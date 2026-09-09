package com.hmdm.persistence.domain;

import java.io.Serializable;

/**
 * A customer-scoped admin-alert rule: when a device event of {@code eventType} fires,
 * notify {@code webhookUrl} and/or {@code email} (either may be blank, but not both).
 * {@code eventType} matches the same vocabulary as {@code device_event.type} (see the
 * console's EVENT_VERBS); a null/empty {@code eventType} means "any event type".
 */
public class AlertRule implements Serializable {

    private static final long serialVersionUID = 1L;

    private Integer id;
    private int customerId;
    private String eventType;
    private String webhookUrl;
    private String email;
    private boolean enabled = true;
    private long createdAt;

    public AlertRule() {
    }

    public Integer getId() {
        return id;
    }

    public void setId(Integer id) {
        this.id = id;
    }

    public int getCustomerId() {
        return customerId;
    }

    public void setCustomerId(int customerId) {
        this.customerId = customerId;
    }

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    public String getWebhookUrl() {
        return webhookUrl;
    }

    public void setWebhookUrl(String webhookUrl) {
        this.webhookUrl = webhookUrl;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public long getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(long createdAt) {
        this.createdAt = createdAt;
    }
}

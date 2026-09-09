package com.hmdm.rest.json.agent;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Getter;
import lombok.Setter;

/**
 * <p>Request body for {@code POST /public/agent/v1/enrollByCredentials} — the "Lite" enrollment
 * path (Device Admin only, no factory reset). Authenticates against the same admin-console
 * login (email/username + master password) instead of a pre-minted single-use token.</p>
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonIgnoreProperties(ignoreUnknown = true)
public class AgentEnrollByCredentialsRequest {

    private String protocolVersion = AgentProtocol.VERSION;

    /** Login or email of an existing console user. */
    private String email;

    private String password;

    /** Stable, permission-free device identifier (enrollment-specific id / ANDROID_ID). */
    private String hardwareId;

    private AgentInfo agent;

    private AgentDeviceInfo device;

    private AgentCapabilities capabilities;

    public AgentEnrollByCredentialsRequest() {
    }
}

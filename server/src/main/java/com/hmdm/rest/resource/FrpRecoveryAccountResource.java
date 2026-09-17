package com.hmdm.rest.resource;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.FrpRecoveryAccountDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.AgentCommand;
import com.hmdm.persistence.domain.Device;
import com.hmdm.persistence.domain.FrpRecoveryAccount;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;
import com.hmdm.service.GoogleFrpOAuthService;
import org.json.JSONObject;

import javax.ws.rs.DELETE;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

/** Tenant-only FRP recovery account management and safe device policy dispatch. */
@Singleton
@Path("/private/agent/v1/frp")
public class FrpRecoveryAccountResource {
    private final FrpRecoveryAccountDAO accounts;
    private final GoogleFrpOAuthService oauth;
    private final AgentCommandDAO commands;
    private final UnsecureDAO devices;

    @Inject
    public FrpRecoveryAccountResource(FrpRecoveryAccountDAO accounts, GoogleFrpOAuthService oauth,
                                      AgentCommandDAO commands, UnsecureDAO devices) {
        this.accounts = accounts; this.oauth = oauth; this.commands = commands; this.devices = devices;
    }

    @GET @Path("/accounts") @Produces(MediaType.APPLICATION_JSON)
    public Response list() {
        Optional<Integer> customerId = currentCustomer();
        return customerId.isPresent() ? Response.OK(accounts.list(customerId.get())) : Response.PERMISSION_DENIED();
    }

    /** Returns a Google authorization URL. UI opens it in the current browser; password stays on Google. */
    @POST @Path("/accounts/connect") @Produces(MediaType.APPLICATION_JSON)
    public Response connect() {
        Optional<Integer> customerId = currentCustomer();
        if (!customerId.isPresent() || !canEdit()) return Response.PERMISSION_DENIED();
        try {
            Integer userId = SecurityContext.get().getCurrentUser().map(u -> u.getId()).orElse(null);
            return Response.OK(Collections.singletonMap("authorizationUrl", oauth.begin(customerId.get(), userId)));
        } catch (IllegalStateException e) {
            return Response.ERROR(e.getMessage());
        }
    }

    @DELETE @Path("/accounts/{id}") @Produces(MediaType.APPLICATION_JSON)
    public Response remove(@PathParam("id") int id) {
        Optional<Integer> customerId = currentCustomer();
        if (!customerId.isPresent() || !canEdit()) return Response.PERMISSION_DENIED();
        return accounts.delete(id, customerId.get()) ? Response.OK() : Response.OBJECT_NOT_FOUND_ERROR();
    }

    /** Queues an explicit ID-bearing command. Android rejects any legacy on/off FRP command. */
    @POST @Path("/devices/{deviceId}/apply") @Produces(MediaType.APPLICATION_JSON)
    public Response apply(@PathParam("deviceId") String deviceId) {
        Optional<Integer> customerId = currentCustomer();
        if (!customerId.isPresent() || !canEdit()) return Response.PERMISSION_DENIED();
        Device device = devices.getDeviceByNumber(deviceId);
        if (device == null) return Response.DEVICE_NOT_FOUND_ERROR();
        if (device.getCustomerId() != customerId.get()) return Response.PERMISSION_DENIED();
        List<FrpRecoveryAccount> configured = accounts.list(customerId.get());
        if (configured.isEmpty()) return Response.ERROR("Connect at least one Google recovery account before enabling FRP");
        org.json.JSONArray ids = new org.json.JSONArray();
        for (FrpRecoveryAccount account : configured) ids.put(account.getGoogleUserId());
        AgentCommand command = new AgentCommand();
        command.setDeviceNumber(deviceId);
        command.setType("policy.apply");
        command.setPayload(new JSONObject().put("policy", "factoryResetProtection").put("value", true)
                .put("recoveryAccountIds", ids).toString());
        command.setRequiresCapability("factoryResetProtection");
        command.setStatus("pending");
        command.setCreatedAt(System.currentTimeMillis());
        commands.insert(command);
        return Response.OK(command);
    }

    private static Optional<Integer> currentCustomer() {
        return SecurityContext.get() == null ? Optional.<Integer>empty() : SecurityContext.get().getCurrentCustomerId();
    }
    private static boolean canEdit() { return SecurityContext.get() != null && SecurityContext.get().hasPermission("edit_devices"); }
}

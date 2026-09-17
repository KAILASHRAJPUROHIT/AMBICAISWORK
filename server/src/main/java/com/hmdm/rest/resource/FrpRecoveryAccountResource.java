package com.hmdm.rest.resource;

import javax.inject.Inject;
import javax.inject.Singleton;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.FrpRecoveryAccountDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.AgentCommand;
import com.hmdm.persistence.domain.Device;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;
import com.hmdm.service.FrpApplyService;
import com.hmdm.service.GoogleFrpOAuthService;

import javax.ws.rs.DELETE;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import java.util.Collections;
import java.util.Optional;

/** Tenant-only FRP recovery account management and safe device policy dispatch. */
@Singleton
@Path("/private/agent/v1/frp")
public class FrpRecoveryAccountResource {
    private final FrpRecoveryAccountDAO accounts;
    private final GoogleFrpOAuthService oauth;
    private final FrpApplyService applyService;
    private final UnsecureDAO devices;
    private final AgentCommandDAO commands;

    @Inject
    public FrpRecoveryAccountResource(FrpRecoveryAccountDAO accounts, GoogleFrpOAuthService oauth,
                                      FrpApplyService applyService, UnsecureDAO devices, AgentCommandDAO commands) {
        this.accounts = accounts; this.oauth = oauth; this.applyService = applyService;
        this.devices = devices; this.commands = commands;
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
        AgentCommand command = applyService.queueIfAccountsConnected(customerId.get(), deviceId);
        if (command == null) return Response.ERROR("Connect at least one Google recovery account before enabling FRP");
        return Response.OK(command);
    }

    /** Device numbers with an FRP-enable command queued but not yet done - drives the "FRP pending" badge. */
    @GET @Path("/pending-devices") @Produces(MediaType.APPLICATION_JSON)
    public Response pendingDevices() {
        Optional<Integer> customerId = currentCustomer();
        return customerId.isPresent() ? Response.OK(commands.listPendingFrpDeviceNumbers(customerId.get())) : Response.PERMISSION_DENIED();
    }

    private static Optional<Integer> currentCustomer() {
        return SecurityContext.get() == null ? Optional.<Integer>empty() : SecurityContext.get().getCurrentCustomerId();
    }
    private static boolean canEdit() { return SecurityContext.get() != null && SecurityContext.get().hasPermission("edit_devices"); }
}

package com.hmdm.rest.resource;

import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.LeaderboardDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.Device;
import com.hmdm.persistence.domain.LeaderboardSnapshot;
import com.hmdm.util.AgentAuth;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.GET;
import javax.ws.rs.HeaderParam;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.QueryParam;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;

/**
 * The tablets' 30-second leaderboard poll. Device-authenticated exactly like check-in
 * ({@code Authorization: Bearer <deviceSecret>} + the device number), and returns only the
 * latest snapshot of that device's own customer. Unknown device and bad secret are one
 * indistinguishable 401 (no enumeration oracle on a public endpoint).
 */
@Singleton
@Path("/public/agent/v1/leaderboard")
public class LeaderboardReadResource {

    private final UnsecureDAO unsecureDAO;
    private final AgentCommandDAO commandDAO;
    private final LeaderboardDAO dao;

    @Inject
    public LeaderboardReadResource(UnsecureDAO unsecureDAO, AgentCommandDAO commandDAO, LeaderboardDAO dao) {
        this.unsecureDAO = unsecureDAO;
        this.commandDAO = commandDAO;
        this.dao = dao;
    }

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response latest(@HeaderParam("Authorization") String authorization,
                           @QueryParam("deviceId") String deviceId) {
        Device device = deviceId == null ? null : unsecureDAO.getDeviceByNumber(deviceId);
        if (device == null || !AgentAuth.authenticate(authorization, deviceId, commandDAO)) {
            return Response.status(Response.Status.UNAUTHORIZED).build();
        }
        LeaderboardSnapshot s = dao.find(device.getCustomerId());
        String data = s == null ? "null" : "{\"receivedAt\":" + s.getReceivedAt() + ",\"board\":" + s.getPayload() + "}";
        return Response.ok("{\"status\":\"OK\",\"message\":null,\"data\":" + data + "}")
                .type(MediaType.APPLICATION_JSON)
                .header("Cache-Control", "no-store")
                .build();
    }
}

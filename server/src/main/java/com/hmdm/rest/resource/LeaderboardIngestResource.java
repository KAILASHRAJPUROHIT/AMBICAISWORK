package com.hmdm.rest.resource;

import com.hmdm.persistence.LeaderboardDAO;
import com.hmdm.persistence.RolloutDAO;
import com.hmdm.persistence.domain.LeaderboardSnapshot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.Consumes;
import javax.ws.rs.HeaderParam;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

/**
 * Receives the sales leaderboard pushed every ~30s by the collector running on the shop server
 * (the shop LAN is not reachable from AWS, so push is the only workable direction).
 *
 * <p>Authenticated by a dedicated shared secret in {@code X-Collector-Token}, compared against the
 * server's {@code MDM_COLLECTOR_TOKEN} environment variable in constant time. With no token
 * configured the endpoint is disabled (503), never open. The snapshot belongs to the only customer
 * that has devices, or to {@code MDM_COLLECTOR_CUSTOMER_ID} when several do.</p>
 */
@Singleton
@Path("/public/collector/v1/leaderboard")
public class LeaderboardIngestResource {

    private static final Logger log = LoggerFactory.getLogger(LeaderboardIngestResource.class);

    private final LeaderboardDAO dao;
    private final RolloutDAO rolloutDAO;

    @Inject
    public LeaderboardIngestResource(LeaderboardDAO dao, RolloutDAO rolloutDAO) {
        this.dao = dao;
        this.rolloutDAO = rolloutDAO;
    }

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response ingest(@HeaderParam("X-Collector-Token") String token, String body) {
        String expected = System.getenv("MDM_COLLECTOR_TOKEN");
        if (expected == null || expected.trim().length() < 16) {
            return Response.status(Response.Status.SERVICE_UNAVAILABLE)
                    .entity("{\"message\":\"collector ingest is not configured\"}").build();
        }
        if (token == null || !MessageDigest.isEqual(
                token.trim().getBytes(StandardCharsets.UTF_8), expected.trim().getBytes(StandardCharsets.UTF_8))) {
            log.warn("Leaderboard ingest rejected: bad collector token");
            return Response.status(Response.Status.UNAUTHORIZED).build();
        }
        LeaderboardPayload p = LeaderboardPayload.parse(body);
        if (p == null) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity("{\"message\":\"invalid leaderboard payload\"}").type(MediaType.APPLICATION_JSON).build();
        }
        Integer customerId = customerId();
        if (customerId == null) {
            return Response.status(Response.Status.CONFLICT)
                    .entity("{\"message\":\"cannot determine the customer\"}").type(MediaType.APPLICATION_JSON).build();
        }
        LeaderboardSnapshot s = new LeaderboardSnapshot();
        s.setCustomerId(customerId);
        s.setBusinessDate(p.businessDate);
        s.setGeneratedAt(p.generatedAt);
        s.setPayload(p.json);
        s.setReceivedAt(System.currentTimeMillis());
        dao.upsert(s);
        return Response.ok("{\"status\":\"OK\"}").type(MediaType.APPLICATION_JSON).build();
    }

    private Integer customerId() {
        String forced = System.getenv("MDM_COLLECTOR_CUSTOMER_ID");
        if (forced != null && forced.trim().matches("\\d+")) return Integer.valueOf(forced.trim());
        List<Integer> ids = rolloutDAO.listCustomerIdsWithDevices();
        return ids != null && ids.size() == 1 ? ids.get(0) : null;
    }
}

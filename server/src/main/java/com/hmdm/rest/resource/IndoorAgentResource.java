package com.hmdm.rest.resource;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.IndoorDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.Device;
import com.hmdm.persistence.domain.IndoorFingerprint;
import com.hmdm.persistence.domain.IndoorMap;
import com.hmdm.util.AgentAuth;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.Consumes;
import javax.ws.rs.GET;
import javax.ws.rs.HeaderParam;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.QueryParam;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Device side of in-store positioning. Device-authenticated exactly like check-in
 * ({@code Authorization: Bearer <deviceSecret>} + the device number); unknown device and bad secret are one
 * indistinguishable 401. A device only ever sees its own customer's plan and survey, and never the plan picture.
 */
@Singleton
@Path("/public/agent/v1/indoor")
public class IndoorAgentResource {

    private static final int MAX_BODY_CHARS = 32_000;
    private static final int MAX_NETWORKS = 60;
    private static final int MAX_POINTS = 5_000;
    private static final ObjectMapper JSON = new ObjectMapper();

    private final UnsecureDAO unsecureDAO;
    private final AgentCommandDAO commandDAO;
    private final IndoorDAO dao;

    @Inject
    public IndoorAgentResource(UnsecureDAO unsecureDAO, AgentCommandDAO commandDAO, IndoorDAO dao) {
        this.unsecureDAO = unsecureDAO;
        this.commandDAO = commandDAO;
        this.dao = dao;
    }

    /** The plan geometry and every surveyed point, for the on-device positioning engine. */
    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response bundle(@HeaderParam("Authorization") String authorization,
                           @QueryParam("deviceId") String deviceId) {
        Device device = authenticated(authorization, deviceId);
        if (device == null) return Response.status(Response.Status.UNAUTHORIZED).build();
        IndoorMap map = dao.findMap(device.getCustomerId());
        if (map == null || map.getPlan() == null) {
            return json("{\"status\":\"OK\",\"message\":null,\"data\":null}");
        }
        List<IndoorFingerprint> points = dao.listFingerprints(device.getCustomerId());
        StringBuilder sb = new StringBuilder(map.getPlan().length() + points.size() * 200 + 128);
        sb.append("{\"status\":\"OK\",\"message\":null,\"data\":{\"updatedAt\":").append(map.getUpdatedAt())
                .append(",\"plan\":").append(map.getPlan()).append(",\"points\":[");
        boolean first = true;
        for (IndoorFingerprint f : points) {
            if (f.getRssi() == null || f.getX() == null || f.getY() == null) continue;
            if (!first) sb.append(',');
            first = false;
            sb.append("{\"x\":").append(f.getX()).append(",\"y\":").append(f.getY())
                    .append(",\"rssi\":").append(f.getRssi());
            if (f.getMag() != null) sb.append(",\"mag\":").append(f.getMag());
            sb.append('}');
        }
        sb.append("]}}");
        return json(sb.toString());
    }

    /** Records one surveyed point. Body: {"deviceId","x","y","rssi":{"bssid":dBm,...},"mag":uT?}. */
    @POST @Path("/survey")
    @Consumes(MediaType.APPLICATION_JSON) @Produces(MediaType.APPLICATION_JSON)
    public Response survey(@HeaderParam("Authorization") String authorization, String body) {
        if (body == null || body.length() > MAX_BODY_CHARS) return bad("invalid survey point");
        JsonNode n;
        try {
            n = JSON.readTree(body);
        } catch (Exception e) {
            return bad("invalid survey point");
        }
        String deviceId = n == null ? null : n.path("deviceId").asText(null);
        Device device = authenticated(authorization, deviceId);
        if (device == null) return Response.status(Response.Status.UNAUTHORIZED).build();

        JsonNode rssi = n.path("rssi");
        if (!n.path("x").isNumber() || !n.path("y").isNumber() || !rssi.isObject() || rssi.size() == 0
                || rssi.size() > MAX_NETWORKS) {
            return bad("invalid survey point");
        }
        IndoorMap map = dao.findMap(device.getCustomerId());
        if (map == null) return bad("no floor plan has been set up yet");
        double x = n.path("x").asDouble();
        double y = n.path("y").asDouble();
        JsonNode plan;
        try {
            plan = JSON.readTree(map.getPlan());
        } catch (Exception e) {
            return bad("the stored floor plan is unreadable");
        }
        if (x < 0 || y < 0 || x > plan.path("widthM").asDouble() || y > plan.path("heightM").asDouble()) {
            return bad("point is outside the floor plan");
        }
        if (dao.countFingerprints(device.getCustomerId()) >= MAX_POINTS) return bad("survey is full");
        // Re-serialise only validated numeric readings, so the stored text is always safe to embed in a response.
        StringBuilder clean = new StringBuilder("{");
        boolean first = true;
        Iterator<Map.Entry<String, JsonNode>> it = rssi.fields();
        while (it.hasNext()) {
            Map.Entry<String, JsonNode> e = it.next();
            if (!e.getValue().isNumber() || !e.getKey().matches("[0-9a-f]{2}(:[0-9a-f]{2}){5}")) continue;
            int dbm = e.getValue().asInt();
            if (dbm > 0 || dbm < -127) continue;
            if (!first) clean.append(',');
            first = false;
            clean.append('"').append(e.getKey()).append("\":").append(dbm);
        }
        clean.append('}');
        if (first) return bad("no usable Wi-Fi readings");

        IndoorFingerprint f = new IndoorFingerprint();
        f.setCustomerId(device.getCustomerId());
        f.setX(x);
        f.setY(y);
        f.setRssi(clean.toString());
        f.setMag(n.path("mag").isNumber() ? n.path("mag").asDouble() : null);
        f.setCreatedAt(System.currentTimeMillis());
        f.setCreatedBy(deviceId);
        dao.addFingerprint(f);
        return json("{\"status\":\"OK\",\"message\":null,\"data\":null}");
    }

    private Device authenticated(String authorization, String deviceId) {
        if (deviceId == null || deviceId.isEmpty()) return null;
        Device device = unsecureDAO.getDeviceByNumber(deviceId);
        if (device == null || !AgentAuth.authenticate(authorization, deviceId, commandDAO)) return null;
        return device;
    }

    private static Response json(String body) {
        return Response.ok(body).type(MediaType.APPLICATION_JSON).header("Cache-Control", "no-store").build();
    }

    private static Response bad(String message) {
        return Response.status(Response.Status.BAD_REQUEST)
                .entity("{\"status\":\"ERROR\",\"message\":\"" + message + "\",\"data\":null}")
                .type(MediaType.APPLICATION_JSON).build();
    }
}

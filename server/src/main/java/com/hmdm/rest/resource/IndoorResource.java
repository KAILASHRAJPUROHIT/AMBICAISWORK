package com.hmdm.rest.resource;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hmdm.persistence.IndoorDAO;
import com.hmdm.persistence.domain.IndoorMap;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.Consumes;
import javax.ws.rs.DELETE;
import javax.ws.rs.GET;
import javax.ws.rs.PUT;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * Console side of in-store positioning: the floor plan (geometry + picture) and the surveyed Wi-Fi fingerprints.
 * Tenant-scoped; changes need the same permission as editing devices.
 */
@Singleton
@Path("/private/indoor/v1")
public class IndoorResource {

    private static final int MAX_PLAN_CHARS = 200_000;
    private static final int MAX_IMAGE_CHARS = 3_000_000;
    private static final ObjectMapper JSON = new ObjectMapper();

    private final IndoorDAO dao;

    @Inject
    public IndoorResource(IndoorDAO dao) { this.dao = dao; }

    /** The whole indoor setup: plan JSON text, picture data URL, and every surveyed point. */
    @GET @Path("/map") @Produces(MediaType.APPLICATION_JSON)
    public Response getMap() {
        Optional<Integer> customerId = currentCustomer();
        if (!customerId.isPresent()) return Response.PERMISSION_DENIED();
        IndoorMap map = dao.findMap(customerId.get());
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("plan", map == null ? null : map.getPlan());
        out.put("image", map == null ? null : map.getImage());
        out.put("updatedAt", map == null ? null : map.getUpdatedAt());
        out.put("points", dao.listFingerprints(customerId.get()));
        return Response.OK(out);
    }

    /** Saves the plan geometry and (optionally) the picture. Body: {"plan": "<json text>", "image": "<data url>|null"}. */
    @PUT @Path("/map") @Consumes(MediaType.APPLICATION_JSON) @Produces(MediaType.APPLICATION_JSON)
    public Response saveMap(Map<String, Object> body) {
        Optional<Integer> customerId = currentCustomer();
        if (!customerId.isPresent() || !canEdit()) return Response.PERMISSION_DENIED();
        Object planObj = body == null ? null : body.get("plan");
        if (!(planObj instanceof String)) return Response.ERROR("plan is required");
        String plan = (String) planObj;
        if (plan.length() > MAX_PLAN_CHARS) return Response.ERROR("The plan is too large");
        String compact;
        try {
            JsonNode node = JSON.readTree(plan);
            if (node == null || !node.isObject() || !node.path("widthM").isNumber() || !node.path("heightM").isNumber()
                    || node.path("widthM").asDouble() <= 0 || node.path("heightM").asDouble() <= 0) {
                return Response.ERROR("The plan needs a positive widthM and heightM");
            }
            compact = JSON.writeValueAsString(node);
        } catch (Exception e) {
            return Response.ERROR("The plan is not valid JSON");
        }
        Object imageObj = body.get("image");
        String image = imageObj instanceof String ? (String) imageObj : null;
        if (image != null && image.length() > MAX_IMAGE_CHARS) return Response.ERROR("The picture is too large");
        if (image != null && !image.startsWith("data:image/")) return Response.ERROR("The picture must be an image");

        IndoorMap existing = dao.findMap(customerId.get());
        IndoorMap map = new IndoorMap();
        map.setCustomerId(customerId.get());
        map.setPlan(compact);
        // An absent image keeps the stored one; an explicit empty string clears it.
        if (imageObj == null && existing != null) {
            map.setImage(existing.getImage());
        } else {
            map.setImage(image == null || image.isEmpty() ? null : image);
        }
        map.setUpdatedAt(System.currentTimeMillis());
        dao.saveMap(map);
        return Response.OK();
    }

    @DELETE @Path("/fingerprints/{id}") @Produces(MediaType.APPLICATION_JSON)
    public Response deleteFingerprint(@PathParam("id") int id) {
        Optional<Integer> customerId = currentCustomer();
        if (!customerId.isPresent() || !canEdit()) return Response.PERMISSION_DENIED();
        return dao.deleteFingerprint(id, customerId.get()) ? Response.OK() : Response.OBJECT_NOT_FOUND_ERROR();
    }

    /** Wipes the whole survey (used before re-surveying a rearranged store). */
    @DELETE @Path("/fingerprints") @Produces(MediaType.APPLICATION_JSON)
    public Response clearFingerprints() {
        Optional<Integer> customerId = currentCustomer();
        if (!customerId.isPresent() || !canEdit()) return Response.PERMISSION_DENIED();
        return Response.OK(dao.clearFingerprints(customerId.get()));
    }

    private static Optional<Integer> currentCustomer() {
        return SecurityContext.get() == null ? Optional.<Integer>empty() : SecurityContext.get().getCurrentCustomerId();
    }

    private static boolean canEdit() {
        return SecurityContext.get() != null && SecurityContext.get().hasPermission("edit_devices");
    }
}

package com.hmdm.rest.resource;

import com.hmdm.persistence.ConsoleDeviceDAO;
import com.hmdm.persistence.domain.ConsoleTrustedDevice;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;
import com.hmdm.service.ConsoleDeviceGuard;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.DELETE;
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** The signed-in user's allowed console computers: see them, and remove one (that computer needs a new code next time). */
@Singleton
@Path("/private/console-devices")
public class ConsoleDeviceResource {
    private final ConsoleDeviceDAO dao;
    private final ConsoleDeviceGuard guard;

    @Inject
    public ConsoleDeviceResource(ConsoleDeviceDAO dao, ConsoleDeviceGuard guard) {
        this.dao = dao;
        this.guard = guard;
    }

    @GET @Produces(MediaType.APPLICATION_JSON)
    public Response list() {
        Optional<Integer> uid = SecurityContext.get().getCurrentUser().map(u -> u.getId());
        if (!uid.isPresent()) return Response.PERMISSION_DENIED();
        List<Map<String, Object>> rows = new ArrayList<>();
        for (ConsoleTrustedDevice d : dao.listTrusted(uid.get())) {
            Map<String, Object> m = new HashMap<>();
            m.put("id", d.getId());
            m.put("label", d.getLabel());
            m.put("userAgent", d.getUserAgent());
            m.put("ipAddress", d.getIpAddress());
            m.put("createdAt", d.getCreatedAt());
            m.put("lastSeenAt", d.getLastSeenAt());
            rows.add(m);
        }
        Map<String, Object> out = new HashMap<>();
        out.put("devices", rows);
        out.put("enforcing", guard.enforcing());
        out.put("mode", guard.mode());
        out.put("sentTo", guard.maskedRecipient());
        return Response.OK(out);
    }

    @DELETE @Path("/{id}") @Produces(MediaType.APPLICATION_JSON)
    public Response remove(@PathParam("id") int id) {
        Optional<Integer> uid = SecurityContext.get().getCurrentUser().map(u -> u.getId());
        if (!uid.isPresent()) return Response.PERMISSION_DENIED();
        return dao.deleteTrusted(id, uid.get()) ? Response.OK() : Response.OBJECT_NOT_FOUND_ERROR();
    }
}

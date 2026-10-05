package com.hmdm.rest.resource;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;

import javax.inject.Singleton;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.regex.Pattern;

/**
 * Windows PCs in the same console as the tablets. The PCs are managed by the Windows side (OpenUEM); the
 * ambic-windows-bridge service reads them and relays commands. This resource only forwards, adding the shared
 * secret and the AMBIC permission checks. Configure with MDM_WINDOWS_BRIDGE_URL and MDM_WINDOWS_BRIDGE_TOKEN.
 */
@Singleton
@Path("/private/windows/v1")
public class WindowsResource {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Pattern ID = Pattern.compile("^[0-9a-fA-F-]{8,64}$");
    private static final Pattern ACTION = Pattern.compile("^[a-z-]{1,32}$");

    private static String setting(String name) {
        String v = System.getProperty(name);
        if (v == null || v.trim().isEmpty()) v = System.getenv(name);
        return v == null ? "" : v.trim();
    }

    @GET @Path("/status") @Produces(MediaType.APPLICATION_JSON)
    public Response status() {
        if (!canView()) return Response.PERMISSION_DENIED();
        return Response.OK(java.util.Collections.singletonMap("configured", !setting("MDM_WINDOWS_BRIDGE_URL").isEmpty()));
    }

    @GET @Path("/devices") @Produces(MediaType.APPLICATION_JSON)
    public Response list() {
        if (!canView()) return Response.PERMISSION_DENIED();
        return relay("GET", "/v1/devices");
    }

    @GET @Path("/devices/{id}") @Produces(MediaType.APPLICATION_JSON)
    public Response get(@PathParam("id") String id) {
        if (!canView()) return Response.PERMISSION_DENIED();
        if (!ID.matcher(id).matches()) return Response.ERROR("Invalid device id");
        return relay("GET", "/v1/devices/" + id);
    }

    @POST @Path("/devices/{id}/commands/{action}") @Produces(MediaType.APPLICATION_JSON)
    public Response command(@PathParam("id") String id, @PathParam("action") String action) {
        if (!canEdit()) return Response.PERMISSION_DENIED();
        if (!ID.matcher(id).matches() || !ACTION.matcher(action).matches()) return Response.ERROR("Invalid request");
        return relay("POST", "/v1/devices/" + id + "/commands/" + action);
    }

    private Response relay(String method, String path) {
        String base = setting("MDM_WINDOWS_BRIDGE_URL");
        String token = setting("MDM_WINDOWS_BRIDGE_TOKEN");
        if (base.isEmpty() || token.isEmpty()) return Response.ERROR("error.windows.not.configured");
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base.replaceAll("/+$", "") + path).openConnection();
            c.setRequestMethod(method);
            c.setConnectTimeout(5000);
            c.setReadTimeout(40000);
            c.setRequestProperty("Authorization", "Bearer " + token);
            if ("POST".equals(method)) { c.setDoOutput(true); c.getOutputStream().close(); }
            int code = c.getResponseCode();
            InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
            JsonNode body = in == null ? null : JSON.readTree(read(in));
            if (code >= 400) {
                String msg = body != null && body.has("error") ? body.get("error").asText() : "Windows service error " + code;
                return Response.ERROR(msg);
            }
            return Response.OK(body);
        } catch (Exception e) {
            return Response.ERROR("error.windows.unreachable");
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static byte[] read(InputStream in) throws java.io.IOException {
        try (InputStream i = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = i.read(buf)) > 0 && out.size() < (4 << 20)) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }

    private static boolean canView() { return SecurityContext.get() != null && SecurityContext.get().getCurrentCustomerId().isPresent(); }
    private static boolean canEdit() { return canView() && SecurityContext.get().hasPermission("edit_devices"); }
}

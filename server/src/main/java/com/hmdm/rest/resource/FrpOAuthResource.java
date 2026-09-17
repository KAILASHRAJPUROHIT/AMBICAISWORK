package com.hmdm.rest.resource;

import javax.inject.Inject;
import javax.inject.Singleton;
import com.hmdm.service.GoogleFrpOAuthService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.QueryParam;
import javax.ws.rs.core.MediaType;

/** Public OAuth redirect target. It does not grant a session; it only consumes a one-time state. */
@Singleton
@Path("/public/frp/oauth")
public class FrpOAuthResource {
    private static final Logger logger = LoggerFactory.getLogger(FrpOAuthResource.class);
    private final GoogleFrpOAuthService oauth;

    @Inject public FrpOAuthResource(GoogleFrpOAuthService oauth) { this.oauth = oauth; }

    @GET @Path("/callback") @Produces(MediaType.TEXT_HTML)
    public javax.ws.rs.core.Response callback(@QueryParam("state") String state, @QueryParam("code") String code,
                                               @QueryParam("error") String error) {
        if (error != null && !error.isEmpty()) return page(false, "Google account connection was cancelled or denied.");
        try {
            oauth.complete(state, code);
            return page(true, "Google recovery account connected. Return to AMBIC MDM and apply FRP to the intended devices.");
        } catch (Exception e) {
            logger.warn("FRP Google OAuth callback rejected: {}", e.getMessage());
            return page(false, "Google account connection failed. Return to AMBIC MDM and try again.");
        }
    }

    private static javax.ws.rs.core.Response page(boolean success, String message) {
        String colour = success ? "#157347" : "#b42318";
        String body = "<!doctype html><title>AMBIC MDM</title><main style='font-family:system-ui;max-width:600px;margin:10vh auto;padding:24px'>"
                + "<h1 style='color:" + colour + "'>" + (success ? "Connected" : "Not connected") + "</h1><p>" + message + "</p></main>";
        return javax.ws.rs.core.Response.ok(body, MediaType.TEXT_HTML).build();
    }
}

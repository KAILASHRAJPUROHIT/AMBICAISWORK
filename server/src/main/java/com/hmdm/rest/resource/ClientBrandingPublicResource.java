package com.hmdm.rest.resource;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.security.PermitAll;
import javax.inject.Inject;
import javax.inject.Named;
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.core.Response;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;

/**
 * Unauthenticated delivery of the client branding images uploaded through
 * {@link ClientBrandingImageResource}: managed devices fetch them during check-in without admin
 * credentials. Its own root path (like every other resource) so Jersey routes to it instead of
 * the broader {@code /public} root.
 */
@Path("/public/client-branding")
public class ClientBrandingPublicResource {

    private static final Logger log = LoggerFactory.getLogger(ClientBrandingPublicResource.class);

    private final File brandingDir;

    @Inject
    public ClientBrandingPublicResource(@Named("files.directory") String filesDirectory) {
        this.brandingDir = ClientBrandingImageResource.dirFor(filesDirectory);
    }

    @GET
    @PermitAll
    @Path("/{name}")
    public Response fetch(@PathParam("name") String name) {
        String slot = ClientBrandingImageResource.normaliseSlot(ClientBrandingImageResource.stripPng(name));
        if (slot == null) {
            return Response.status(Response.Status.NOT_FOUND).build();
        }
        File file = new File(brandingDir, slot + ".png");
        if (!file.isFile()) {
            return Response.status(Response.Status.NOT_FOUND).build();
        }
        byte[] bytes;
        try {
            bytes = Files.readAllBytes(file.toPath());
        } catch (IOException e) {
            log.error("Cannot read stored client branding image", e);
            return Response.status(Response.Status.INTERNAL_SERVER_ERROR).build();
        }
        return Response.ok(bytes)
                .type("image/png")
                // The URL stays stable across re-uploads, so devices are told to re-fetch.
                .header("Cache-Control", "no-cache")
                .build();
    }
}

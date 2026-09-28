package com.hmdm.rest.resource;

import com.hmdm.security.SecurityContext;
import org.glassfish.jersey.media.multipart.FormDataContentDisposition;
import org.glassfish.jersey.media.multipart.FormDataParam;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.security.PermitAll;
import javax.inject.Inject;
import javax.inject.Named;
import javax.ws.rs.Consumes;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.Locale;

/**
 * Storage and public delivery for client branding images (the customer's logo and emblem).
 *
 * <p>Upload is console-only ({@code /private/...}); delivery is unauthenticated under
 * {@code /public/...} because managed devices fetch the image during check-in without admin
 * credentials. Only PNG is accepted, and the stored name is fixed per slot so a re-upload
 * replaces rather than accumulates.
 */
@Path("/")
public class ClientBrandingImageResource {

    private static final Logger log = LoggerFactory.getLogger(ClientBrandingImageResource.class);

    /** Generous ceiling; a retail logo is a few tens of KB. Guards against a hostile upload. */
    private static final long MAX_BYTES = 4L * 1024 * 1024;

    /** PNG signature, compared byte-wise so a locale or encoding cannot affect it. */
    private static final byte[] PNG_MAGIC = {
            (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A
    };

    private final File brandingDir;

    @Inject
    public ClientBrandingImageResource(@Named("files.directory") String filesDirectory) {
        this.brandingDir = new File(filesDirectory, "client-branding");
    }

    // ------------------------------------------------------------------ upload

    @POST
    @Consumes(MediaType.MULTIPART_FORM_DATA)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/private/settings/clientBranding/image")
    public Response upload(@FormDataParam("file") InputStream in,
                            @FormDataParam("file") FormDataContentDisposition detail,
                            @FormDataParam("kind") String kind) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to upload client branding image by user "
                    + SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        String slot = normaliseSlot(kind);
        if (slot == null) {
            return badRequest("kind must be 'logo' or 'mark'");
        }
        if (in == null || detail == null) {
            return badRequest("file is required");
        }
        try {
            byte[] bytes = readCapped(in);
            if (bytes == null) {
                return Response.status(Response.Status.REQUEST_ENTITY_TOO_LARGE)
                        .entity("{\"message\":\"image exceeds 4 MB\"}")
                        .type(MediaType.APPLICATION_JSON).build();
            }
            if (!isPng(bytes)) {
                return badRequest("only PNG images are accepted");
            }
            if (!brandingDir.isDirectory() && !brandingDir.mkdirs()) {
                throw new IOException("cannot create " + brandingDir);
            }
            File target = new File(brandingDir, slot + ".png");
            File tmp = new File(brandingDir, slot + ".png.tmp");
            try (OutputStream out = new FileOutputStream(tmp)) {
                out.write(bytes);
            }

    // ------------------------------------------------------------------ delivery

    @GET
    @PermitAll
    @Path("/public/client-branding/{name}")
    public Response fetch(@PathParam("name") String name) {
        String slot = normaliseSlot(stripPng(name));
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
            return Response.INTERNAL_SERVER_ERROR();
        }
        return Response.ok(bytes)
                .type("image/png")
                // The URL stays stable across re-uploads, so devices are told to re-fetch.
                .header("Cache-Control", "no-cache")
                .build();
    }

    // ------------------------------------------------------------------ helpers

    private static Response badRequest(String message) {
        return Response.status(Response.Status.BAD_REQUEST)
                .entity("{\"message\":\"" + message + "\"}")
                .type(MediaType.APPLICATION_JSON).build();
    }

    private static String normaliseSlot(String kind) {
        if (kind == null) return null;
        String k = kind.trim().toLowerCase(Locale.ROOT);
        return ("logo".equals(k) || "mark".equals(k)) ? k : null;
    }

    private static String stripPng(String name) {
        if (name == null) return null;
        String n = name.trim();
        return n.toLowerCase(Locale.ROOT).endsWith(".png")
                ? n.substring(0, n.length() - 4) : n;
    }

    private static String publicPath(String slot) {
        return "/public/client-branding/" + slot + ".png";
    }

    /** Reads at most {@link #MAX_BYTES}; returns null when the stream is larger. */
    private static byte[] readCapped(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int read;
        long total = 0;
        while ((read = in.read(chunk)) != -1) {
            total += read;
            if (total > MAX_BYTES) return null;
            buffer.write(chunk, 0, read);
        }
        return buffer.toByteArray();
    }

    private static boolean isPng(byte[] bytes) {
        if (bytes.length < PNG_MAGIC.length) return false;
        for (int i = 0; i < PNG_MAGIC.length; i++) {
            if (bytes[i] != PNG_MAGIC[i]) return false;
        }
        return true;
    }
}

            // Replace atomically so a device never fetches a half-written image.
            Files.move(tmp.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING);
            log.info("Client branding '{}' image stored ({} bytes)", slot, bytes.length);
            return Response.ok("{\"path\":\"" + publicPath(slot) + "\"}")
                    .type(MediaType.APPLICATION_JSON).build();
        } catch (Exception e) {
            log.error("Unexpected error when storing client branding image", e);
            return Response.INTERNAL_ERROR();
        }
    }

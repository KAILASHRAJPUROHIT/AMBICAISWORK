/*
 *
 * Headwind MDM: Open Source Android MDM Software
 * https://h-mdm.com
 *
 * Copyright (C) 2019 Headwind Solutions LLC (http://h-sms.com)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *       http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */

package com.hmdm.rest.resource;

import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.RemoteSnapshotDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.Device;
import com.hmdm.persistence.domain.RemoteSnapshot;
import com.hmdm.rest.json.Response;
import com.hmdm.util.AgentAuth;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.glassfish.jersey.media.multipart.FormDataParam;
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
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Set;

/**
 * <p>Device-authenticated (not an admin session — same {@code Authorization: Bearer <deviceSecret>}
 * check as checkin) endpoint the agent uploads its own remote-view captures to. Deliberately under
 * {@code /public/agent/v1/...} for the same reason {@link AgentResource#checkin} is — the caller is
 * the device itself, which never holds an admin session cookie — but "public" here means
 * unauthenticated-by-session, not unauthenticated-by-anything: {@link AgentAuth#authenticate} still
 * gates every call.</p>
 */
@Singleton
@Path("/public/agent/v1/remote")
@Api(tags = {"Agent v1 remote view"})
public class RemoteSnapshotUploadResource {

    private static final Logger logger = LoggerFactory.getLogger(RemoteSnapshotUploadResource.class);
    private static final Set<String> KNOWN_KINDS = Set.of("screen", "cameraFront", "cameraBack", "mic");
    // Generous for a compressed JPEG screenshot/photo or a short audio clip, small enough that a
    // misbehaving/malicious client can't use this as an unbounded upload sink.
    private static final int MAX_BYTES = 8 * 1024 * 1024;

    private UnsecureDAO unsecureDAO;
    private AgentCommandDAO commandDAO;
    private RemoteSnapshotDAO snapshotDAO;

    public RemoteSnapshotUploadResource() {
    }

    @Inject
    public RemoteSnapshotUploadResource(UnsecureDAO unsecureDAO, AgentCommandDAO commandDAO, RemoteSnapshotDAO snapshotDAO) {
        this.unsecureDAO = unsecureDAO;
        this.commandDAO = commandDAO;
        this.snapshotDAO = snapshotDAO;
    }

    // =================================================================================================================
    @ApiOperation(value = "Upload a remote-view snapshot", notes = "Overwrites this device's latest capture for the given kind.")
    @POST
    @Path("/snapshot")
    @Consumes(MediaType.MULTIPART_FORM_DATA)
    @Produces(MediaType.APPLICATION_JSON)
    public Response upload(
            @HeaderParam("Authorization") String authorization,
            @FormDataParam("deviceNumber") String deviceNumber,
            @FormDataParam("kind") String kind,
            @FormDataParam("contentType") String contentType,
            @FormDataParam("file") InputStream fileStream) {
        if (deviceNumber == null || deviceNumber.trim().isEmpty()) {
            return Response.ERROR("error.remote.device.missing");
        }
        if (!AgentAuth.authenticate(authorization, deviceNumber, commandDAO)) {
            return Response.PERMISSION_DENIED();
        }
        if (kind == null || !KNOWN_KINDS.contains(kind)) {
            return Response.ERROR("error.remote.kind.invalid");
        }
        if (fileStream == null) {
            return Response.ERROR("error.remote.file.missing");
        }
        Device device = unsecureDAO.getDeviceByNumber(deviceNumber);
        if (device == null) {
            return Response.ERROR("error.agent.device.unknown");
        }

        byte[] data;
        try {
            data = readBounded(fileStream, MAX_BYTES);
        } catch (IOException e) {
            logger.warn("Remote snapshot upload for {} failed to read: {}", deviceNumber, e.getMessage());
            return Response.ERROR("error.remote.file.read");
        }
        if (data.length == 0) {
            return Response.ERROR("error.remote.file.empty");
        }

        RemoteSnapshot snapshot = new RemoteSnapshot();
        snapshot.setCustomerId(device.getCustomerId());
        snapshot.setDeviceNumber(deviceNumber);
        snapshot.setKind(kind);
        snapshot.setCapturedAt(System.currentTimeMillis());
        snapshot.setContentType(contentType != null && !contentType.isBlank() ? contentType : defaultContentType(kind));
        snapshot.setData(data);
        snapshotDAO.upsert(snapshot);

        return Response.OK();
    }

    private static String defaultContentType(String kind) {
        return "mic".equals(kind) ? "audio/aac" : "image/jpeg";
    }

    /** Reads at most {@code maxBytes}+1 (to detect overflow) so an oversized upload is rejected
     *  without ever buffering an unbounded amount of attacker-controlled data first. */
    private static byte[] readBounded(InputStream in, int maxBytes) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream(Math.min(maxBytes, 65536));
        byte[] buf = new byte[8192];
        int total = 0;
        int n;
        while ((n = in.read(buf)) != -1) {
            total += n;
            if (total > maxBytes) {
                throw new IOException("upload exceeds " + maxBytes + " bytes");
            }
            out.write(buf, 0, n);
        }
        return out.toByteArray();
    }
}

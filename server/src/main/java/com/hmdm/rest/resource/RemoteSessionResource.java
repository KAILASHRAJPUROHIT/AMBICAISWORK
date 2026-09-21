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

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.hmdm.notification.AgentWakeHub;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.RemoteSnapshotDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.AgentCommand;
import com.hmdm.persistence.domain.Device;
import com.hmdm.persistence.domain.RemoteSnapshot;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.Consumes;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.StreamingOutput;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * <p>Admin-facing control for the time-boxed "remote view" session: periodic screen/front-camera/
 * back-camera/mic capture, started/stopped like any other opaque agent command, with the latest
 * capture per kind readable back here. Not continuous live video/audio — see
 * {@code docs/REMOTE-VIEW.md} for why (Android gives a non-privileged Device-Owner app no silent
 * path to true live streaming; periodic snapshots are what's actually achievable, and Android's own
 * camera/mic-in-use indicator is unavoidable regardless of approach).</p>
 *
 * <p>Snapshot bytes are never exposed at a public URL — {@link #snapshotBytes} is a private,
 * session-authenticated endpoint (same as every other {@code /private/...} resource); the browser's
 * same-origin session cookie is what makes an {@code <img src="...">} tag work here without a
 * separate token.</p>
 */
@Singleton
@Path("/private/agent/v1/devices/{deviceId}/remote")
@Api(tags = {"Agent v1 remote view"})
public class RemoteSessionResource {

    private static final Logger logger = LoggerFactory.getLogger(RemoteSessionResource.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final java.util.Set<String> KNOWN_KINDS = java.util.Set.of("screen", "cameraFront", "cameraBack", "mic");

    private UnsecureDAO unsecureDAO;
    private AgentCommandDAO commandDAO;
    private RemoteSnapshotDAO snapshotDAO;
    private AgentWakeHub wakeHub;

    public RemoteSessionResource() {
    }

    @Inject
    public RemoteSessionResource(UnsecureDAO unsecureDAO, AgentCommandDAO commandDAO,
                                  RemoteSnapshotDAO snapshotDAO, AgentWakeHub wakeHub) {
        this.unsecureDAO = unsecureDAO;
        this.commandDAO = commandDAO;
        this.snapshotDAO = snapshotDAO;
        this.wakeHub = wakeHub;
    }

    public static class StartRequest {
        private Integer durationSec;
        private Integer intervalSec;
        private List<String> kinds;

        public Integer getDurationSec() { return durationSec; }
        public void setDurationSec(Integer v) { this.durationSec = v; }
        public Integer getIntervalSec() { return intervalSec; }
        public void setIntervalSec(Integer v) { this.intervalSec = v; }
        public List<String> getKinds() { return kinds; }
        public void setKinds(List<String> v) { this.kinds = v; }
    }

    public static class InputRequest {
        private String action; // "tap", "swipe", "key"
        private Float x;
        private Float y;
        private Float endX;
        private Float endY;
        private Long durationMs;
        private String key;

        public String getAction() { return action; }
        public void setAction(String action) { this.action = action; }
        public Float getX() { return x; }
        public void setX(Float x) { this.x = x; }
        public Float getY() { return y; }
        public void setY(Float y) { this.y = y; }
        public Float getEndX() { return endX; }
        public void setEndX(Float endX) { this.endX = endX; }
        public Float getEndY() { return endY; }
        public void setEndY(Float endY) { this.endY = endY; }
        public Long getDurationMs() { return durationMs; }
        public void setDurationMs(Long durationMs) { this.durationMs = durationMs; }
        public String getKey() { return key; }
        public void setKey(String key) { this.key = key; }
    }

    // =================================================================================================================
    @ApiOperation(value = "Inject touch or key input", notes = "Injects a tap, swipe, or navigation key into the device screen.")
    @POST
    @Path("/input")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response injectInput(@PathParam("deviceId") String deviceId, InputRequest body) {
        Device device = requireOwnedDevice(deviceId);
        if (device == null) return Response.PERMISSION_DENIED();
        if (body == null || isBlank(body.getAction())) return Response.ERROR("error.input.invalid");

        ObjectNode payload = MAPPER.createObjectNode();
        payload.put("action", body.getAction());
        if (body.getX() != null) payload.put("x", body.getX());
        if (body.getY() != null) payload.put("y", body.getY());
        if (body.getEndX() != null) payload.put("endX", body.getEndX());
        if (body.getEndY() != null) payload.put("endY", body.getEndY());
        if (body.getDurationMs() != null) payload.put("durationMs", body.getDurationMs());
        if (body.getKey() != null) payload.put("key", body.getKey());

        AgentCommand command = new AgentCommand();
        command.setDeviceNumber(deviceId);
        command.setType("device.remoteInput");
        command.setPayload(payload.toString());
        command.setRequiresCapability("device.remoteSession");
        command.setStatus("pending");
        command.setCreatedAt(System.currentTimeMillis());
        commandDAO.insert(command);
        wakeHub.wake(deviceId, "interactive");

        return Response.OK();
    }

    // =================================================================================================================
    @ApiOperation(value = "Start remote view session", notes = "Begins periodic screen/camera/mic " +
            "capture on the device for a bounded duration (default 5 minutes).")
    @POST
    @Path("/start")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response start(@PathParam("deviceId") String deviceId, StartRequest body) {
        Device device = requireOwnedDevice(deviceId);
        if (device == null) return Response.PERMISSION_DENIED();

        int durationSec = clamp(body != null && body.getDurationSec() != null ? body.getDurationSec() : 300, 30, 1800);
        int intervalSec = clamp(body != null && body.getIntervalSec() != null ? body.getIntervalSec() : 3, 1, 60);
        List<String> kinds = (body != null && body.getKinds() != null && !body.getKinds().isEmpty())
                ? body.getKinds().stream().filter(KNOWN_KINDS::contains).collect(Collectors.toList())
                : List.copyOf(KNOWN_KINDS);
        if (kinds.isEmpty()) return Response.ERROR("error.remote.kinds.invalid");

        String sessionId = UUID.randomUUID().toString();
        long now = System.currentTimeMillis();
        ObjectNode payload = MAPPER.createObjectNode();
        payload.put("sessionId", sessionId);
        payload.put("durationSec", durationSec);
        payload.put("intervalSec", intervalSec);
        payload.put("expiresAt", now + durationSec * 1000L);
        com.fasterxml.jackson.databind.node.ArrayNode kindsArray = payload.putArray("kinds");
        kinds.forEach(kindsArray::add);

        AgentCommand command = new AgentCommand();
        command.setDeviceNumber(deviceId);
        command.setType("device.remoteSessionStart");
        command.setPayload(payload.toString());
        command.setRequiresCapability("device.remoteSession");
        command.setStatus("pending");
        command.setCreatedAt(now);
        commandDAO.insert(command);
        wakeHub.wake(deviceId, "interactive"); // admin is actively watching — prioritise over the batch wake

        logger.info("Remote session {} started for device {} (kinds {}, {}s @ {}s)", sessionId, deviceId, kinds, durationSec, intervalSec);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("sessionId", sessionId);
        view.put("durationSec", durationSec);
        view.put("intervalSec", intervalSec);
        view.put("kinds", kinds);
        return Response.OK(view);
    }

    // =================================================================================================================
    @ApiOperation(value = "Stop remote view session", notes = "Ends capture immediately rather than waiting for the duration to elapse.")
    @POST
    @Path("/stop")
    @Produces(MediaType.APPLICATION_JSON)
    public Response stop(@PathParam("deviceId") String deviceId) {
        Device device = requireOwnedDevice(deviceId);
        if (device == null) return Response.PERMISSION_DENIED();

        AgentCommand command = new AgentCommand();
        command.setDeviceNumber(deviceId);
        command.setType("device.remoteSessionStop");
        command.setStatus("pending");
        command.setCreatedAt(System.currentTimeMillis());
        commandDAO.insert(command);
        wakeHub.wake(deviceId, "interactive");

        logger.info("Remote session stop requested for device {}", deviceId);
        return Response.OK();
    }

    // =================================================================================================================
    @ApiOperation(value = "Latest snapshots", notes = "Metadata (kind + capture time) for whatever this device has uploaded so far.")
    @GET
    @Path("/latest")
    @Produces(MediaType.APPLICATION_JSON)
    public Response latest(@PathParam("deviceId") String deviceId) {
        Device device = requireOwnedDevice(deviceId);
        if (device == null) return Response.PERMISSION_DENIED();

        List<RemoteSnapshot> rows = snapshotDAO.listMetaByDevice(deviceId);
        List<Map<String, Object>> view = rows.stream().map(r -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("kind", r.getKind());
            m.put("capturedAt", r.getCapturedAt());
            m.put("contentType", r.getContentType());
            return m;
        }).collect(Collectors.toList());
        return Response.OK(view);
    }

    // =================================================================================================================
    @ApiOperation(value = "Snapshot bytes", notes = "The raw image/audio bytes for one kind's latest capture.")
    @GET
    @Path("/snapshot/{kind}")
    public javax.ws.rs.core.Response snapshotBytes(@PathParam("deviceId") String deviceId, @PathParam("kind") String kind) {
        Device device = requireOwnedDevice(deviceId);
        if (device == null) {
            return javax.ws.rs.core.Response.status(javax.ws.rs.core.Response.Status.FORBIDDEN).build();
        }
        RemoteSnapshot row = snapshotDAO.findByDeviceAndKind(deviceId, kind);
        if (row == null) {
            return javax.ws.rs.core.Response.status(javax.ws.rs.core.Response.Status.NOT_FOUND).build();
        }
        StreamingOutput out = output -> output.write(row.getData());
        return javax.ws.rs.core.Response.ok(out, row.getContentType())
                .header("Cache-Control", "no-store")
                .build();
    }

    // ---- helpers ----------------------------------------------------------------------------------------------------

    private Device requireOwnedDevice(String deviceNumber) {
        Optional<Integer> customerId = SecurityContext.get().getCurrentCustomerId();
        if (!customerId.isPresent()) return null;
        Device device = unsecureDAO.getDeviceByNumber(deviceNumber);
        if (device == null || device.getCustomerId() != customerId.get()) return null;
        return device;
    }

    private static int clamp(int v, int min, int max) {
        return Math.max(min, Math.min(max, v));
    }

    private static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }
}

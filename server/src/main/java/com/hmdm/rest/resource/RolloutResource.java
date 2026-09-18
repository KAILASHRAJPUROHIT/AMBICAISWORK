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
import com.hmdm.persistence.ApplicationDAO;
import com.hmdm.persistence.RolloutDAO;
import com.hmdm.persistence.domain.AgentCommand;
import com.hmdm.persistence.domain.AgentRollout;
import com.hmdm.persistence.domain.Application;
import com.hmdm.persistence.domain.ApplicationVersion;
import com.hmdm.persistence.domain.RolloutCommandStatusRow;
import com.hmdm.persistence.domain.RolloutDeviceRow;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;
import com.hmdm.util.RolloutProgress;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import javax.inject.Named;
import javax.inject.Singleton;
import javax.ws.rs.Consumes;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * <p>Admin resource for staged agent-APK rollouts (canary → fleet). Reuses the opaque
 * {@code app.install}/{@code app.silentInstall} OTA path — the command is enqueued exactly like
 * {@link AgentAdminResource#queueCommand}; progress is derived from each device's reported
 * {@code agentVersion}. Both stages are admin-gated; one active rollout per customer.</p>
 */
@Singleton
@Path("/private/agent/v1/rollout")
@Api(tags = {"Agent v1 rollout"})
public class RolloutResource {

    private static final Logger logger = LoggerFactory.getLogger(RolloutResource.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private RolloutDAO rolloutDAO;
    private AgentCommandDAO commandDAO;
    private ApplicationDAO applicationDAO;
    private AgentWakeHub wakeHub;
    private String baseUrl;

    public RolloutResource() {
    }

    @Inject
    public RolloutResource(RolloutDAO rolloutDAO, AgentCommandDAO commandDAO, ApplicationDAO applicationDAO,
                           AgentWakeHub wakeHub, @Named("base.url") String baseUrl) {
        this.rolloutDAO = rolloutDAO;
        this.commandDAO = commandDAO;
        this.applicationDAO = applicationDAO;
        this.wakeHub = wakeHub;
        this.baseUrl = baseUrl;
    }

    /** Request body for creating a rollout. */
    public static class CreateRolloutRequest {
        private String targetVersion;
        private String packageName;
        private Integer apkVersionCode;
        private String apkSha256;
        private List<String> canaryDeviceNumbers;
        // NOTE: apkUrl is deliberately NOT accepted from the client — it is built server-side from
        // base.url so a rollout can never be pointed at an attacker-controlled APK host.

        public String getTargetVersion() { return targetVersion; }
        public void setTargetVersion(String v) { this.targetVersion = v; }
        public String getPackageName() { return packageName; }
        public void setPackageName(String v) { this.packageName = v; }
        public Integer getApkVersionCode() { return apkVersionCode; }
        public void setApkVersionCode(Integer v) { this.apkVersionCode = v; }
        public String getApkSha256() { return apkSha256; }
        public void setApkSha256(String v) { this.apkSha256 = v; }
        public List<String> getCanaryDeviceNumbers() { return canaryDeviceNumbers; }
        public void setCanaryDeviceNumbers(List<String> v) { this.canaryDeviceNumbers = v; }
    }

    // =================================================================================================================
    @ApiOperation(value = "Create rollout", notes = "Start a canary-stage agent-APK rollout to the selected devices.")
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response create(CreateRolloutRequest body) {
        Optional<Integer> customerId = SecurityContext.get().getCurrentCustomerId();
        if (!customerId.isPresent()) {
            return Response.PERMISSION_DENIED();
        }
        if (body == null || isBlank(body.getTargetVersion()) || isBlank(body.getPackageName())
                || body.getApkVersionCode() == null) {
            return Response.ERROR("error.rollout.invalid");
        }
        // Require a full SHA-256 — the device verifies the APK against it; never roll out unverified.
        if (body.getApkSha256() == null || !body.getApkSha256().matches("[0-9a-fA-F]{64}")) {
            return Response.ERROR("error.rollout.sha256");
        }
        if (body.getCanaryDeviceNumbers() == null || body.getCanaryDeviceNumbers().isEmpty()) {
            return Response.ERROR("error.rollout.canary.empty");
        }
        int cust = customerId.get();
        if (rolloutDAO.findActiveByCustomerAndPackage(cust, body.getPackageName()) != null) {
            return Response.ERROR("error.rollout.active");
        }
        // Build the APK URL server-side from THIS deployment's base URL — the client never supplies a
        // host, so a rollout cannot be pointed at an attacker-controlled APK (the mirror is at
        // /update/agent.apk, proxied to the supervisor by Caddy).
        String apkUrl = baseUrl.replaceAll("/+$", "") + "/update/agent.apk?v=" + body.getApkVersionCode();

        long now = System.currentTimeMillis();
        AgentRollout r = new AgentRollout();
        r.setCustomerId(cust);
        r.setTargetVersion(body.getTargetVersion());
        r.setPackageName(body.getPackageName());
        r.setApkUrl(apkUrl);
        r.setApkSha256(body.getApkSha256());
        r.setApkVersionCode(body.getApkVersionCode());
        r.setStage("canary");
        r.setCreatedAt(now);
        r.setUpdatedAt(now);
        r.setTrackingMode("version");
        try {
            rolloutDAO.insertRollout(r);
        } catch (Exception e) {
            // The partial unique index (one active rollout per customer+package) closes the
            // check-then-act race above: two concurrent creates → the loser lands here, not on a
            // duplicate rollout.
            logger.info("Rollout create lost the single-active race for customer {} package {}", cust, body.getPackageName());
            return Response.ERROR("error.rollout.active");
        }

        // Persist the canary set (only device numbers that actually belong to this customer).
        List<RolloutDeviceRow> rows = rolloutDAO.listCustomerDevices(cust);
        Set<String> customerNumbers = new HashSet<>();
        for (RolloutDeviceRow row : rows) customerNumbers.add(row.getDeviceNumber());
        Set<String> canary = new HashSet<>();
        for (String n : body.getCanaryDeviceNumbers()) {
            if (customerNumbers.contains(n)) { rolloutDAO.insertCanary(r.getId(), n); canary.add(n); }
        }

        // Enqueue to the eligible canary devices (skips already-updated / pending / ineligible).
        Set<String> pending = new HashSet<>(rolloutDAO.listPendingInstallNumbers(cust));
        List<RolloutDeviceRow> canaryRows = filter(rows, canary, true);
        int queued = enqueueEligible(r, canaryRows, pending);
        logger.info("Rollout {} created for customer {} (canary {}, queued {})", r.getId(), cust, canary.size(), queued);
        return Response.OK(buildView(r));
    }

    /** Request body for creating a Library-app rollout. */
    public static class CreateAppRolloutRequest {
        private Integer applicationVersionId;
        private List<String> canaryDeviceNumbers;

        public Integer getApplicationVersionId() { return applicationVersionId; }
        public void setApplicationVersionId(Integer v) { this.applicationVersionId = v; }
        public List<String> getCanaryDeviceNumbers() { return canaryDeviceNumbers; }
        public void setCanaryDeviceNumbers(List<String> v) { this.canaryDeviceNumbers = v; }
    }

    // =================================================================================================================
    @ApiOperation(value = "Create Library-app rollout", notes = "Push a Library app's version to the " +
            "selected devices via the same silent-install path used for agent self-updates. Unlike " +
            "the agent rollout, every APK detail (url/pkg/sha256/versionCode) is looked up server-side " +
            "from the application version — the client only names which version and which devices.")
    @POST
    @Path("/apps")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response createApp(CreateAppRolloutRequest body) {
        Optional<Integer> customerId = SecurityContext.get().getCurrentCustomerId();
        if (!customerId.isPresent()) return Response.PERMISSION_DENIED();
        if (body == null || body.getApplicationVersionId() == null
                || body.getCanaryDeviceNumbers() == null || body.getCanaryDeviceNumbers().isEmpty()) {
            return Response.ERROR("error.rollout.invalid");
        }
        int cust = customerId.get();

        ApplicationVersion version = applicationDAO.findApplicationVersionById(body.getApplicationVersionId());
        if (version == null) return Response.ERROR("error.rollout.invalid");
        Application app = applicationDAO.findById(version.getApplicationId());
        if (app == null || app.getCustomerId() != cust) return Response.PERMISSION_DENIED();
        if (isBlank(app.getPkg()) || isBlank(version.getUrl())) return Response.ERROR("error.rollout.invalid");
        if (version.getApkHash() == null || !version.getApkHash().matches("[0-9a-fA-F]{64}")) {
            return Response.ERROR("error.rollout.sha256");
        }

        if (rolloutDAO.findActiveByCustomerAndPackage(cust, app.getPkg()) != null) {
            return Response.ERROR("error.rollout.active");
        }

        long now = System.currentTimeMillis();
        AgentRollout r = new AgentRollout();
        r.setCustomerId(cust);
        r.setTargetVersion(version.getVersion());
        r.setPackageName(app.getPkg());
        r.setApkUrl(version.getUrl());
        r.setApkSha256(version.getApkHash());
        r.setApkVersionCode(version.getVersionCode());
        r.setStage("canary");
        r.setCreatedAt(now);
        r.setUpdatedAt(now);
        r.setTrackingMode("command");
        r.setDisplayName(app.getName());
        try {
            rolloutDAO.insertRollout(r);
        } catch (Exception e) {
            logger.info("App rollout create lost the single-active race for customer {} package {}", cust, app.getPkg());
            return Response.ERROR("error.rollout.active");
        }

        List<RolloutDeviceRow> rows = rolloutDAO.listCustomerDevices(cust);
        Set<String> customerNumbers = new HashSet<>();
        for (RolloutDeviceRow row : rows) customerNumbers.add(row.getDeviceNumber());
        Set<String> canary = new HashSet<>();
        for (String n : body.getCanaryDeviceNumbers()) {
            if (customerNumbers.contains(n)) { rolloutDAO.insertCanary(r.getId(), n); canary.add(n); }
        }

        List<RolloutDeviceRow> canaryRows = filter(rows, canary, true);
        int queued = enqueueEligibleByCommand(r, canaryRows);
        logger.info("App rollout {} ({}) created for customer {} (canary {}, queued {})",
                r.getId(), app.getPkg(), cust, canary.size(), queued);
        return Response.OK(buildView(r));
    }

    // =================================================================================================================
    @ApiOperation(value = "Active Library-app rollouts", notes = "Every in-progress (canary/fleet) " +
            "Library-app rollout for this customer, with progress.")
    @GET
    @Path("/apps/active")
    @Produces(MediaType.APPLICATION_JSON)
    public Response listActiveApps() {
        Optional<Integer> customerId = SecurityContext.get().getCurrentCustomerId();
        if (!customerId.isPresent()) return Response.PERMISSION_DENIED();
        List<Map<String, Object>> views = rolloutDAO.listActiveAppRollouts(customerId.get()).stream()
                .map(this::buildView)
                .collect(Collectors.toList());
        return Response.OK(views);
    }

    // =================================================================================================================
    @ApiOperation(value = "Promote to fleet", notes = "Advance a canary rollout to the rest of the fleet.")
    @POST
    @Path("/{id}/promote")
    @Produces(MediaType.APPLICATION_JSON)
    public Response promote(@PathParam("id") int id) {
        Optional<Integer> customerId = SecurityContext.get().getCurrentCustomerId();
        if (!customerId.isPresent()) return Response.PERMISSION_DENIED();
        AgentRollout r = rolloutDAO.findById(id);
        if (r == null || !customerId.get().equals(r.getCustomerId())) return Response.PERMISSION_DENIED();
        if (!"canary".equals(r.getStage())) return Response.ERROR("error.rollout.stage");

        rolloutDAO.updateStage(r.getId(), "fleet");
        r.setStage("fleet");

        int cust = customerId.get();
        List<RolloutDeviceRow> rows = rolloutDAO.listCustomerDevices(cust);
        Set<String> canary = new HashSet<>(rolloutDAO.listCanaryNumbers(r.getId()));
        List<RolloutDeviceRow> fleetRows = filter(rows, canary, false); // everyone NOT in canary
        int queued = "command".equals(r.getTrackingMode())
                ? enqueueEligibleByCommand(r, fleetRows)
                : enqueueEligible(r, fleetRows, new HashSet<>(rolloutDAO.listPendingInstallNumbers(cust)));
        logger.info("Rollout {} promoted to fleet (queued {})", r.getId(), queued);
        return Response.OK(buildView(r));
    }

    // =================================================================================================================
    @ApiOperation(value = "Cancel/finish rollout", notes = "Stop offering the update (in-flight installs run their course).")
    @POST
    @Path("/{id}/cancel")
    @Produces(MediaType.APPLICATION_JSON)
    public Response cancel(@PathParam("id") int id) {
        Optional<Integer> customerId = SecurityContext.get().getCurrentCustomerId();
        if (!customerId.isPresent()) return Response.PERMISSION_DENIED();
        AgentRollout r = rolloutDAO.findById(id);
        if (r == null || !customerId.get().equals(r.getCustomerId())) return Response.PERMISSION_DENIED();
        rolloutDAO.updateStage(r.getId(), "cancelled");
        return Response.OK();
    }

    // =================================================================================================================
    @ApiOperation(value = "Active rollout", notes = "The current canary/fleet rollout for this customer + progress, or null.")
    @GET
    @Path("/active")
    @Produces(MediaType.APPLICATION_JSON)
    public Response active() {
        Optional<Integer> customerId = SecurityContext.get().getCurrentCustomerId();
        if (!customerId.isPresent()) return Response.PERMISSION_DENIED();
        AgentRollout r = rolloutDAO.findActiveByCustomer(customerId.get());
        return Response.OK(r == null ? null : buildView(r));
    }

    // ---- helpers ----------------------------------------------------------------------------------------------------

    private static boolean isBlank(String s) { return s == null || s.trim().isEmpty(); }

    /** Rows whose membership in {@code set} equals {@code inSet}. */
    private static List<RolloutDeviceRow> filter(List<RolloutDeviceRow> rows, Set<String> set, boolean inSet) {
        List<RolloutDeviceRow> out = new ArrayList<>();
        for (RolloutDeviceRow row : rows) {
            if (set.contains(row.getDeviceNumber()) == inSet) out.add(row);
        }
        return out;
    }

    /** Queue an app.install for every OUTSTANDING device (eligible, not updated, not already pending). */
    private int enqueueEligible(AgentRollout r, List<RolloutDeviceRow> rows, Set<String> pending) {
        int n = 0;
        for (RolloutDeviceRow row : rows) {
            boolean hasPending = pending.contains(row.getDeviceNumber());
            if (RolloutProgress.classify(r.getTargetVersion(), row, hasPending) == RolloutProgress.Status.OUTSTANDING) {
                enqueueInstall(r, row.getDeviceNumber());
                n++;
            }
        }
        return n;
    }

    /** Same as {@link #enqueueEligible}, for a "command"-tracked (Library-app) rollout — see
     *  {@link RolloutProgress#classifyByCommand}. */
    private int enqueueEligibleByCommand(AgentRollout r, List<RolloutDeviceRow> rows) {
        Map<String, String> statusByDevice = commandStatusByDevice(r.getId());
        int n = 0;
        for (RolloutDeviceRow row : rows) {
            String status = statusByDevice.get(row.getDeviceNumber());
            if (RolloutProgress.classifyByCommand(row, status) == RolloutProgress.Status.OUTSTANDING) {
                enqueueInstall(r, row.getDeviceNumber());
                n++;
            }
        }
        return n;
    }

    private Map<String, String> commandStatusByDevice(int rolloutId) {
        Map<String, String> m = new HashMap<>();
        for (RolloutCommandStatusRow row : rolloutDAO.listCommandStatuses(rolloutId)) {
            m.put(row.getDeviceNumber(), row.getStatus());
        }
        return m;
    }

    /** Per-device breakdown for a "command"-tracked rollout's progress view — the console shows
     *  exactly which devices are still pending, not just a count. */
    private List<Map<String, Object>> perDeviceStatus(List<RolloutDeviceRow> rows, Map<String, String> statusByDevice) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (RolloutDeviceRow row : rows) {
            String status = statusByDevice.get(row.getDeviceNumber());
            Map<String, Object> d = new LinkedHashMap<>();
            d.put("deviceNumber", row.getDeviceNumber());
            d.put("status", RolloutProgress.classifyByCommand(row, status).name());
            out.add(d);
        }
        return out;
    }

    private void enqueueInstall(AgentRollout r, String deviceNumber) {
        AgentCommand cmd = new AgentCommand();
        cmd.setDeviceNumber(deviceNumber);
        cmd.setType("app.install");
        cmd.setPayload(installPayload(r));
        cmd.setRequiresCapability(RolloutProgress.INSTALL_CAPABILITY);
        cmd.setStatus("pending");
        cmd.setCreatedAt(System.currentTimeMillis());
        commandDAO.insert(cmd);
        // Recorded for every tracking mode (harmless, unused by "version"-tracked progress) so a
        // rollout never needs to know in advance which kind of progress query it'll need later.
        rolloutDAO.upsertRolloutCommand(r.getId(), deviceNumber, cmd.getId());
        wakeHub.wake(deviceNumber, "commands");
    }

    private String installPayload(AgentRollout r) {
        ObjectNode p = MAPPER.createObjectNode();
        p.put("url", r.getApkUrl());
        p.put("packageName", r.getPackageName());
        if (r.getApkVersionCode() != null) p.put("versionCode", r.getApkVersionCode());
        if (r.getApkSha256() != null) p.put("sha256", r.getApkSha256());
        p.put("runAfterInstall", false);
        try {
            return MAPPER.writeValueAsString(p);
        } catch (Exception e) {
            return "{}"; // unreachable for a plain ObjectNode
        }
    }

    private Map<String, Object> buildView(AgentRollout r) {
        int cust = r.getCustomerId();
        boolean byCommand = "command".equals(r.getTrackingMode());
        List<RolloutDeviceRow> rows = rolloutDAO.listCustomerDevices(cust);
        Set<String> canary = new HashSet<>(rolloutDAO.listCanaryNumbers(r.getId()));
        List<RolloutDeviceRow> canaryRows = filter(rows, canary, true);
        List<RolloutDeviceRow> fleetRows = filter(rows, canary, false);
        boolean fleetStarted = "fleet".equals(r.getStage()) || "done".equals(r.getStage());

        Map<String, Object> progress = new LinkedHashMap<>();
        progress.put("stage", r.getStage());
        progress.put("targetVersion", r.getTargetVersion());
        if (byCommand) {
            Map<String, String> statusByDevice = commandStatusByDevice(r.getId());
            progress.put("canary", RolloutProgress.countsByCommand(canaryRows, statusByDevice));
            progress.put("fleet", fleetStarted ? RolloutProgress.countsByCommand(fleetRows, statusByDevice) : null);
            progress.put("canaryDevices", perDeviceStatus(canaryRows, statusByDevice));
            progress.put("fleetDevices", fleetStarted ? perDeviceStatus(fleetRows, statusByDevice) : null);
        } else {
            Set<String> pending = new HashSet<>(rolloutDAO.listPendingInstallNumbers(cust));
            progress.put("canary", RolloutProgress.counts(r.getTargetVersion(), canaryRows, pending));
            progress.put("fleet", fleetStarted ? RolloutProgress.counts(r.getTargetVersion(), fleetRows, pending) : null);
        }

        Map<String, Object> view = new LinkedHashMap<>();
        view.put("id", r.getId());
        view.put("targetVersion", r.getTargetVersion());
        view.put("packageName", r.getPackageName());
        view.put("displayName", r.getDisplayName());
        view.put("apkVersionCode", r.getApkVersionCode());
        view.put("stage", r.getStage());
        view.put("createdAt", r.getCreatedAt());
        view.put("updatedAt", r.getUpdatedAt());
        view.put("progress", progress);
        return view;
    }
}

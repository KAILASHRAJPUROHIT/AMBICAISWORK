package com.hmdm.task;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.RolloutDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.AgentRollout;
import com.hmdm.persistence.domain.Device;
import com.hmdm.persistence.domain.DeviceEvent;
import com.hmdm.persistence.domain.RolloutDeviceRow;
import com.hmdm.rest.resource.RolloutResource;
import com.hmdm.util.RolloutProgress;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Automatic agent updates, overnight, canary first (agreed 2026-09-28).
 *
 * <p>Runs every 10 minutes and uses the same rollout machinery as the console ({@link RolloutResource}),
 * so an automatic rollout looks and behaves exactly like a manual one (marked displayName
 * "auto-update"). It only acts when the console's "Automatic updates" switch is on -- the
 * supervisor's {@code auto} flag -- so one switch controls both server and agent updates.</p>
 *
 * <ol>
 *   <li>A newer agent release is mirrored and verified by the supervisor, no rollout of that version
 *       exists yet (so an admin's cancel is never overridden), and it is inside the install window
 *       (default 20:30-10:30 Asia/Kolkata, changed from 22:00-07:00 on 2026-09-28): pick ONE online device still on the old version as the
 *       canary and start the rollout.</li>
 *   <li>Canary stage: once every canary device reports the new version, at least
 *       {@link #CANARY_SOAK_MS} have passed and no canary logged a crash since the rollout started,
 *       promote to the whole fleet (inside the window). A canary that never reports is left for an
 *       admin -- the fleet is not touched.</li>
 *   <li>Fleet stage: inside the window, re-queue devices that missed their install (e.g. were
 *       offline); once nothing is outstanding or pending, mark the rollout done so the next release
 *       can start. A superseded auto rollout is also closed.</li>
 * </ol>
 *
 * <p>Tablets switched off overnight get their queued install when they next start, i.e. at boot, not
 * mid-sale. Manual (console-started) rollouts are left alone apart from nothing: this task never
 * promotes or finishes a rollout it didn't start.</p>
 */
@Singleton
public class AgentAutoRolloutTask implements Runnable {

    private static final Logger logger = LoggerFactory.getLogger(AgentAutoRolloutTask.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    static final String AUTO = "auto-update";
    private static final String AGENT_PACKAGE = "com.mdmesh.agent";
    private static final long CANARY_SOAK_MS = 20 * 60 * 1000L;
    private static final long ONLINE_MS = 15 * 60 * 1000L;
    private static final long STALE_FLEET_MS = 3L * 24 * 60 * 60 * 1000;

    private final RolloutResource rollouts;
    private final RolloutDAO rolloutDAO;
    private final UnsecureDAO unsecureDAO;
    private final AgentCommandDAO commandDAO;

    @Inject
    public AgentAutoRolloutTask(RolloutResource rollouts, RolloutDAO rolloutDAO, UnsecureDAO unsecureDAO,
                                AgentCommandDAO commandDAO) {
        this.rollouts = rollouts;
        this.rolloutDAO = rolloutDAO;
        this.unsecureDAO = unsecureDAO;
        this.commandDAO = commandDAO;
    }

    @Override
    public void run() {
        try {
            JsonNode status = supervisorStatus();
            if (status == null || !status.path("auto").asBoolean(false)) return; // switch off / unreachable
            JsonNode apk = status.path("apk");
            if (!apk.path("available").asBoolean(false)) return;
            String version = apk.path("version").asText(null);
            int versionCode = apk.path("versionCode").asInt(0);
            String sha256 = apk.path("sha256").asText(null);
            if (version == null || versionCode <= 0 || sha256 == null || !sha256.matches("[0-9a-fA-F]{64}")) return;

            boolean inWindow = inInstallWindow();
            for (Integer cust : rolloutDAO.listCustomerIdsWithDevices()) {
                if (cust == null) continue;
                try {
                    handleCustomer(cust, version, versionCode, sha256, inWindow);
                } catch (Exception e) {
                    logger.warn("auto agent rollout failed for customer {}", cust, e);
                }
            }
        } catch (Exception e) {
            logger.warn("auto agent rollout run failed", e); // next run retries
        }
    }

    private void handleCustomer(int cust, String version, int versionCode, String sha256, boolean inWindow) {
        AgentRollout active = rolloutDAO.findActiveByCustomerAndPackage(cust, AGENT_PACKAGE);
        if (active != null) {
            if (!AUTO.equals(active.getDisplayName())) return; // an admin's rollout: hands off
            boolean superseded = active.getApkVersionCode() != null && active.getApkVersionCode() < versionCode;
            if ("canary".equals(active.getStage())) {
                if (superseded) {
                    rolloutDAO.updateStage(active.getId(), "cancelled"); // a newer release replaces it
                    logger.info("auto rollout {} ({}) superseded by {}", active.getId(), active.getTargetVersion(), version);
                } else if (inWindow && canaryHealthy(active)) {
                    rollouts.promoteRollout(active);
                    logger.info("auto rollout {} ({}) canary healthy -> promoted to fleet", active.getId(), version);
                }
            } else if ("fleet".equals(active.getStage())) {
                RolloutProgress.Counts fleet = rollouts.cohortCounts(active, false);
                boolean finished = fleet.getOutstanding() == 0 && fleet.getPending() == 0;
                boolean stale = System.currentTimeMillis() - active.getCreatedAt() > STALE_FLEET_MS;
                if (finished || stale || superseded) {
                    rolloutDAO.updateStage(active.getId(), "done");
                    logger.info("auto rollout {} ({}) closed (finished={}, stale={}, superseded={})",
                            active.getId(), active.getTargetVersion(), finished, stale, superseded);
                } else if (inWindow) {
                    rollouts.reconcileRollout(active); // re-queue devices that missed it (offline etc.)
                }
            }
            return;
        }

        if (!inWindow) return;
        if (rolloutDAO.findLatestForVersion(cust, AGENT_PACKAGE, version) != null) return; // already done/cancelled

        // Canary = the most recently seen online device that still needs this version.
        Set<String> pending = new HashSet<>(rolloutDAO.listPendingInstallNumbers(cust));
        String canary = null;
        long best = 0;
        for (RolloutDeviceRow row : rolloutDAO.listCustomerDevices(cust)) {
            boolean hasPending = pending.contains(row.getDeviceNumber());
            if (RolloutProgress.classify(version, AGENT_PACKAGE, row, hasPending) != RolloutProgress.Status.OUTSTANDING) continue;
            Device d = unsecureDAO.getDeviceByNumber(row.getDeviceNumber());
            Long seen = d == null ? null : d.getLastUpdate();
            if (seen == null || System.currentTimeMillis() - seen > ONLINE_MS) continue;
            if (seen > best) { best = seen; canary = row.getDeviceNumber(); }
        }
        if (canary == null) return; // everyone current, or nobody online to be the canary

        AgentRollout started = rollouts.startAgentCanary(cust, version, AGENT_PACKAGE, versionCode, sha256,
                Collections.singletonList(canary), AUTO);
        if (started != null) {
            logger.info("auto rollout {} started for customer {}: v{} canary {}", started.getId(), cust, version, canary);
        }
    }

    /** Every canary reports the target version, the soak time has passed, and no canary crashed. */
    private boolean canaryHealthy(AgentRollout r) {
        if (System.currentTimeMillis() - r.getCreatedAt() < CANARY_SOAK_MS) return false;
        RolloutProgress.Counts c = rollouts.cohortCounts(r, true);
        if (c.getUpdated() == 0 || c.getOutstanding() > 0 || c.getPending() > 0) return false;
        for (String n : rolloutDAO.listCanaryNumbers(r.getId())) {
            List<DeviceEvent> evs = commandDAO.listEvents(n, r.getCreatedAt(), 500);
            for (DeviceEvent e : evs) {
                if ("crash".equals(e.getType()) || "kioskCrashLoop".equals(e.getType())) {
                    logger.warn("auto rollout {}: canary {} crashed after update -- not promoting", r.getId(), n);
                    return false;
                }
            }
        }
        return true;
    }

    private static final int DEFAULT_FROM_MIN = 20 * 60 + 30; // 8:30 PM
    private static final int DEFAULT_TO_MIN = 10 * 60 + 30;   // 10:30 AM

    private static boolean inInstallWindow() {
        String tz = env("MDM_AGENT_AUTO_UPDATE_TZ", "Asia/Kolkata");
        int from = parseHhMm(env("MDM_AGENT_AUTO_UPDATE_FROM", "20:30"), DEFAULT_FROM_MIN);
        int to = parseHhMm(env("MDM_AGENT_AUTO_UPDATE_TO", "10:30"), DEFAULT_TO_MIN);
        ZonedDateTime now;
        try {
            now = ZonedDateTime.now(ZoneId.of(tz));
        } catch (Exception e) {
            now = ZonedDateTime.now(ZoneId.of("Asia/Kolkata"));
        }
        int m = now.getHour() * 60 + now.getMinute();
        return from <= to ? (m >= from && m < to) : (m >= from || m < to); // window may cross midnight
    }

    /** "HH:MM" (24h) -> minutes after midnight; {@code dflt} if malformed. */
    private static int parseHhMm(String v, int dflt) {
        try {
            String[] p = v.trim().split(":");
            int h = Integer.parseInt(p[0]);
            int min = p.length > 1 ? Integer.parseInt(p[1]) : 0;
            return h >= 0 && h <= 23 && min >= 0 && min <= 59 ? h * 60 + min : dflt;
        } catch (Exception e) {
            return dflt;
        }
    }

    private static String env(String key, String dflt) {
        String v = System.getProperty(key, System.getenv(key));
        return v == null || v.trim().isEmpty() ? dflt : v.trim();
    }

    /** GET the supervisor's public /update/status (no auth) over the compose network. */
    private static JsonNode supervisorStatus() {
        String base = env("MDM_SUPERVISOR_URL", "http://supervisor:9000");
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base.replaceAll("/+$", "") + "/update/status").openConnection();
            c.setConnectTimeout(5000);
            c.setReadTimeout(5000);
            if (c.getResponseCode() != 200) return null;
            try (InputStream in = c.getInputStream()) {
                return MAPPER.readTree(in);
            }
        } catch (Exception e) {
            logger.debug("supervisor status unavailable: {}", e.toString());
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }
}

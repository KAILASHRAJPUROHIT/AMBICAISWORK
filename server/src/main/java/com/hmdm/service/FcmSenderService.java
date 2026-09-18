package com.hmdm.service;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import org.json.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.net.ssl.HttpsURLConnection;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Sends a silent, data-only, high-priority FCM message to wake one device. This is a SECOND wake
 * channel alongside {@link com.hmdm.notification.AgentWakeHub}'s WebSocket, not a replacement -
 * the WebSocket still fires when it's open (usually faster when the screen is on), and this covers
 * exactly the case the WebSocket cannot: a device whose screen is off and whose connection Doze (or
 * an OEM's own battery manager, notably MIUI) has already killed. Google Play Services keeps its
 * own connection alive through Doze specifically for high-priority FCM delivery, which a custom
 * WebSocket has no way to match.
 *
 * Data-only (no "notification" block) so nothing appears in the system tray - the payload is the
 * exact same wake-only signal shape AgentWakeHub already sends, carrying no command content.
 * Authenticates via {@link GoogleWifTokenService} (no static Google credential, no Firebase Admin
 * SDK - same raw-HTTP philosophy as the rest of this codebase's Google integrations).
 */
@Singleton
public class FcmSenderService {
    private static final Logger logger = LoggerFactory.getLogger(FcmSenderService.class);

    private final GoogleWifTokenService wif;

    @Inject
    public FcmSenderService(GoogleWifTokenService wif) {
        this.wif = wif;
    }

    public boolean isConfigured() {
        return !projectId().isEmpty();
    }

    /** Best-effort: a failure here must never break a check-in or command-queue path that also
     *  calls it - this is one of two wake channels, not the only path to command delivery. */
    public void wakeDevice(String fcmToken, String wakeKind) {
        if (fcmToken == null || fcmToken.trim().isEmpty()) return;
        String project = projectId();
        if (project.isEmpty()) {
            logger.debug("FCM wake skipped for token ending ...{}: AMBIC_FCM_PROJECT_ID not set",
                    tail(fcmToken));
            return;
        }
        try {
            String accessToken = wif.getAccessToken(GoogleWifTokenService.SCOPE_FIREBASE_MESSAGING);
            JSONObject data = new JSONObject()
                    .put("wake", "interactive".equals(wakeKind) ? "interactive" : "commands");
            JSONObject message = new JSONObject()
                    .put("token", fcmToken)
                    .put("data", data)
                    .put("android", new JSONObject().put("priority", "high"));
            JSONObject body = new JSONObject().put("message", message);

            String url = "https://fcm.googleapis.com/v1/projects/" + project + "/messages:send";
            HttpsURLConnection c = (HttpsURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(10000); c.setReadTimeout(10000); c.setRequestMethod("POST"); c.setDoOutput(true);
            c.setRequestProperty("Authorization", "Bearer " + accessToken);
            c.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
            byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
            c.setFixedLengthStreamingMode(payload.length);
            try (OutputStream out = c.getOutputStream()) { out.write(payload); }

            int status = c.getResponseCode();
            if (status < 200 || status >= 300) {
                logger.warn("FCM wake failed (HTTP {}) for token ending ...{}: {}",
                        status, tail(fcmToken), readBody(c));
            } else {
                // Log only the redacted token suffix. This proves server-to-FCM acceptance
                // without exposing a reusable registration token in production logs.
                logger.info("FCM wake accepted (HTTP {}) for token ending ...{}", status, tail(fcmToken));
            }
        } catch (Exception e) {
            logger.warn("FCM wake error for token ending ...{}: {}", tail(fcmToken), e.getMessage());
        }
    }

    private static String tail(String token) {
        return token.length() > 8 ? token.substring(token.length() - 8) : token;
    }

    private static String readBody(HttpsURLConnection c) {
        try {
            InputStream stream = c.getErrorStream() != null ? c.getErrorStream() : c.getInputStream();
            if (stream == null) return "";
            StringBuilder body = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line; while ((line = reader.readLine()) != null) body.append(line);
            }
            return body.toString();
        } catch (Exception e) {
            return "(unreadable: " + e.getMessage() + ")";
        }
    }

    private static String projectId() {
        String value = System.getProperty("AMBIC_FCM_PROJECT_ID");
        if (value == null || value.trim().isEmpty()) value = System.getenv("AMBIC_FCM_PROJECT_ID");
        return value == null ? "" : value.trim();
    }
}

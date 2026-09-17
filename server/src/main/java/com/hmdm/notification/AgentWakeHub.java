/*
 * MDMesh agent wake hub: holds live device WebSocket sessions and fans out wake-only signals.
 */
package com.hmdm.notification;

import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.service.FcmSenderService;
import com.hmdm.util.CryptoUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.websocket.Session;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Registry of live agent WebSocket sessions (one per device number) plus the wake fan-out.
 *
 * <p>The wake payload is signal-only ({@code {"wake":"commands"}}) — never a command — so a leaked
 * connection reveals nothing; the device still authenticates its actual sync with its bearer secret.
 * Sessions are authenticated at connect via that same per-device secret (see {@link #validate}).</p>
 *
 * <p>Reached from the container-managed {@code AgentWakeEndpoint} via {@link #INSTANCE} (JSR-356
 * endpoints aren't Guice-instantiated); the hub is an eager singleton so {@code INSTANCE} is set at
 * boot, before any device can connect.</p>
 */
@Singleton
public class AgentWakeHub {

    private static final Logger log = LoggerFactory.getLogger(AgentWakeHub.class);

    /** Static bridge for the container-created WebSocket endpoint. Set in the constructor. */
    public static volatile AgentWakeHub INSTANCE;

    private final AgentCommandDAO commandDAO;
    private final FcmSenderService fcm;
    private final Map<String, Session> sessions = new ConcurrentHashMap<>();

    @Inject
    public AgentWakeHub(AgentCommandDAO commandDAO, FcmSenderService fcm) {
        this.commandDAO = commandDAO;
        this.fcm = fcm;
        INSTANCE = this;
    }

    /** Constant-time check of the presented secret against the stored per-device SHA-256 hash. */
    public boolean validate(String deviceNumber, String secret) {
        if (deviceNumber == null || secret == null) {
            return false;
        }
        String expectedHash = commandDAO.getDeviceSecretHash(deviceNumber);
        return expectedHash != null
                && CryptoUtil.constantTimeEquals(CryptoUtil.getSHA256String(secret), expectedHash);
    }

    public void register(String deviceNumber, Session session) {
        Session previous = sessions.put(deviceNumber, session);
        if (previous != null && previous != session && previous.isOpen()) {
            try { previous.close(); } catch (Exception ignored) { }
        }
        log.debug("Agent wake socket registered for {}", deviceNumber);
    }

    public void unregister(String deviceNumber, Session session) {
        sessions.remove(deviceNumber, session);
    }

    public boolean isOnline(String deviceNumber) {
        Session s = sessions.get(deviceNumber);
        return s != null && s.isOpen();
    }

    /** Send a wake-only signal to the device over every channel available: the live WebSocket if
     *  one is open (fastest when the screen is already on), and an FCM data message (survives
     *  Doze/OEM battery restrictions that kill the WebSocket while the screen is off) if this
     *  device has a registered token. Neither channel is required to succeed - a caller that needs
     *  guaranteed delivery still relies on the periodic check-in floor, same as before either
     *  channel existed. */
    public void wake(String deviceNumber, String wakeKind) {
        Session s = sessions.get(deviceNumber);
        if (s != null && s.isOpen()) {
            String payload = "interactive".equals(wakeKind)
                    ? "{\"wake\":\"interactive\",\"ttlSec\":120}"
                    : "{\"wake\":\"commands\"}";
            try {
                s.getAsyncRemote().sendText(payload);
            } catch (Exception e) {
                log.warn("Agent wake send failed for {}: {}", deviceNumber, e.getMessage());
            }
        }
        String fcmToken = commandDAO.getFcmToken(deviceNumber);
        if (fcmToken != null && !fcmToken.trim().isEmpty()) {
            fcm.wakeDevice(fcmToken, wakeKind);
        }
    }
}

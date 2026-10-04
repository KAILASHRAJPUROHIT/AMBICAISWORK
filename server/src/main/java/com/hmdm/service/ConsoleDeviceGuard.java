package com.hmdm.service;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.ConsoleDeviceDAO;
import com.hmdm.persistence.domain.ConsoleLoginOtp;
import com.hmdm.persistence.domain.ConsoleTrustedDevice;
import com.hmdm.persistence.domain.User;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;

/**
 * Console sign-in allow-list. After the password is right, a computer the user has not signed in from before must
 * also enter a one-time code that is emailed to the owner's address; the computer's fingerprint is then added to the
 * user's allowed list and later sign-ins from it need no code.
 *
 * <p>Mode (environment {@code MDM_CONSOLE_DEVICE_BINDING}): {@code on} always enforces and fails closed;
 * {@code auto} (default) enforces only while outgoing email is configured, so a missing SMTP setup can never lock
 * everyone out; {@code off} disables it. The code goes to {@code MDM_CONSOLE_OTP_EMAIL}
 * (default info@aradhanajewellers.com).</p>
 */
@Singleton
public class ConsoleDeviceGuard {
    private static final Logger logger = LoggerFactory.getLogger(ConsoleDeviceGuard.class);
    private static final long OTP_TTL_MS = 10 * 60_000L;
    private static final long RESEND_MIN_MS = 30_000L;
    private static final int MAX_CODES_PER_HOUR = 5;
    private static final int MAX_ATTEMPTS = 5;

    public enum Result { ALLOW, OTP_SENT, OTP_INVALID, FINGERPRINT_MISSING, RATE_LIMITED, MAIL_FAILED }

    public static final class Outcome {
        public final Result result;
        public final String sentTo;
        Outcome(Result result, String sentTo) { this.result = result; this.sentTo = sentTo; }
        public boolean allowed() { return result == Result.ALLOW; }
    }

    private final ConsoleDeviceDAO dao;
    private final EmailService email;
    private final SecureRandom random = new SecureRandom();
    private final String mode;
    private final String recipient;

    @Inject
    public ConsoleDeviceGuard(ConsoleDeviceDAO dao, EmailService email) {
        this.dao = dao;
        this.email = email;
        String m = setting("MDM_CONSOLE_DEVICE_BINDING", "auto").toLowerCase();
        this.mode = (m.equals("on") || m.equals("off")) ? m : "auto";
        this.recipient = setting("MDM_CONSOLE_OTP_EMAIL", "info@aradhanajewellers.com");
    }

    /** Whether sign-ins are being checked right now (for the Settings page). */
    public boolean enforcing() {
        return mode.equals("on") || (mode.equals("auto") && email.isConfigured());
    }

    public String mode() { return mode; }
    public String recipient() { return recipient; }
    public String maskedRecipient() { return mask(recipient); }

    public Outcome check(User user, String fingerprint, String otp, String label, String ip, String userAgent) {
        if (!enforcing()) {
            if (mode.equals("auto")) logger.warn("Console device binding is INACTIVE: outgoing email is not configured (set SMTP_HOST, or MDM_CONSOLE_DEVICE_BINDING=off to silence this)");
            return new Outcome(Result.ALLOW, null);
        }
        if (fingerprint == null || fingerprint.trim().length() < 16) return new Outcome(Result.FINGERPRINT_MISSING, null);
        final long now = System.currentTimeMillis();
        final String fp = sha256(fingerprint.trim());

        ConsoleTrustedDevice known = dao.findTrusted(user.getId(), fp);
        if (known != null) {
            dao.touchTrusted(known.getId());
            return new Outcome(Result.ALLOW, null);
        }

        if (otp == null || otp.trim().isEmpty()) return sendCode(user, fp, label, ip, now);

        ConsoleLoginOtp open = dao.latestOpenOtp(user.getId(), fp);
        if (open == null || open.getAttempts() >= MAX_ATTEMPTS) return new Outcome(Result.OTP_INVALID, null);
        String candidate = sha256(open.getSalt() + ":" + otp.trim());
        if (!MessageDigest.isEqual(candidate.getBytes(StandardCharsets.UTF_8), open.getCodeHash().getBytes(StandardCharsets.UTF_8))) {
            dao.bumpAttempts(open.getId());
            return new Outcome(Result.OTP_INVALID, null);
        }
        if (!dao.markUsed(open.getId())) return new Outcome(Result.OTP_INVALID, null);

        ConsoleTrustedDevice d = new ConsoleTrustedDevice();
        d.setUserId(user.getId());
        d.setFingerprintHash(fp);
        d.setLabel(clip(label, 120, "Unnamed computer"));
        d.setUserAgent(clip(userAgent, 300, ""));
        d.setIpAddress(clip(ip, 64, ""));
        d.setCreatedAt(now);
        d.setLastSeenAt(now);
        dao.upsertTrusted(d);
        logger.info("Console device added to the allowed list for user {} from {}", user.getLogin(), ip);
        return new Outcome(Result.ALLOW, null);
    }

    private Outcome sendCode(User user, String fp, String label, String ip, long now) {
        // Asking again within 30 s does not send a second email (the first one is still good).
        ConsoleLoginOtp open = dao.latestOpenOtp(user.getId(), fp);
        if (open != null && now - open.getCreatedAt() < RESEND_MIN_MS) return new Outcome(Result.OTP_SENT, mask(recipient));
        if (dao.countOtpSince(user.getId(), now - 3600_000L) >= MAX_CODES_PER_HOUR) return new Outcome(Result.RATE_LIMITED, null);

        String code = String.format("%06d", random.nextInt(1_000_000));
        String salt = randomHex(16);
        ConsoleLoginOtp row = new ConsoleLoginOtp();
        row.setUserId(user.getId());
        row.setFingerprintHash(fp);
        row.setSalt(salt);
        row.setCodeHash(sha256(salt + ":" + code));
        row.setCreatedAt(now);
        row.setExpiresAt(now + OTP_TTL_MS);
        dao.insertOtp(row);
        dao.purgeOtp();

        String body = "Your AMBIC MDM console sign-in code is " + code + "\n\n"
                + "It expires in 10 minutes and works once.\n"
                + "User: " + user.getLogin() + "\n"
                + "Computer: " + clip(label, 120, "Unnamed computer") + "\n"
                + "Address: " + clip(ip, 64, "unknown") + "\n\n"
                + "If this was not you, do not share the code and change the password.";
        boolean sent = email.sendEmail(recipient, "AMBIC MDM sign-in code", body);
        if (!sent) {
            logger.error("Could not email the console sign-in code to {}", mask(recipient));
            return new Outcome(Result.MAIL_FAILED, null);
        }
        return new Outcome(Result.OTP_SENT, mask(recipient));
    }

    private static String setting(String name, String fallback) {
        String v = System.getProperty(name);
        if (v == null || v.trim().isEmpty()) v = System.getenv(name);
        return v == null || v.trim().isEmpty() ? fallback : v.trim();
    }

    private static String clip(String s, int max, String fallback) {
        if (s == null || s.trim().isEmpty()) return fallback;
        String t = s.trim();
        return t.length() > max ? t.substring(0, max) : t;
    }

    private static String mask(String addr) {
        int at = addr.indexOf('@');
        if (at < 2) return addr;
        return addr.substring(0, 2) + "***" + addr.substring(at);
    }

    private String randomHex(int bytes) {
        byte[] b = new byte[bytes];
        random.nextBytes(b);
        return hex(b);
    }

    static String sha256(String s) {
        try {
            return hex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder(b.length * 2);
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }
}

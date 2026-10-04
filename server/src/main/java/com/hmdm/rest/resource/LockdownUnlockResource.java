package com.hmdm.rest.resource;

import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.DeviceUnlockDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.domain.Device;
import com.hmdm.persistence.domain.DeviceUnlockOtp;
import com.hmdm.rest.json.Response;
import com.hmdm.service.EmailService;
import com.hmdm.util.AgentAuth;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
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
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Map;

/**
 * Lifts a tablet's offline lockdown. A locked tablet asks for a code ({@code unlock-request}); the server emails it to the
 * owner ({@code MDM_CONSOLE_OTP_EMAIL}, default info@aradhanajewellers.com); the administrator types it on the tablet
 * ({@code unlock-verify}). Device-authenticated like check-in: only the tablet itself, holding its secret, can ask.
 * Codes last 10 minutes, work once, allow 5 wrong tries, and at most 3 can be requested per 10 minutes.
 */
@Singleton
@Path("/public/agent/v1/lockdown")
@Api(tags = {"Agent v1 lockdown"})
public class LockdownUnlockResource {
    private static final Logger logger = LoggerFactory.getLogger(LockdownUnlockResource.class);
    private static final long TTL_MS = 10 * 60_000L;
    private static final int MAX_CODES_PER_WINDOW = 3;
    private static final int MAX_ATTEMPTS = 5;

    private UnsecureDAO unsecureDAO;
    private AgentCommandDAO commandDAO;
    private DeviceUnlockDAO dao;
    private EmailService email;
    private final SecureRandom random = new SecureRandom();

    public LockdownUnlockResource() {
    }

    @Inject
    public LockdownUnlockResource(UnsecureDAO unsecureDAO, AgentCommandDAO commandDAO, DeviceUnlockDAO dao, EmailService email) {
        this.unsecureDAO = unsecureDAO;
        this.commandDAO = commandDAO;
        this.dao = dao;
        this.email = email;
    }

    public static class CodeBody {
        private String code;
        public String getCode() { return code; }
        public void setCode(String code) { this.code = code; }
    }

    @ApiOperation(value = "Email an unlock code", notes = "Device-authenticated. Sends a one-time code to the owner's address.")
    @POST
    @Path("/unlock-request")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response unlockRequest(@HeaderParam("Authorization") String authorization,
                                  @HeaderParam("X-Device-Number") String deviceNumber) {
        Response denied = authenticate(authorization, deviceNumber);
        if (denied != null) return denied;
        if (!email.isConfigured()) return Response.ERROR("error.unlock.mail.unconfigured");

        final long now = System.currentTimeMillis();
        if (dao.countSince(deviceNumber, now - TTL_MS) >= MAX_CODES_PER_WINDOW) return Response.ERROR("error.unlock.rate.limited");

        String code = String.format("%06d", random.nextInt(1_000_000));
        String salt = randomHex(16);
        DeviceUnlockOtp row = new DeviceUnlockOtp();
        row.setDeviceNumber(deviceNumber);
        row.setSalt(salt);
        row.setCodeHash(sha256(salt + ":" + code));
        row.setCreatedAt(now);
        row.setExpiresAt(now + TTL_MS);
        dao.insert(row);
        dao.purge();

        Device device = unsecureDAO.getDeviceByNumber(deviceNumber);
        String name = device != null && device.getDescription() != null && !device.getDescription().trim().isEmpty()
                ? device.getDescription() + " (" + deviceNumber + ")" : deviceNumber;
        String recipient = recipient();
        String body = "Tablet unlock code: " + code + "\n\n"
                + "Tablet: " + name + "\n"
                + "This tablet locked itself after 30 minutes without internet. Enter the code on the tablet to unlock it.\n"
                + "The code is valid for 10 minutes and works once. If you did not expect this, do not share it.";
        if (!email.sendEmail(recipient, "AMBIC MDM tablet unlock code", body)) {
            logger.error("Could not email the tablet unlock code for {}", deviceNumber);
            return Response.ERROR("error.unlock.mail.failed");
        }
        logger.info("Unlock code emailed for tablet {}", deviceNumber);
        Map<String, Object> out = new HashMap<>();
        out.put("sentTo", mask(recipient));
        return Response.OK(out);
    }

    @ApiOperation(value = "Check an unlock code", notes = "Device-authenticated. OK means the tablet may leave lockdown.")
    @POST
    @Path("/unlock-verify")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response unlockVerify(@HeaderParam("Authorization") String authorization,
                                 @HeaderParam("X-Device-Number") String deviceNumber,
                                 CodeBody body) throws InterruptedException {
        Response denied = authenticate(authorization, deviceNumber);
        if (denied != null) return denied;
        String code = body == null || body.getCode() == null ? "" : body.getCode().trim();
        DeviceUnlockOtp open = dao.latestOpen(deviceNumber);
        if (code.isEmpty() || open == null || open.getAttempts() >= MAX_ATTEMPTS) {
            Thread.sleep(500);
            return Response.ERROR("error.unlock.invalid");
        }
        String candidate = sha256(open.getSalt() + ":" + code);
        if (!MessageDigest.isEqual(candidate.getBytes(StandardCharsets.UTF_8), open.getCodeHash().getBytes(StandardCharsets.UTF_8))) {
            dao.bumpAttempts(open.getId());
            Thread.sleep(500);
            return Response.ERROR("error.unlock.invalid");
        }
        if (!dao.markUsed(open.getId())) return Response.ERROR("error.unlock.invalid");
        logger.info("Tablet {} unlocked with an emailed code", deviceNumber);
        Map<String, Object> out = new HashMap<>();
        out.put("unlocked", true);
        return Response.OK(out);
    }

    private Response authenticate(String authorization, String deviceNumber) {
        if (deviceNumber == null || deviceNumber.trim().isEmpty()) return Response.ERROR("error.remote.device.missing");
        if (!AgentAuth.authenticate(authorization, deviceNumber, commandDAO)) return Response.PERMISSION_DENIED();
        return null;
    }

    private static String recipient() {
        String v = System.getProperty("MDM_CONSOLE_OTP_EMAIL");
        if (v == null || v.trim().isEmpty()) v = System.getenv("MDM_CONSOLE_OTP_EMAIL");
        return v == null || v.trim().isEmpty() ? "info@aradhanajewellers.com" : v.trim();
    }

    private static String mask(String addr) {
        int at = addr.indexOf('@');
        return at < 2 ? addr : addr.substring(0, 2) + "***" + addr.substring(at);
    }

    private String randomHex(int bytes) {
        byte[] b = new byte[bytes];
        random.nextBytes(b);
        return hex(b);
    }

    private static String sha256(String s) {
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

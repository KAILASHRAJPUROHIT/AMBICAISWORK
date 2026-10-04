package com.hmdm.rest.resource;

import com.hmdm.persistence.SmtpOverrideDAO;
import com.hmdm.persistence.domain.SmtpOverride;
import com.hmdm.rest.json.Response;
import com.hmdm.security.SecurityContext;
import com.hmdm.service.ConsoleDeviceGuard;
import com.hmdm.service.EmailService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.Consumes;
import javax.ws.rs.DELETE;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.PUT;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import java.util.HashMap;
import java.util.Map;

/**
 * Outgoing-email settings, editable in the console (Settings &gt; Security) so the sign-in and tablet-unlock codes can be
 * emailed without touching the server's environment. The password is write-only: it is stored encrypted and never returned.
 */
@Singleton
@Path("/private/smtp-settings")
public class SmtpSettingsResource {
    private static final Logger logger = LoggerFactory.getLogger(SmtpSettingsResource.class);

    private final SmtpOverrideDAO dao;
    private final EmailService email;
    private final ConsoleDeviceGuard guard;

    @Inject
    public SmtpSettingsResource(SmtpOverrideDAO dao, EmailService email, ConsoleDeviceGuard guard) {
        this.dao = dao;
        this.email = email;
        this.guard = guard;
    }

    public static class SmtpBody {
        private String host;
        private Integer port;
        private String security;
        private String username;
        private String password;
        private String fromAddress;
        public String getHost() { return host; }
        public void setHost(String host) { this.host = host; }
        public Integer getPort() { return port; }
        public void setPort(Integer port) { this.port = port; }
        public String getSecurity() { return security; }
        public void setSecurity(String security) { this.security = security; }
        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }
        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }
        public String getFromAddress() { return fromAddress; }
        public void setFromAddress(String fromAddress) { this.fromAddress = fromAddress; }
    }

    @GET @Produces(MediaType.APPLICATION_JSON)
    public Response get() {
        if (!allowed()) return Response.PERMISSION_DENIED();
        return Response.OK(view());
    }

    @PUT @Consumes(MediaType.APPLICATION_JSON) @Produces(MediaType.APPLICATION_JSON)
    public Response save(SmtpBody body) {
        if (!allowed()) return Response.PERMISSION_DENIED();
        if (body == null || body.getHost() == null || body.getHost().trim().isEmpty() || body.getHost().trim().length() > 255
                || body.getHost().trim().matches(".*\\s.*")) {
            return Response.ERROR("error.smtp.host.invalid");
        }
        int port = body.getPort() == null ? 587 : body.getPort();
        if (port < 1 || port > 65535) return Response.ERROR("error.smtp.port.invalid");
        String security = body.getSecurity() == null ? "starttls" : body.getSecurity().toLowerCase();
        if (!security.equals("ssl") && !security.equals("starttls") && !security.equals("none")) return Response.ERROR("error.smtp.security.invalid");
        String from = body.getFromAddress() == null ? "" : body.getFromAddress().trim();
        if (!from.isEmpty() && !from.matches("^[^@\\s]+@[^@\\s]+$")) return Response.ERROR("error.smtp.from.invalid");

        SmtpOverride o = new SmtpOverride();
        o.setHost(body.getHost().trim());
        o.setPort(port);
        o.setSecurity(security);
        o.setUsername(body.getUsername() == null ? "" : body.getUsername().trim());
        o.setFromAddress(from);
        o.setUpdatedBy(SecurityContext.get().getCurrentUser().map(u -> u.getLogin()).orElse(""));
        try {
            dao.save(o, body.getPassword());
        } catch (RuntimeException e) {
            logger.error("Could not save the email settings: " + e.getMessage());
            return Response.ERROR("error.smtp.save.failed");
        }
        logger.info("Outgoing email settings changed by {}", o.getUpdatedBy());
        return Response.OK(view());
    }

    @DELETE @Produces(MediaType.APPLICATION_JSON)
    public Response clear() {
        if (!allowed()) return Response.PERMISSION_DENIED();
        dao.clear();
        return Response.OK(view());
    }

    /** Sends one message to the sign-in code address, so a wrong setting shows up now rather than at the next sign-in. */
    @POST @Path("/test") @Produces(MediaType.APPLICATION_JSON)
    public Response test() {
        if (!allowed()) return Response.PERMISSION_DENIED();
        String to = guard.recipient();
        String failure = email.sendEmailReport(to, "AMBIC MDM test email",
                "This is a test message from the AMBIC MDM console. If you can read it, sign-in and unlock codes will reach this address.", null);
        Map<String, Object> out = new HashMap<>();
        out.put("ok", failure == null);
        out.put("message", failure == null ? "Test email sent" : failure);
        out.put("sentTo", guard.maskedRecipient());
        return Response.OK(out);
    }

    private Map<String, Object> view() {
        SmtpOverride stored = dao.stored();
        Map<String, Object> m = new HashMap<>();
        m.put("configured", email.isConfigured());
        m.put("source", email.configSource());
        m.put("recipient", guard.maskedRecipient());
        m.put("deviceCheckActive", guard.enforcing());
        if (stored != null) {
            m.put("host", stored.getHost());
            m.put("port", stored.getPort());
            m.put("security", stored.getSecurity());
            m.put("username", stored.getUsername());
            m.put("fromAddress", stored.getFromAddress());
            m.put("hasPassword", stored.getPasswordEnc() != null && !stored.getPasswordEnc().isEmpty());
            m.put("updatedAt", stored.getUpdatedAt());
            m.put("updatedBy", stored.getUpdatedBy());
        }
        return m;
    }

    /** Super administrators and users who may change settings. */
    private static boolean allowed() {
        SecurityContext c = SecurityContext.get();
        return c != null && (c.isSuperAdmin() || c.hasPermission("settings"));
    }
}

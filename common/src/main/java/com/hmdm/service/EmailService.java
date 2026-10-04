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

package com.hmdm.service;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.event.EventService;
import com.hmdm.persistence.SmtpOverrideDAO;
import com.hmdm.persistence.domain.Customer;
import com.hmdm.persistence.domain.SmtpOverride;
import com.hmdm.util.StringUtil;
import liquibase.util.FileUtil;
import org.apache.commons.io.FileUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Named;
import javax.mail.*;
import javax.mail.internet.InternetAddress;
import javax.mail.internet.MimeBodyPart;
import javax.mail.internet.MimeMessage;
import javax.mail.internet.MimeMultipart;
import java.io.File;
import java.io.IOException;
import java.util.Properties;

/**
 * <p>A service to use for email sending.</p>
 *
 * @author seva
 */
@Singleton
public class EmailService {

    private static final Logger logger = LoggerFactory.getLogger(EmailService.class);

    private final String smtpHost;
    private final int smtpPort;
    private final boolean sslEnabled;
    private final boolean startTlsEnabled;
    private final String sslProtocols;
    private final String sslTrust;
    private final String smtpUsername;
    private final String smtpPassword;
    private final String smtpFrom;
    private final SmtpOverrideDAO overrides;

    private final String appName;
    private final String baseUrl;

    private final String recoveryEmailSubj;
    private final String recoveryEmailBody;
    private final String signupEmailSubj;
    private final String signupEmailBody;
    private final String signupCompleteEmailSubj;
    private final String signupCompleteEmailBody;

    @Inject
    public EmailService(@Named("smtp.host") String smtpHost,
                        @Named("smtp.port") int smtpPort,
                        @Named("smtp.ssl") boolean sslEnabled,
                        @Named("smtp.starttls") boolean startTlsEnabled,
                        @Named("smtp.ssl.protocols") String sslProtocols,
                        @Named("smtp.ssl.trust") String sslTrust,
                        @Named("smtp.username") String smtpUsername,
                        @Named("smtp.password") String smtpPassword,
                        @Named("smtp.from") String smtpFrom,
                        SmtpOverrideDAO overrides,
                        @Named("rebranding.name") String appName,
                        @Named("base.url") String baseUrl,
                        @Named("email.recovery.subj") String recoveryEmailSubj,
                        @Named("email.recovery.body") String recoveryEmailBody,
                        @Named("email.signup.subj") String signupEmailSubj,
                        @Named("email.signup.body") String signupEmailBody,
                        @Named("email.signup.complete.subj") String signupCompleteEmailSubj,
                        @Named("email.signup.complete.body") String signupCompleteEmailBody) {
        this.smtpHost = smtpHost;
        this.smtpPort = smtpPort;
        this.sslEnabled = sslEnabled;
        this.startTlsEnabled = startTlsEnabled;
        this.sslProtocols = sslProtocols;
        this.sslTrust = sslTrust;
        this.smtpUsername = smtpUsername;
        this.smtpPassword = smtpPassword;
        this.smtpFrom = smtpFrom;
        this.overrides = overrides;
        if (appName.equals("")) {
            appName = "Headwind MDM";
        }
        this.baseUrl = baseUrl;
        this.appName = appName;
        this.recoveryEmailSubj = recoveryEmailSubj;
        this.recoveryEmailBody = recoveryEmailBody;
        this.signupEmailSubj = signupEmailSubj;
        this.signupEmailBody = signupEmailBody;
        this.signupCompleteEmailSubj = signupCompleteEmailSubj;
        this.signupCompleteEmailBody = signupCompleteEmailBody;
    }

    /** The settings in force right now: those entered in the console if any, otherwise the server's SMTP_* values. */
    private static final class Cfg {
        String host; int port; boolean ssl; boolean startTls; String user; String pass; String from;
    }

    private Cfg cfg() {
        Cfg c = new Cfg();
        SmtpOverride o = overrides == null ? null : overrides.effective();
        if (o != null && o.getHost() != null && !o.getHost().trim().isEmpty()) {
            c.host = o.getHost().trim();
            c.port = o.getPort();
            c.ssl = "ssl".equals(o.getSecurity());
            c.startTls = "starttls".equals(o.getSecurity());
            c.user = o.getUsername() == null ? "" : o.getUsername();
            c.pass = o.getPassword() == null ? "" : o.getPassword();
            c.from = o.getFromAddress() != null && !o.getFromAddress().trim().isEmpty() ? o.getFromAddress().trim()
                    : (!c.user.isEmpty() ? c.user : smtpFrom);
        } else {
            c.host = smtpHost; c.port = smtpPort; c.ssl = sslEnabled; c.startTls = startTlsEnabled;
            c.user = smtpUsername; c.pass = smtpPassword; c.from = smtpFrom;
        }
        return c;
    }

    public boolean isConfigured() {
        return !cfg().host.equals("");
    }

    /** "console" when the settings were entered in the console, "server" when they come from the environment, "none" otherwise. */
    public String configSource() {
        SmtpOverride o = overrides == null ? null : overrides.effective();
        if (o != null && o.getHost() != null && !o.getHost().trim().isEmpty()) return "console";
        return smtpHost.equals("") ? "none" : "server";
    }


    public boolean sendEmail(String to, String subj, String body) {
        return sendEmail(to, subj, body, null);
    }

    public boolean sendEmail(String to, String subj, String body, String replyTo) {
        return sendEmailReport(to, subj, body, replyTo) == null;
    }

    /** Sends an email and returns null on success, or a short reason on failure (used by the console's "send test email"). */
    public String sendEmailReport(String to, String subj, String body, String replyTo) {
        final Cfg c = cfg();
        if (c.host.equals("")) {
            return "Outgoing email is not configured";
        }
        try {
            Properties properties = new Properties();
            properties.put("mail.smtp.host", c.host);
            properties.put("mail.smtp.port", c.port);
            properties.put("mail.smtp.auth", !c.user.equals(""));
            properties.put("mail.smtp.ssl.enable", c.ssl);
            properties.put("mail.smtp.starttls.enable", c.startTls);
            // A mail server that does not answer must never hang a request (sign-in sends its code through here).
            properties.put("mail.smtp.connectiontimeout", "10000");
            properties.put("mail.smtp.timeout", "15000");
            properties.put("mail.smtp.writetimeout", "15000");
            if (!StringUtil.isEmpty(sslProtocols)) {
                properties.put("mail.smtp.ssl.protocols", sslProtocols);
            }
            if (!StringUtil.isEmpty(sslTrust)) {
                properties.put("mail.smtp.ssl.trust", sslTrust);
            }

            logger.info("SMTP connection: " + c.host + ":" + c.port + ", ssl:" + c.ssl + ", startTls:" + c.startTls);

            Session session = Session.getInstance(properties, new Authenticator() {
                @Override
                protected PasswordAuthentication getPasswordAuthentication() {
                    return new PasswordAuthentication(c.user, c.pass);
                }
            });

            Message message = new MimeMessage(session);
            message.setFrom(new InternetAddress(c.from));
            message.setRecipients(Message.RecipientType.TO, InternetAddress.parse(to));
            if (replyTo != null && !replyTo.equals("")) {
                message.addHeader("Reply-To", replyTo);
            }
            message.setSubject(subj);

            MimeBodyPart mimeBodyPart = new MimeBodyPart();
            mimeBodyPart.setContent(body, "text/html; charset=utf-8");

            Multipart multipart = new MimeMultipart();
            multipart.addBodyPart(mimeBodyPart);

            message.setContent(multipart);

            Transport.send(message);

            return null;

        } catch (Exception e) {
            logger.warn(e.getMessage());
            String reason = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            return reason.length() > 300 ? reason.substring(0, 300) : reason;
        }
    }

    public String getRecoveryEmailSubj(String language) {
        return getLocalizedText(recoveryEmailSubj, language);
    }

    public String getRecoveryEmailBody(String language, String passwordResetToken) {
        String passwordResetUrl = baseUrl + "/#/passwordReset/" + passwordResetToken;

        return getLocalizedText(recoveryEmailBody, language)
                .replace("${passwordResetUrl}", passwordResetUrl);
    }

    public String getVerifyEmailSubj(String language) {
        return getLocalizedText(signupEmailSubj, language);
    }

    public String getVerifyEmailBody(String language, String verifyToken) {
        String signupCompleteUrl = baseUrl + "/#/signupComplete/" + verifyToken;

        return getLocalizedText(signupEmailBody, language)
                .replace("${signupCompleteUrl}", signupCompleteUrl);
    }

    public String getSignupCompleteEmailSubj(String language) {
        return getLocalizedText(signupCompleteEmailSubj, language);
    }


    public String getSignupCompleteEmailBody(Customer customer) {
        String deviceIds = customer.getPrefix() + "001, " +
                customer.getPrefix() + "002," +
                customer.getPrefix() + "003";

        return getLocalizedText(signupCompleteEmailBody, customer.getLanguage())
                .replace("${firstName}", customer.getFirstName())
                .replace("${lastName}", customer.getLastName())
                .replace("${customerName}", customer.getName())
                .replace("${deviceLimit}", "" + customer.getDeviceLimit())
                .replace("${sizeLimit}", "" + customer.getSizeLimit() + " Mb")
                .replace("${prefix}", customer.getPrefix())
                .replace("${deviceIds}", deviceIds);
    }

    public String getSignupNotifyEmailSubj() {
        return "New customer created at " + appName;
    }

    public String getSignupNotifyEmailBody(Customer customer) {
        int schemePos = baseUrl.indexOf("://");
        String server = schemePos != -1 ? baseUrl.substring(schemePos + 3) : baseUrl;

        StringBuilder builder = new StringBuilder();
        builder.append("Username: ");
        builder.append(customer.getName());
        builder.append("\n<br>");
        builder.append("Email: ");
        builder.append(customer.getEmail());
        builder.append("\n<br>");
        builder.append("Name: ");
        builder.append(customer.getFirstName());
        builder.append(" ");
        builder.append(customer.getLastName());
        builder.append("\n<br>");
        builder.append("Description: ");
        builder.append(customer.getDescription());
        builder.append("\n<br>");
        builder.append("Language: ");
        builder.append(customer.getLanguage());
        builder.append("\n<br>");
        builder.append("Server: ");
        builder.append(server);
        return builder.toString();
    }

    // Default language is English
    private String getLocalizedText(String path, String language) {
        if (language == null || language.equals("")) {
            language = "en";
        }

        File file = new File(path.replace("_LANGUAGE_", language));
        String ret = readFile(file);
        if (ret == null) {
            file = new File(path.replace("_LANGUAGE_", "en"));
            ret = readFile(file);
        }
        if (ret == null) {
            logger.error("Email template not found: " + file.getAbsolutePath());
            return null;
        }

        return ret
                .replace("${baseUrl}", baseUrl)
                .replace("${appName}", appName);
    }

    private String readFile(File file) {
        if (file.exists()) {
            try {
                return FileUtils.readFileToString(file, "UTF-8");
            } catch (IOException e) {
                logger.error("Failed to read email template: " + file.getAbsolutePath());
                return null;
            }
        }
        return null;
    }

}

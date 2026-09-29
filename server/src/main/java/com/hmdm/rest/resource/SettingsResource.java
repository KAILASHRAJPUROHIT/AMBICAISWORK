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

import javax.inject.Inject;
import javax.inject.Singleton;
import javax.ws.rs.Consumes;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;

import com.hmdm.persistence.CustomerDAO;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.UserRoleSettingsDAO;
import com.hmdm.persistence.domain.UserRoleSettings;
import com.hmdm.security.SecurityContext;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.Authorization;
import com.hmdm.persistence.CommonDAO;
import com.hmdm.persistence.domain.Settings;
import com.hmdm.rest.json.Response;
import com.hmdm.util.PasswordUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Optional;

@Api(tags = {"Settings"}, authorizations = {@Authorization("Bearer Token")})
@Singleton
@Path("/private/settings")
public class SettingsResource {

    private static final Logger log = LoggerFactory.getLogger(SettingsResource.class);

    private CommonDAO commonDAO;
    private UserRoleSettingsDAO userRoleSettingsDAO;
    private UnsecureDAO unsecureDAO;

    /**
     * <p>A constructor required by Swagger.</p>
     */
    public SettingsResource() {
    }

    /** Public address of this server (BASE_URL), used to complete relative branding image paths. */
    private final String baseUrl;

    @Inject
    public SettingsResource(CommonDAO commonDAO, UserRoleSettingsDAO userRoleSettingsDAO, UnsecureDAO unsecureDAO,
                            @javax.inject.Named("base.url") String baseUrl) {
        this.baseUrl = baseUrl == null ? "" : baseUrl.trim().replaceAll("/+$", "");
        this.commonDAO = commonDAO;
        this.userRoleSettingsDAO = userRoleSettingsDAO;
        this.unsecureDAO = unsecureDAO;
    }

    // =================================================================================================================
    @ApiOperation(
            value = "Get settings",
            notes = "Gets the current settings",
            response = Settings.class
    )
    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response getSettings() {
        try {
            Settings settings = Optional.ofNullable(this.commonDAO.getSettings()).orElse(new Settings());
            settings.setSingleCustomer(unsecureDAO.isSingleCustomer());
            if (!settings.isSingleCustomer()) {
                this.commonDAO.loadCustomerSettings(settings);
            }
            return Response.OK(settings);
        } catch (Exception e) {
            log.error("Unexpected error when getting the settings for customer", e);
            return Response.INTERNAL_ERROR();
        }
    }

    // =================================================================================================================
    @ApiOperation(
            value = "Get user role settings",
            notes = "Gets the current settings for role of the current user",
            response = UserRoleSettings.class
    )
    @GET
    @Path("/userRole/{roleId}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getUserRoleSettings(@PathParam("roleId") int roleId) {
        try {
            UserRoleSettings settings = this.userRoleSettingsDAO.getUserRoleSettings(roleId);
            if (settings == null) {
                final UserRoleSettings defaultSettings = new UserRoleSettings();
                defaultSettings.setRoleId(roleId);

                settings = defaultSettings;
            }
            return Response.OK(settings);
        } catch (Exception e) {
            log.error("Unexpected error when getting the user role settings for current user", e);
            return Response.INTERNAL_ERROR();
        }
    }

    // =================================================================================================================
    @ApiOperation(
            value = "Save default design",
            notes = "Save the settings for Default Design for mobile application",
            response = Settings.class
    )
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/design")
    public Response updateDefaultDesignSettings(Settings settings) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to update settings by user " +
                    SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        try {
            this.commonDAO.saveDefaultDesignSettings(settings);
            return Response.OK();
        } catch (Exception e) {
            log.error("Unexpected error when saving default design settings", e);
            return Response.INTERNAL_ERROR();
        }
    }

    // =================================================================================================================
    @ApiOperation(
            value = "Save user role common settings",
            notes = "Save the settings for user roles",
            response = Settings.class
    )
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/userRoles/common")
    public Response updateUserRoleCommonSettings(List<UserRoleSettings> settings) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to update settings by user " +
                    SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        try {
            this.userRoleSettingsDAO.saveCommonSettings(settings);
            return Response.OK();
        } catch (Exception e) {
            log.error("Unexpected error when saving user roles common settings", e);
            return Response.INTERNAL_ERROR();
        }
    }

    // =================================================================================================================
    @ApiOperation(
            value = "Save language settings",
            notes = "Save the language settings for MDM web application",
            response = Settings.class
    )
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/lang")
    public Response updateLanguageSettings(Settings settings) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to update settings by user " +
                    SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        try {
            this.commonDAO.saveLanguageSettings(settings);
            return Response.OK();
        } catch (Exception e) {
            log.error("Unexpected error when saving language settings", e);
            return Response.INTERNAL_ERROR();
        }
    }

    // =================================================================================================================
    @ApiOperation(
            value = "Save misc settings",
            notes = "Save the misc settings for MDM web application",
            response = Settings.class
    )
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/misc")
    public Response updateMiscSettings(Settings settings) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to update settings by user " +
                    SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        try {
            if (!unsecureDAO.isSingleCustomer()) {
                // These settings are not allowed to setup in multi-tenant mode
                settings.setCreateNewDevices(false);
                settings.setNewDeviceGroupId(null);
                settings.setNewDeviceConfigurationId(null);
            }
            this.commonDAO.saveMiscSettings(settings);
            return Response.OK();
        } catch (Exception e) {
            log.error("Unexpected error when saving misc settings", e);
            return Response.INTERNAL_ERROR();
        }
    }

    // =================================================================================================================
    @ApiOperation(
            value = "Set the fleet-wide admin passcode",
            notes = "Sets (or clears, when passcode is blank) the admin passcode that gates local kiosk exit " +
                    "on every enrolled device. Only its hash is ever stored — the raw value never leaves this call.",
            response = Response.class
    )
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/adminPasscode")
    public Response updateAdminPasscode(AdminPasscodeRequest request) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to update the admin passcode by user " +
                    SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        try {
            String raw = request == null ? null : request.getPasscode();
            Settings settings = new Settings();
            settings.setAdminPasscodeHash(
                    (raw == null || raw.trim().isEmpty()) ? null : PasswordUtil.getHashFromRaw(raw.trim())
            );
            this.commonDAO.saveAdminPasscodeHash(settings);
            return Response.OK();
        } catch (Exception e) {
            log.error("Unexpected error when saving the admin passcode", e);
            return Response.INTERNAL_ERROR();
        }
    }

    /**
     * Client branding: the customer's own name/logo, shown on its devices (kiosk, agent screen)
     * and in the console. AMBIC DIGITAL remains the product brand. Blank values clear a field.
     */
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/clientBranding")
    public Response updateClientBranding(ClientBrandingRequest request) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to update client branding by user " +
                    SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        try {
            Settings settings = new Settings();
            settings.setClientName(trimOrNull(request == null ? null : request.getName(), 120));
            settings.setClientLogoUrl(httpUrlOrNull(request == null ? null : request.getLogoUrl()));
            settings.setClientMarkUrl(httpUrlOrNull(request == null ? null : request.getMarkUrl()));
            this.commonDAO.saveClientBranding(settings);
            return Response.OK();
        } catch (Exception e) {
            log.error("Unexpected error when saving client branding", e);
            return Response.INTERNAL_ERROR();
        }
    }

    /** Kiosk sections the admin can switch on/off. Anything else in a request is ignored. */
    private static final java.util.List<String> KIOSK_SECTIONS = java.util.Arrays.asList(
            "leaderboard", "quickControls", "clientLogo", "clockCard", "statusPills");

    /**
     * Switches kiosk sections on/off for every managed device. The body is a map of section key to
     * boolean; only known keys are kept, and only {@code false} is stored (a missing key means on).
     * Devices pick the result up on their next check-in.
     */
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    @Path("/kioskSections")
    public Response updateKioskSections(java.util.Map<String, Boolean> request) {
        if (!SecurityContext.get().hasPermission("settings")) {
            log.error("Unauthorized attempt to update kiosk sections by user " +
                    SecurityContext.get().getCurrentUserName());
            return Response.PERMISSION_DENIED();
        }
        try {
            StringBuilder json = new StringBuilder("{");
            if (request != null) {
                for (String key : KIOSK_SECTIONS) {
                    if (Boolean.FALSE.equals(request.get(key))) {
                        if (json.length() > 1) json.append(',');
                        json.append('"').append(key).append("\":false");
                    }
                }
            }
            json.append('}');
            Settings settings = new Settings();
            settings.setKioskSections(json.length() > 2 ? json.toString() : null);
            this.commonDAO.saveKioskSections(settings);
            return Response.OK();
        } catch (Exception e) {
            log.error("Unexpected error when saving kiosk sections", e);
            return Response.INTERNAL_ERROR();
        }
    }

    private static String trimOrNull(String v, int max) {
        if (v == null || v.trim().isEmpty()) return null;
        String t = v.trim();
        return t.length() > max ? t.substring(0, max) : t;
    }

    private static final java.util.regex.Pattern BRANDING_PATH =
            java.util.regex.Pattern.compile("^(?:/[A-Za-z0-9_-]+)*/public/client-branding/(logo|mark)\\.png$");

    /**
     * Branding image address for devices. A full http(s) URL is kept. A root-relative path to one of
     * this server's own branding images (what a console served from this same server sends, e.g.
     * {@code /rest/public/client-branding/logo.png}) is completed with the server's public address,
     * because devices need a full URL. Anything else is dropped so a console mistake cannot point
     * managed devices at an unexpected place. (The relative form used to be dropped silently, which
     * left devices with no logo even though the console said "Branding saved".)
     */
    private String httpUrlOrNull(String v) {
        String t = trimOrNull(v, 2000);
        if (t == null) return null;
        String lower = t.toLowerCase();
        if (lower.startsWith("https://") || lower.startsWith("http://")) return t;
        java.util.regex.Matcher m = BRANDING_PATH.matcher(t);
        if (m.matches() && !baseUrl.isEmpty()) {
            return baseUrl + "/rest/public/client-branding/" + m.group(1) + ".png";
        }
        return null;
    }

    /** Body of {@link #updateClientBranding}. */
    public static class ClientBrandingRequest {
        private String name;
        private String logoUrl;
        private String markUrl;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public String getLogoUrl() { return logoUrl; }
        public void setLogoUrl(String logoUrl) { this.logoUrl = logoUrl; }
        public String getMarkUrl() { return markUrl; }
        public void setMarkUrl(String markUrl) { this.markUrl = markUrl; }
    }

    /** Body of {@link #updateAdminPasscode}: the raw passcode (or blank/null to clear it). */
    public static class AdminPasscodeRequest {
        private String passcode;

        public String getPasscode() {
            return passcode;
        }

        public void setPasscode(String passcode) {
            this.passcode = passcode;
        }
    }
}

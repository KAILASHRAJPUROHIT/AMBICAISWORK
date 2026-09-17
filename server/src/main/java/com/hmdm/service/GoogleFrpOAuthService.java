package com.hmdm.service;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.FrpRecoveryAccountDAO;
import com.hmdm.persistence.domain.FrpOAuthState;
import com.hmdm.persistence.domain.FrpRecoveryAccount;
import org.json.JSONArray;
import org.json.JSONObject;

import javax.net.ssl.HttpsURLConnection;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * Server-side OAuth code flow for one tenant's EFRP recovery accounts. It deliberately never
 * receives a Google password and discards access/ID tokens immediately after People API lookup.
 */
@Singleton
public class GoogleFrpOAuthService {
    private static final long STATE_TTL_MS = 10L * 60L * 1000L;
    private static final SecureRandom RANDOM = new SecureRandom();
    private final FrpRecoveryAccountDAO dao;
    private final String redirectUri;
    private final String clientId;
    private final String clientSecret;

    @Inject
    public GoogleFrpOAuthService(FrpRecoveryAccountDAO dao) {
        this.dao = dao;
        this.clientId = setting("AMBIC_GOOGLE_OAUTH_CLIENT_ID");
        this.clientSecret = setting("AMBIC_GOOGLE_OAUTH_CLIENT_SECRET");
        this.redirectUri = setting("AMBIC_GOOGLE_OAUTH_REDIRECT_URI");
    }

    public boolean isConfigured() {
        return !clientId.isEmpty() && !clientSecret.isEmpty() && !redirectUri.isEmpty();
    }

    public String begin(int customerId, Integer userId) {
        requireConfigured();
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        String state = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        FrpOAuthState row = new FrpOAuthState();
        row.setStateHash(sha256(state));
        row.setCustomerId(customerId);
        row.setUserId(userId);
        row.setExpiresAt(System.currentTimeMillis() + STATE_TTL_MS);
        dao.insertState(row);
        return "https://accounts.google.com/o/oauth2/v2/auth?client_id=" + enc(clientId)
                + "&redirect_uri=" + enc(redirectUri)
                + "&response_type=code&scope=" + enc("openid email https://www.googleapis.com/auth/userinfo.profile")
                + "&state=" + enc(state) + "&prompt=select_account&access_type=online";
    }

    /** Completes one code exchange and persists only display email + numeric People resource ID. */
    public void complete(String opaqueState, String code) throws Exception {
        requireConfigured();
        if (opaqueState == null || code == null || opaqueState.isEmpty() || code.isEmpty()) {
            throw new IllegalArgumentException("Missing OAuth state or authorization code");
        }
        FrpOAuthState state = dao.findState(sha256(opaqueState));
        if (state == null || state.getConsumedAt() != null || state.getExpiresAt() <= System.currentTimeMillis()) {
            throw new IllegalArgumentException("Expired or invalid OAuth state");
        }
        JSONObject token = postForm("https://oauth2.googleapis.com/token",
                "code=" + enc(code) + "&client_id=" + enc(clientId) + "&client_secret=" + enc(clientSecret)
                        + "&redirect_uri=" + enc(redirectUri) + "&grant_type=authorization_code");
        String accessToken = token.optString("access_token", "");
        if (accessToken.isEmpty()) throw new IllegalStateException("Google did not return an access token");
        JSONObject person = getJson("https://people.googleapis.com/v1/people/me?personFields=metadata,emailAddresses", accessToken);
        String resourceName = person.optString("resourceName", "");
        if (!resourceName.matches("people/[1-9][0-9]{0,29}")) {
            throw new IllegalStateException("Google returned no numeric People user ID");
        }
        String email = primaryEmail(person.optJSONArray("emailAddresses"));
        if (email.isEmpty()) throw new IllegalStateException("Google returned no verified display email");
        // Claim the state before writing. A second callback cannot attach the same authorization.
        if (!dao.consumeState(state.getId())) throw new IllegalStateException("OAuth state was already consumed");
        FrpRecoveryAccount account = new FrpRecoveryAccount();
        account.setCustomerId(state.getCustomerId());
        account.setGoogleUserId(resourceName.substring("people/".length()));
        account.setEmail(email);
        account.setConnectedByUserId(state.getUserId());
        account.setConnectedAt(System.currentTimeMillis());
        dao.upsert(account);
    }

    private static String primaryEmail(JSONArray emails) {
        if (emails == null) return "";
        String fallback = "";
        for (int i = 0; i < emails.length(); i++) {
            JSONObject item = emails.optJSONObject(i);
            if (item == null) continue;
            String value = item.optString("value", "").trim();
            if (value.isEmpty()) continue;
            if (fallback.isEmpty()) fallback = value;
            if (item.optJSONObject("metadata") != null && item.getJSONObject("metadata").optBoolean("primary")) return value;
        }
        return fallback;
    }

    private static JSONObject postForm(String url, String body) throws Exception {
        HttpsURLConnection c = (HttpsURLConnection) new java.net.URL(url).openConnection();
        c.setConnectTimeout(15000); c.setReadTimeout(15000); c.setRequestMethod("POST"); c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        c.setFixedLengthStreamingMode(data.length);
        try (OutputStream out = c.getOutputStream()) { out.write(data); }
        return jsonResponse(c);
    }

    private static JSONObject getJson(String url, String accessToken) throws Exception {
        HttpsURLConnection c = (HttpsURLConnection) new java.net.URL(url).openConnection();
        c.setConnectTimeout(15000); c.setReadTimeout(15000);
        c.setRequestProperty("Authorization", "Bearer " + accessToken);
        return jsonResponse(c);
    }

    private static JSONObject jsonResponse(HttpsURLConnection c) throws Exception {
        int status = c.getResponseCode();
        InputStream stream = status >= 200 && status < 300 ? c.getInputStream() : c.getErrorStream();
        StringBuilder body = new StringBuilder();
        if (stream != null) try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line; while ((line = reader.readLine()) != null) body.append(line);
        }
        if (status < 200 || status >= 300) throw new IllegalStateException("Google OAuth request failed (HTTP " + status + ")");
        return new JSONObject(body.toString());
    }

    private void requireConfigured() {
        if (!isConfigured()) throw new IllegalStateException("Google OAuth is not configured on this MDM server");
    }
    private static String setting(String name) {
        String value = System.getProperty(name);
        if (value == null || value.trim().isEmpty()) value = System.getenv(name);
        return value == null ? "" : value.trim();
    }
    private static String enc(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (java.io.UnsupportedEncodingException e) {
            throw new IllegalStateException("UTF-8 unavailable", e);
        }
    }
    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(64);
            for (byte b : digest) out.append(String.format("%02x", b));
            return out.toString();
        } catch (Exception e) { throw new IllegalStateException("SHA-256 unavailable", e); }
    }
}

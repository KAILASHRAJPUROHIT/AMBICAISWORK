package com.hmdm.service;

import com.google.inject.Singleton;
import com.hmdm.util.AwsSigV4Signer;
import org.json.JSONArray;
import org.json.JSONObject;

import javax.net.ssl.HttpsURLConnection;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

/**
 * Exchanges this EC2 instance's IMDSv2 identity for a Google access token scoped to whatever the
 * caller asks for (androidmanagement, firebase.messaging, ...), via Workload Identity Federation -
 * no AWS SDK, no Google SDK, matching this codebase's existing raw-HTTP style (see
 * GoogleFrpOAuthService). One impersonated service account, many possible scopes - each scope
 * caches its own token independently since Google issues a token bound to the exact scope set
 * requested.
 *
 * The exact request shapes (subject-token JSON envelope, STS form fields, impersonation body) were
 * copied from reading google-auth-library-python's own aws.py/external_account.py/sts.py/
 * impersonated_credentials.py source directly on the EC2 box where the Python check already passes -
 * this is a faithful Java port of that already-verified flow, not a reconstruction from docs.
 */
@Singleton
public class GoogleWifTokenService {
    private static final String STS_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange";
    private static final String STS_REQUESTED_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token";
    private static final long IMPERSONATION_LIFETIME_SECONDS = 3600L;
    private static final long REFRESH_MARGIN_MS = 2L * 60 * 1000; // refresh 2 minutes before expiry
    private static final Pattern FRACTIONAL_SECONDS = Pattern.compile("\\.\\d+(?=Z$)");

    /** Well-known scopes so callers don't retype the URL. */
    public static final String SCOPE_ANDROID_MANAGEMENT = "https://www.googleapis.com/auth/androidmanagement";
    public static final String SCOPE_FIREBASE_MESSAGING = "https://www.googleapis.com/auth/firebase.messaging";

    /** The scope the federated (STS-exchanged) token itself must carry to be allowed to call
     *  iamcredentials.googleapis.com:generateAccessToken at all — verified against
     *  google-auth-library-python's own iam.py (`_IAM_SCOPE`) and impersonated_credentials.py
     *  ("Service account source credentials must have the _IAM_SCOPE"). This is INDEPENDENT of
     *  whatever target scope (androidmanagement, firebase.messaging, ...) is being impersonated —
     *  the target scope only appears in the generateAccessToken request body, never as the OAuth
     *  scope of the bearer token calling it. Using a target scope here instead (as an earlier
     *  version of this file did) fails with HTTP 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT the moment the
     *  target scope isn't broad enough to also cover IAM Credentials API access. */
    private static final String SCOPE_IAM = "https://www.googleapis.com/auth/iam";

    private static final class CachedToken {
        volatile String accessToken;
        volatile long expiryMillis;
    }

    private final Map<String, CachedToken> cacheByScope = new ConcurrentHashMap<>();

    /** Returns a cached access token for this scope, refreshing it if near expiry. */
    public String getAccessToken(String scope) {
        CachedToken cached = cacheByScope.computeIfAbsent(scope, s -> new CachedToken());
        String token = cached.accessToken;
        if (token != null && System.currentTimeMillis() < cached.expiryMillis - REFRESH_MARGIN_MS) {
            return token;
        }
        synchronized (cached) {
            if (cached.accessToken != null && System.currentTimeMillis() < cached.expiryMillis - REFRESH_MARGIN_MS) {
                return cached.accessToken;
            }
            try {
                refresh(scope, cached);
            } catch (Exception e) {
                throw new IllegalStateException("Unable to acquire Google WIF access token for scope " + scope, e);
            }
            return cached.accessToken;
        }
    }

    private void refresh(String scope, CachedToken cached) throws Exception {
        JSONObject config = loadCredentialConfig();
        JSONObject credentialSource = config.getJSONObject("credential_source");

        String imdsv2Token = fetchImdsv2Token(credentialSource.getString("imdsv2_session_token_url"));
        String region = fetchRegion(credentialSource.getString("region_url"), imdsv2Token);
        JSONObject awsCredentials = fetchAwsCredentials(credentialSource.getString("url"), imdsv2Token);

        String audience = config.getString("audience");
        String subjectToken = buildSubjectToken(region, awsCredentials,
                credentialSource.getString("regional_cred_verification_url"), audience);

        String subjectTokenType = config.getString("subject_token_type");
        String federatedToken = exchangeForFederatedToken(config.getString("token_url"), audience,
                subjectToken, subjectTokenType);

        JSONObject impersonated = impersonateServiceAccount(
                config.getString("service_account_impersonation_url"), federatedToken, scope);

        cached.accessToken = impersonated.getString("accessToken");
        cached.expiryMillis = parseExpireTime(impersonated.getString("expireTime"));
    }

    private JSONObject loadCredentialConfig() throws Exception {
        String path = setting("AMBIC_GOOGLE_WIF_CONFIG");
        if (path.isEmpty()) path = "/etc/ambic-mdm/google-wif.json";
        String json = new String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8);
        return new JSONObject(json);
    }

    private static String fetchImdsv2Token(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(5000); c.setReadTimeout(5000);
        c.setRequestMethod("PUT");
        c.setRequestProperty("X-aws-ec2-metadata-token-ttl-seconds", "300");
        return textResponse(c);
    }

    private static String fetchRegion(String regionUrl, String imdsv2Token) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(regionUrl).openConnection();
        c.setConnectTimeout(5000); c.setReadTimeout(5000);
        c.setRequestProperty("X-aws-ec2-metadata-token", imdsv2Token);
        String availabilityZone = textResponse(c);
        return availabilityZone.substring(0, availabilityZone.length() - 1); // strip trailing AZ letter
    }

    private static JSONObject fetchAwsCredentials(String baseUrl, String imdsv2Token) throws Exception {
        HttpURLConnection roleConn = (HttpURLConnection) new URL(baseUrl).openConnection();
        roleConn.setConnectTimeout(5000); roleConn.setReadTimeout(5000);
        roleConn.setRequestProperty("X-aws-ec2-metadata-token", imdsv2Token);
        String roleName = textResponse(roleConn);

        HttpURLConnection credsConn = (HttpURLConnection) new URL(baseUrl + "/" + roleName).openConnection();
        credsConn.setConnectTimeout(5000); credsConn.setReadTimeout(5000);
        credsConn.setRequestProperty("X-aws-ec2-metadata-token", imdsv2Token);
        return new JSONObject(textResponse(credsConn));
    }

    /** Builds and signs the AWS GetCallerIdentity request, then serializes it into Google's AWS subject-token envelope. */
    private static String buildSubjectToken(String region, JSONObject awsCredentials, String regionalCredVerificationUrlTemplate, String audience) {
        String regionalUrl = regionalCredVerificationUrlTemplate.replace("{region}", region);
        String accessKeyId = awsCredentials.getString("AccessKeyId");
        String secretAccessKey = awsCredentials.getString("SecretAccessKey");
        String sessionToken = awsCredentials.optString("Token", null);

        Map<String, String> headers = AwsSigV4Signer.signGetCallerIdentity(region, accessKeyId, secretAccessKey, sessionToken);
        // Added after signing - not part of the AWS signature, only carried for Google's own integrity check.
        headers.put("x-goog-cloud-target-resource", audience);

        JSONArray headerArray = new JSONArray();
        for (Map.Entry<String, String> e : headers.entrySet()) {
            headerArray.put(new JSONObject().put("key", e.getKey()).put("value", e.getValue()));
        }
        JSONObject signedRequest = new JSONObject();
        signedRequest.put("url", regionalUrl);
        signedRequest.put("method", "POST");
        signedRequest.put("headers", headerArray);

        return enc(signedRequest.toString());
    }

    /** The STS token-exchange step always requests {@link #SCOPE_IAM} — the federated token is a
     *  stepping stone that only ever gets used for ONE thing (calling generateAccessToken below),
     *  never directly against any target API, so it must carry the scope THAT call needs, not the
     *  final target scope. See {@link #SCOPE_IAM}'s doc comment for how this was verified. */
    private static String exchangeForFederatedToken(String tokenUrl, String audience, String subjectToken, String subjectTokenType) throws Exception {
        String body = "grant_type=" + enc(STS_GRANT_TYPE)
                + "&audience=" + enc(audience)
                + "&scope=" + enc(SCOPE_IAM)
                + "&requested_token_type=" + enc(STS_REQUESTED_TOKEN_TYPE)
                + "&subject_token=" + enc(subjectToken)
                + "&subject_token_type=" + enc(subjectTokenType);
        JSONObject response = postForm(tokenUrl, body);
        String accessToken = response.optString("access_token", "");
        if (accessToken.isEmpty()) throw new IllegalStateException("Google STS did not return a federated access_token");
        return accessToken;
    }

    private static JSONObject impersonateServiceAccount(String impersonationUrl, String federatedToken, String scope) throws Exception {
        JSONObject body = new JSONObject();
        body.put("delegates", new JSONArray());
        body.put("scope", new JSONArray().put(scope));
        body.put("lifetime", IMPERSONATION_LIFETIME_SECONDS + "s");

        HttpsURLConnection c = (HttpsURLConnection) new URL(impersonationUrl).openConnection();
        c.setConnectTimeout(15000); c.setReadTimeout(15000); c.setRequestMethod("POST"); c.setDoOutput(true);
        c.setRequestProperty("Authorization", "Bearer " + federatedToken);
        c.setRequestProperty("Content-Type", "application/json");
        byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
        c.setFixedLengthStreamingMode(data.length);
        try (OutputStream out = c.getOutputStream()) { out.write(data); }
        JSONObject response = jsonResponse(c);
        if (!response.has("accessToken") || !response.has("expireTime")) {
            throw new IllegalStateException("Google IAM impersonation response missing accessToken/expireTime");
        }
        return response;
    }

    private static long parseExpireTime(String rfc3339) {
        // Java 8's Instant.parse is strict about fractional-second digit counts; we don't need
        // sub-second precision here (a 2-minute refresh margin already covers any clock skew).
        String normalized = FRACTIONAL_SECONDS.matcher(rfc3339).replaceAll("");
        return Instant.parse(normalized).toEpochMilli();
    }

    private static JSONObject postForm(String url, String body) throws Exception {
        HttpsURLConnection c = (HttpsURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(15000); c.setReadTimeout(15000); c.setRequestMethod("POST"); c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        c.setFixedLengthStreamingMode(data.length);
        try (OutputStream out = c.getOutputStream()) { out.write(data); }
        return jsonResponse(c);
    }

    private static String textResponse(HttpURLConnection c) throws Exception {
        int status = c.getResponseCode();
        InputStream stream = status >= 200 && status < 300 ? c.getInputStream() : c.getErrorStream();
        StringBuilder body = new StringBuilder();
        if (stream != null) try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line; while ((line = reader.readLine()) != null) body.append(line);
        }
        if (status < 200 || status >= 300) throw new IllegalStateException("Request to " + c.getURL() + " failed (HTTP " + status + "): " + body);
        return body.toString();
    }

    private static JSONObject jsonResponse(HttpsURLConnection c) throws Exception {
        int status = c.getResponseCode();
        InputStream stream = status >= 200 && status < 300 ? c.getInputStream() : c.getErrorStream();
        StringBuilder body = new StringBuilder();
        if (stream != null) try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line; while ((line = reader.readLine()) != null) body.append(line);
        }
        if (status < 200 || status >= 300) throw new IllegalStateException("Request to " + c.getURL() + " failed (HTTP " + status + "): " + body);
        return new JSONObject(body.toString());
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
}

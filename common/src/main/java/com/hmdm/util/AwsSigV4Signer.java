package com.hmdm.util;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Signs a single AWS "GetCallerIdentity" request against the regional STS endpoint, per AWS's
 * SigV4 algorithm (https://docs.aws.amazon.com/general/latest/gr/sigv4_signing.html). Used only to
 * build the AWS subject token Google's Workload Identity Federation expects - no AWS SDK involved,
 * this is the entire signing surface this project needs.
 *
 * Method is POST with an empty body (params live in the query string) - this must match exactly
 * what google-auth's own AWS credential source signs (verified by reading
 * google/auth/aws.py::RequestSigner.get_request_options in the working WIF venv on EC2, which
 * hardcodes method="POST" even though STS also accepts GET for this action). Signing it as GET
 * produces a signature Google's STS token exchange will silently reject.
 */
public class AwsSigV4Signer {
    private static final DateTimeFormatter AMZ_DATE = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC);
    private static final DateTimeFormatter DATE_STAMP = DateTimeFormatter.ofPattern("yyyyMMdd").withZone(ZoneOffset.UTC);
    private static final String SERVICE = "sts";
    private static final String ALGORITHM = "AWS4-HMAC-SHA256";

    /** Returns the headers (Authorization, X-Amz-Date, X-Amz-Security-Token, Host) to attach to the GetCallerIdentity GET request. */
    public static Map<String, String> signGetCallerIdentity(String region, String accessKeyId, String secretAccessKey, String sessionToken) {
        Instant now = Instant.now();
        String amzDate = AMZ_DATE.format(now);
        String dateStamp = DATE_STAMP.format(now);
        String host = "sts." + region + ".amazonaws.com";
        String canonicalQueryString = "Action=GetCallerIdentity&Version=2011-06-15";
        String emptyPayloadHash = sha256Hex("");

        Map<String, String> headersToSign = new LinkedHashMap<>();
        headersToSign.put("host", host);
        headersToSign.put("x-amz-date", amzDate);
        if (sessionToken != null && !sessionToken.isEmpty()) {
            headersToSign.put("x-amz-security-token", sessionToken);
        }

        StringBuilder canonicalHeaders = new StringBuilder();
        StringBuilder signedHeaders = new StringBuilder();
        for (Map.Entry<String, String> e : headersToSign.entrySet()) {
            canonicalHeaders.append(e.getKey()).append(':').append(e.getValue()).append('\n');
            if (signedHeaders.length() > 0) signedHeaders.append(';');
            signedHeaders.append(e.getKey());
        }

        String canonicalRequest = "POST\n/\n" + canonicalQueryString + "\n" + canonicalHeaders + "\n" + signedHeaders + "\n" + emptyPayloadHash;

        String credentialScope = dateStamp + "/" + region + "/" + SERVICE + "/aws4_request";
        String stringToSign = ALGORITHM + "\n" + amzDate + "\n" + credentialScope + "\n" + sha256Hex(canonicalRequest);

        byte[] signingKey = deriveSigningKey(secretAccessKey, dateStamp, region);
        String signature = hex(hmacSha256(signingKey, stringToSign));

        String authorization = ALGORITHM + " Credential=" + accessKeyId + "/" + credentialScope
                + ", SignedHeaders=" + signedHeaders + ", Signature=" + signature;

        Map<String, String> result = new LinkedHashMap<>();
        result.put("Host", host);
        result.put("X-Amz-Date", amzDate);
        if (sessionToken != null && !sessionToken.isEmpty()) {
            result.put("X-Amz-Security-Token", sessionToken);
        }
        result.put("Authorization", authorization);
        return result;
    }

    public static String regionalStsUrl(String region) {
        return "https://sts." + region + ".amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15";
    }

    private static byte[] deriveSigningKey(String secretAccessKey, String dateStamp, String region) {
        byte[] kSecret = ("AWS4" + secretAccessKey).getBytes(StandardCharsets.UTF_8);
        byte[] kDate = hmacSha256(kSecret, dateStamp);
        byte[] kRegion = hmacSha256(kDate, region);
        byte[] kService = hmacSha256(kRegion, SERVICE);
        return hmacSha256(kService, "aws4_request");
    }

    private static byte[] hmacSha256(byte[] key, String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException("HmacSHA256 unavailable", e);
        }
    }

    private static String sha256Hex(String value) {
        try {
            return hex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) out.append(String.format("%02x", b));
        return out.toString();
    }
}

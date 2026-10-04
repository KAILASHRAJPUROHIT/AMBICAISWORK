package com.hmdm.persistence;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.SmtpOverride;
import com.hmdm.persistence.mapper.SmtpOverrideMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import javax.inject.Named;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * Reads and writes the console-entered outgoing-email settings. The password is encrypted with AES-GCM under a key derived
 * from the server's {@code hash.secret}, so a database copy alone does not reveal it. Reads are cached for 20 seconds so
 * every email send does not hit the database.
 */
@Singleton
public class SmtpOverrideDAO {
    private static final Logger logger = LoggerFactory.getLogger(SmtpOverrideDAO.class);
    private static final long CACHE_MS = 20_000L;

    private final SmtpOverrideMapper mapper;
    private final byte[] key;
    private final SecureRandom random = new SecureRandom();
    private volatile SmtpOverride cached;
    private volatile long cachedAt;
    private volatile boolean loaded;

    @Inject
    public SmtpOverrideDAO(SmtpOverrideMapper mapper, @Named("hash.secret") String hashSecret) {
        this.mapper = mapper;
        this.key = sha256(("ambic-smtp-v1:" + (hashSecret == null ? "" : hashSecret)).getBytes(StandardCharsets.UTF_8));
    }

    /** The settings in force, with the password decrypted, or null when the server's own SMTP_* values apply. */
    public SmtpOverride effective() {
        long now = System.currentTimeMillis();
        if (!loaded || now - cachedAt > CACHE_MS) {
            SmtpOverride o = null;
            try {
                o = mapper.get();
                if (o != null && o.getPasswordEnc() != null && !o.getPasswordEnc().isEmpty()) {
                    o.setPassword(decrypt(o.getPasswordEnc()));
                }
            } catch (Exception e) {
                logger.warn("Could not read the email settings: " + e.getMessage());
                o = null;
            }
            cached = o;
            cachedAt = now;
            loaded = true;
        }
        return cached;
    }

    /** @param newPassword the new password, or null/empty to keep the one already stored. */
    public void save(SmtpOverride o, String newPassword) {
        SmtpOverride existing = mapper.get();
        if (newPassword != null && !newPassword.isEmpty()) {
            o.setPasswordEnc(encrypt(newPassword));
        } else {
            o.setPasswordEnc(existing == null ? null : existing.getPasswordEnc());
        }
        o.setUpdatedAt(System.currentTimeMillis());
        mapper.upsert(o);
        loaded = false;
    }

    public void clear() {
        mapper.clear();
        loaded = false;
    }

    /** What the console may show: never the password, only whether one is stored. */
    public SmtpOverride stored() {
        return mapper.get();
    }

    private String encrypt(String plain) {
        try {
            byte[] iv = new byte[12];
            random.nextBytes(iv);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, iv));
            byte[] ct = c.doFinal(plain.getBytes(StandardCharsets.UTF_8));
            byte[] out = new byte[iv.length + ct.length];
            System.arraycopy(iv, 0, out, 0, iv.length);
            System.arraycopy(ct, 0, out, iv.length, ct.length);
            return Base64.getEncoder().encodeToString(out);
        } catch (Exception e) {
            throw new IllegalStateException("Could not protect the email password", e);
        }
    }

    private String decrypt(String stored) {
        try {
            byte[] in = Base64.getDecoder().decode(stored);
            byte[] iv = java.util.Arrays.copyOfRange(in, 0, 12);
            byte[] ct = java.util.Arrays.copyOfRange(in, 12, in.length);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, iv));
            return new String(c.doFinal(ct), StandardCharsets.UTF_8);
        } catch (Exception e) {
            logger.warn("Stored email password could not be decrypted (was the server secret changed?)");
            return "";
        }
    }

    private static byte[] sha256(byte[] in) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(in);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}

package com.hmdm.service;

import org.junit.Test;

import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.spec.MGF1ParameterSpec;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/** Ensures the browser-compatible RSA-OAEP login envelope remains usable. */
public class RsaKeyServiceTest {
    private static final OAEPParameterSpec OAEP_SHA256 = new OAEPParameterSpec(
            "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT);

    @Test
    public void decryptsRsaOaepSha256Envelope() throws Exception {
        Path directory = Files.createTempDirectory("mdmesh-rsa-test-");
        try {
            RsaKeyService service = new RsaKeyService(directory.toString());
            assertTrue(service.generateKeys());

            Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
            cipher.init(Cipher.ENCRYPT_MODE, service.getPublicKey(), OAEP_SHA256);
            byte[] encrypted = cipher.doFinal("0123456789ABCDEF".getBytes(StandardCharsets.UTF_8));

            assertEquals("0123456789ABCDEF", service.decryptOaepSha256(encrypted));
        } finally {
            Files.deleteIfExists(directory.resolve("private.key"));
            Files.deleteIfExists(directory.resolve("public.key"));
            Files.deleteIfExists(directory);
        }
    }
}

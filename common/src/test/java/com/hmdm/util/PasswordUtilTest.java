package com.hmdm.util;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class PasswordUtilTest {
    @Test
    public void pbkdf2HashesVerifyAndAreSalted() {
        String first = PasswordUtil.getHashFromRaw("correct horse battery staple");
        String second = PasswordUtil.getHashFromRaw("correct horse battery staple");

        assertTrue(PasswordUtil.isPbkdf2Hash(first));
        assertTrue(PasswordUtil.passwordMatchRaw("correct horse battery staple", first));
        assertFalse(PasswordUtil.passwordMatchRaw("wrong", first));
        assertFalse(first.equals(second));
    }

    @Test
    public void legacyDigestCompatibilityRemainsAvailableForTransition() {
        String digest = CryptoUtil.getMD5String("legacy-password");
        String stored = PasswordUtil.getHashFromMd5(digest);

        assertTrue(PasswordUtil.looksLikeMd5Digest(digest));
        assertTrue(PasswordUtil.passwordMatchLegacyDigest(digest, stored));
    }
}

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

package com.hmdm.util;

import com.hmdm.persistence.AgentCommandDAO;

/**
 * Shared {@code Authorization: Bearer <deviceSecret>} check for every {@code /public/agent/v1/...}
 * endpoint a device calls directly (not through an admin session) — extracted from
 * {@code AgentResource#authenticate} so a second device-authenticated endpoint (e.g. remote-session
 * snapshot upload) doesn't duplicate or drift from the checkin path's own check.
 */
public final class AgentAuth {

    private AgentAuth() {
    }

    /** Verifies the header against the SHA-256 hash stored at enrollment. Constant-time compare;
     *  fails closed when the header is missing or the device has no stored secret. */
    public static boolean authenticate(String authorization, String deviceNumber, AgentCommandDAO commandDAO) {
        String presented = bearer(authorization);
        if (presented == null) {
            return false;
        }
        String expectedHash = commandDAO.getDeviceSecretHash(deviceNumber);
        if (expectedHash == null) {
            return false;
        }
        return CryptoUtil.constantTimeEquals(CryptoUtil.getSHA256String(presented), expectedHash);
    }

    public static String bearer(String authorization) {
        if (authorization == null) {
            return null;
        }
        String s = authorization.trim();
        if (s.regionMatches(true, 0, "Bearer ", 0, 7)) {
            String token = s.substring(7).trim();
            return token.isEmpty() ? null : token;
        }
        return null;
    }
}

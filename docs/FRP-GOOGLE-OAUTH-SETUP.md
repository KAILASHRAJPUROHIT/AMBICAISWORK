# Tenant Google recovery accounts for Android EFRP

AMBIC MDM never asks for, receives, stores, or proxies a Google password, MFA approval, access token, refresh token, or ID token.

Each tenant administrator connects a recovery account through Google OAuth. The server calls Google People API `people/me`, validates `resourceName` as `people/<numeric-user-id>`, then stores only the tenant ID, numeric Google user ID, display email, MDM user, and connection time.

Android receives numeric IDs only. It applies EFRP, broadcasts `com.google.android.gms.auth.FRP_CONFIG_CHANGED` to Google Play services, reads the policy back, and reports failure on a mismatch. Generic `factoryResetProtection=true` is deliberately rejected.

## One-time server configuration

Create a Google Cloud **Web application** OAuth client, enable People API, configure the consent screen, and add this exact redirect URI:

```
https://<mdm-host>/rest/public/frp/oauth/callback
```

Set these only in the server runtime/service manager. Never Git:

```
AMBIC_GOOGLE_OAUTH_CLIENT_ID=<client-id>
AMBIC_GOOGLE_OAUTH_CLIENT_SECRET=<client-secret>
AMBIC_GOOGLE_OAUTH_REDIRECT_URI=https://<mdm-host>/rest/public/frp/oauth/callback
```

Restart the MDM server. If any setting is absent, connection is unavailable; it never falls back to an email string.

## Operator sequence

1. Connect recovery account in AMBIC MDM. Sign in on Google-owned page.
2. Confirm account appears in tenant list.
3. Apply EFRP to target Device Owner device.
4. Wait for `done` command result before any reset.
5. Before resale/repurpose, explicitly clear FRP and wait for `done`.

## Required acceptance test

Use a spare device: one account, multiple accounts, removal + reapply, normal OTA update, recovery wipe + correct recovery sign-in, then FRP clear + wipe. Never test a recovery wipe on production until successful policy read-back is in command history.

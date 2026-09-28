# AIS origin security deployment

No production setting is changed by this source tree.

## Cloudflare Access JWT validation

Set these production secrets only after the Cloudflare Access application is working for the recovery administrator:

```text
AIS_REQUIRE_CF_ACCESS=true
CF_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com
CF_ACCESS_AUD=<Access application audience value>
AIS_ALLOWED_EMAILS=info@aradhanajewellers.com
```

`CF_ACCESS_AUD` is the Access application audience, not its application ID. AIS validates the signed `Cf-Access-Jwt-Assertion` against Cloudflare's JWKS, issuer, audience and explicit email allowlist. It fails closed when enabled.

Keep the origin private/tunnel-only. Do not expose the origin directly to the public Internet.

## Device-bound passkeys

Use HTTPS only. Before enforcement, configure:

```text
AIS_WEBAUTHN_RP_ID=ais.aradhanajewellers.com
AIS_WEBAUTHN_ORIGIN=https://ais.aradhanajewellers.com
AIS_WEBAUTHN_ENABLED=false
```

1. Sign in with the existing password.
2. Enrol a Windows Hello/platform passkey on each of the two approved devices.
3. Verify both passkeys work.
4. Set `AIS_WEBAUTHN_ENABLED=true`.

AIS stores public credential keys, counters and labels only. It never stores face images, video, blink data or biometric templates. Windows Hello performs local biometric/PIN verification.

Do not enable Access JWT enforcement, passkey enforcement, device posture or mTLS simultaneously. Validate one layer and retain a tested recovery administrator path before the next.

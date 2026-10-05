# Third-party notices — AMBIC Digital MDM for Windows

## OpenUEM — Apache License 2.0

Source: https://github.com/open-uem (organisation). Each repository below was copied unmodified into `windows/upstream/<name>/`
on 2026-10-05, from the commit shown, with its `LICENSE` file. The Apache License 2.0 applies to all of them. Copyright remains with
the OpenUEM authors.

| Repository | Commit |
|---|---|
| openuem-console | 5604db7e4b4ac0fef5f95aad0ef279722966bd9d |
| openuem-worker | c852d70f9eb783330664f96ee7ca0c65fe951a02 |
| openuem-agent | ee23c21f11464b9c130445d017b413385b6d0d9c |
| openuem-cert-manager | 6b136eb42b64f058fc9f581e40b0da936ae169ac |
| openuem-nats-service | 4c6e8123b20c3f68bdcaeabae66ee829ab401a9d |
| openuem-ocsp-responder | 9e19683e5f304c53c351a156728295371f4f984e |
| ent | 6f7d005adb1d036046963ed7b0c6e20023b91937 |
| utils | 91c07c6c24cb5be0c63ebc0894357c8db91a50ea |
| nats | 98373a46adcff00efc936e26440048bfae5d8c6c |
| wingetcfg | 80e823d91ea5a3474ddce10374b591e1550e05dd |
| openuem-agent-updater | 3e25917a8508329f09f6b4868d84c544c5172199 |
| openuem-server-updater | c09e6450cc46463f99489b77479c558d71e26601 |
| openuem-messenger | 1d3f12d6cb6d817886061dcb615cda3806658361 |
| openuem-docker | 28ede14ab5e2add40c5c10fb5ff4415df6c4d2e4 |

Their third-party Go dependencies keep their own licences (see each module's `go.mod` / `go.sum`); a full dependency licence
report must be produced before the first release.

## Fleet — MIT (planned reuse, nothing copied yet)

Fleet Device Management Inc, https://github.com/fleetdm/fleet. Only files outside `ee/` are MIT-licensed
("MIT Expat", Copyright (c) 2020-present Fleet Device Management Inc and (c) 2017 Kolide). If any file is reused in Phase 2 the MIT
notice will be reproduced here. The `ee/` directory is under Fleet's commercial licence and must not be used.

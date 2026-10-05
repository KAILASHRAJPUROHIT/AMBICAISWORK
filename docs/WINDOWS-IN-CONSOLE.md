# Windows PCs in the AMBIC console

Windows PCs are managed by the Windows side (`windows/`, built on OpenUEM, Apache-2.0). The AMBIC console shows them
under **Devices → Windows PCs** and opens a detail page with actions.

```
browser → AMBIC server  /rest/private/windows/v1/*   (session + permission checks)
              │  Bearer MDM_WINDOWS_BRIDGE_TOKEN
              ▼
        ambic-windows-bridge  (windows/bridge, Go)
              ├─ reads OpenUEM's Postgres (read-only is enough)
              └─ sends commands through OpenUEM's own console with an administrator certificate
```

## Turn it on

AMBIC server environment:

| Variable | Meaning |
|---|---|
| `MDM_WINDOWS_BRIDGE_URL` | e.g. `http://127.0.0.1:8470` |
| `MDM_WINDOWS_BRIDGE_TOKEN` | shared secret, at least 16 characters |

Bridge environment: `BRIDGE_TOKEN` (same secret), `OPENUEM_DB_URL`, and for commands `OPENUEM_CONSOLE_URL`,
`OPENUEM_ADMIN_PFX`, `OPENUEM_ADMIN_PFX_PASSWORD`, `OPENUEM_CA_CERT`, optional `OPENUEM_TENANT` (default `1`),
`BRIDGE_LISTEN` (default `127.0.0.1:8470`).

Leave `MDM_WINDOWS_BRIDGE_URL` empty and the Windows section is hidden; nothing else changes.

## Rules

* Viewing needs a signed-in user; commands (`report`, `admit`, `restart-agent`) need the `edit_devices` permission.
* The bridge only acts on PCs in OpenUEM's database and only on its fixed action list.
* The bridge listens on loopback by default. Do not expose it; the AMBIC server is the only caller.
* The bridge presents only the administrator leaf certificate to OpenUEM (a full chain makes OpenUEM refuse the session).

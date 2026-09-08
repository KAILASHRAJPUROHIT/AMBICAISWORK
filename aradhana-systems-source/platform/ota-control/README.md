# AIS OTA Control

Laptop-hosted, LAN-only OTA service. Release payloads are RSA/SHA-256 signed on the laptop. Clients reject an unsigned manifest, target/channel mismatch, malformed ZIP, or SHA-256 mismatch before staging anything.

Channels: `beta` for PC2/Dell validation; `stable` only after physical proof. Each ZIP must contain an `apply.ps1`; it is executed only with explicit `-Apply`. Default behavior is verify and stage only.

Server: `http://192.168.0.12:8091`. It has no public binding. Private signing key stays under `C:\AradhanaSystems\ota-releases\keys` on this laptop; only `ota-public.cer` travels to clients.

Install the durable laptop service once from an elevated PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\AradhanaSystems\platform\ota-control\install_ais_ota_server.ps1
```

It creates `AISOTAServer`, writes runtime logs under
`C:\ProgramData\AradhanaSystems\logs\ais-ota`, and adds one inbound Private
profile firewall rule restricted to `192.168.0.12` and `192.168.0.0/24`.

Example publisher:

```powershell
python publish_release.py --initialize-keys --channel beta --target print-router-pc2 --version 2026.9.6.1 --bundle C:\release\router.zip --notes "Validated third-copy routing"
```

Example client staging check:

```powershell
powershell -ExecutionPolicy Bypass -File .\AISUpdateAgent.ps1 -ServerUrl http://192.168.0.12:8091 -Channel beta -Target print-router-pc2
```

## Bundle construction

Never ZIP a project tree wholesale. Build an allow-listed payload first:

```powershell
powershell -ExecutionPolicy Bypass -File .\New-AISReleaseBundle.ps1 `
  -Target document-workflow-pc2 -Version 1.0.0-beta.1 `
  -SourceRoot C:\AradhanaSystems\platform\plugins\document-print-workflow `
  -Include service\app.py,bridge\biller_popup.py,bridge\qr_bundle_sync.py `
  -ApplyScript C:\verified-release\apply.ps1
```

The generated payload contains `ais-release.json` with the exact included
files and hashes. The signed OTA envelope then authenticates the ZIP itself.
The apply script remains target-specific and must contain a health check plus
a documented rollback action. No client applies an update merely because it is
available: `AISUpdateAgent.ps1` stages by default and requires explicit
`-Apply`.

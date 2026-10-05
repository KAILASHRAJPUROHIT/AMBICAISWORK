# Local evaluation stack (Windows)

A throw-away copy of the OpenUEM server on one machine, to see the console and test an agent. It uses OpenUEM's own published images
(not yet our build) and lives outside the repository in `C:\AradhanaSystems\tools\openuem-eval\`. Its `.env` holds generated secrets and
must never be committed.

## What was done on ARADHANA (2026-10-05)

1. Docker Desktop engine started. Compose files copied from `upstream/openuem-docker` (`compose.yml`, `compose.base.yml`) and a `.env`
   written with:
   - domain `192-168-0-8.nip.io` (public DNS maps `console.`, `nats.`, `ocsp.` of that name to 192.168.0.8, so no hosts-file or admin change);
   - generated database password and console JWT key;
   - OCSP on port **18000** because port 8000 on this laptop belongs to another service;
   - NATS 4433, console 1323 (login) and 1324.
2. `docker compose up openuem-certs -d` generated the certificate authority and every certificate (including `users/admin.pfx`, the
   administrator's browser certificate), then `docker compose up -d` started database, OCSP responder, NATS, workers and console.
3. Our own build of the Windows agent (`build.ps1`) was run from `agent-test\` (no Windows service, using the foreground mode in
   `MODIFICATIONS.md`) with an `openuem.ini` and the agent, CA and console-SFTP public certificates. It connected, registered as
   `ARADHANA` (status `WaitingForAdmission`) and uploaded hardware, OS (Windows 11 25H2 Pro) and 335 installed apps.

## Agent configuration that was needed (`config\openuem.ini`, next to the exe)

`[Agent]`: `UUID`, `Enabled`, `ExecuteTaskEveryXMinutes`, `Debug`, `DefaultFrequency`, `SFTPPort`, `VNCProxyPort`, `SFTPDisabled`,
`RemoteAssistanceDisabled`. `[NATS]`: `NATSServers=nats.<domain>:4433`. `[Certificates]`: `AgentCert`, `AgentKey`, `CACert`, `SFTPCert`
(the console's `sftp.cer`, public part only). The agent also needs an empty `logs\` folder.

## Run / stop

```
cd C:\AradhanaSystems\tools\openuem-eval
docker compose start      # or: docker compose up -d
docker compose stop       # keeps the data
docker compose down -v    # removes everything, including the database
```

The console is at `https://console.192-168-0-8.nip.io:1323` and signs in with a client certificate (import `certificates\users\admin.pfx`
into the browser). A new agent must be admitted by an administrator in the console before it counts as managed.

## Not verified yet

Signing in to the console in a browser, admitting the agent, running a command (software install, restart, script) from the console, and
the update service. The built-in test browser could not open the self-signed address.

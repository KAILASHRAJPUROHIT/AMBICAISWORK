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
   - NATS 4433, console 1323 (login) and 1324 (certificate sign-in).
2. `docker compose up openuem-certs -d` generated the certificate authority and every certificate (including `users/admin.pfx`, the
   administrator's browser certificate), then `docker compose up -d` started database, OCSP responder, NATS, workers and console.
3. Our own build of the Windows agent (`build.ps1`) was run from `agent-test\` (no Windows service, using the foreground mode listed in
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

## Console sign-in, admission and a command (verified 2026-10-05)

- **Sign-in.** The console uses client-certificate login. The administrator certificate `certificates\users\admin.pfx` (password `changeit`,
  the go-pkcs12 default) was imported into the Windows **CurrentUser\My** store only (no admin rights needed). A request to `/auth` on port 1323
  redirects to port 1324, which accepts the certificate and issues a `session` cookie, then redirects to `/tenant/1/site/1/dashboard`. The
  dashboard and agent list pages were served, and `ARADHANA` showed as `WaitingForAdmission`.
- **Admission.** `POST /tenant/1/agents/<uuid>/admit` (with the `_csrf` cookie value sent in an `X-CSRF-Token` header) set the agent to `Enabled`,
  and the cert-manager worker issued the agent its own certificate over NATS (the agent saved `server.cer` and `server.key`).
- **Command.** `POST /tenant/1/agents/<uuid>/forcereport` was published through JetStream (`agent.report.<uuid>`). The agent ran a fresh inventory
  report (about 60 seconds, because some WMI disk queries are slow), sent it, and the server updated `last_contact` (10:12:59 to 10:23:03 UTC).
- Run as a normal user, the agent cannot read BitLocker status (WMI access denied) and some WMI disk queries time out. As the real Windows service
  (LocalSystem) these are expected to work, but that is not yet tested.

To remove the browser certificate again:

```
Get-ChildItem Cert:\CurrentUser\My | Where-Object Subject -like "CN=admin, O=AMBIC Digital*" | Remove-Item
```

## Not verified yet

Clicking through the console in a real browser (the built-in test browser refused the self-signed address), software install / script /
restart commands, running the agent as a real Windows service, the update service, and our own build of the server (this stack runs
OpenUEM's published images).

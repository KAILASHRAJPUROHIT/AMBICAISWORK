# AMBIC Digital MDM for Windows

Windows 11 management for AMBIC Digital MDM, built on the Apache 2.0 licensed [OpenUEM](https://github.com/open-uem) project and
kept in this repository so it is versioned, released and sold with the rest of AMBIC MDM.

## Status

Phase 1 is under way. The upstream source is imported unchanged under `upstream/` and **all six Windows components compile** with `build.ps1`
(agent, agent updater, agent worker, certificate manager, OCSP responder, console). Nothing is branded, installed on a PC, or released yet,
and the console has not been run (it needs PostgreSQL, a NATS server and certificates).

| Phase | What | State |
|---|---|---|
| 1 | AMBIC Windows agent + console integration (inventory, software install, scripts, restart/lock, update and antivirus status, remote assistance) | source imported, **builds**; local stack + branding next |
| 2 | Windows MDM enrolment (policy, BitLocker, kiosk, update rings) using AMBIC's own endpoint; the MIT-licensed SyncML / enrolment code from Fleet may be reused with attribution | not started |
| 3 | Windows Server: the Phase 1 agent plus Group Policy (servers do not use the MDM protocol) | not started |

Targets: Windows 11 Pro/Enterprise (full), Windows 11 Home (agent features and monitoring; many MDM policies do not apply to Home).
No device ever needs a reset: the agent installs onto a running PC, and Phase 2 enrols an existing PC from
Settings > Accounts > Access work or school.

## Build

```
pwsh -File windowsuild.ps1
```

Uses a portable Go in `C:AradhanaSystems	oolsgo` (downloaded and checksum-verified if missing; nothing is installed into Windows), generates
the console templates, and writes the executables to `windowsdist` (git-ignored). Needs Go 1.26.2 or newer.

## Layout

- `upstream/<repo>` — OpenUEM repositories exactly as imported (see `UPSTREAM.txt` for the commit of each). Their own `LICENSE`
  files are kept. **Do not edit these in place without recording it in `MODIFICATIONS.md`** (Apache 2.0 section 4 requires modified
  files to carry notices of the change).
- `THIRD-PARTY-NOTICES.md` — what was taken from where, and under which licence.
- `UPSTREAM.txt` — upstream repository, commit and licence.

## Licence rules for this folder

- OpenUEM: Apache 2.0. Keep every `LICENSE`/`NOTICE`, and note each modification.
- Fleet (`fleetdm/fleet`): the root is MIT, but everything under its `ee/` directory is a commercial licence. Only MIT paths
  (for example `server/mdm/microsoft/`) may ever be copied here, and only with the MIT notice. Never copy from `ee/`.
- AMBIC's own additions are Apache 2.0, like the rest of this repository.

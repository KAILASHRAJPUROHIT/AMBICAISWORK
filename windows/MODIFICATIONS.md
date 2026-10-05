# Modifications to upstream (Apache License 2.0, section 4(b))

Every change AMBIC makes to a file under `upstream/` is listed here, with the date, so modified files carry a notice of the change.
Original authors keep their copyright; AMBIC's changes are licensed under Apache 2.0 like the rest of this repository.

| Date | File | Change |
|---|---|---|
| 2026-10-05 | `upstream/openuem-agent/internal/service/windows/main.go` | When the agent is started from a console (not by the Windows Service Control Manager) it runs the same service code in the foreground with `svc/debug.Run`, so it can be developed and tested without installing a Windows service. Behaviour as a real service is unchanged. |

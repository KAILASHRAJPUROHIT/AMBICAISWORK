# AIS Print Combo release

Creates one source-only release package for the coordinated QR Print Server,
QR local agent, AIS document workflow, and Ornate router source.

Run from an elevated development PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\AradhanaSystems\projects\qr-print-server\deployment\New-AISPrintComboPackage.ps1" -OutputDirectory "C:\AradhanaSystems\releases"
```

The package intentionally excludes databases, uploaded documents, logs,
`.env` files, bridge tokens, agent tokens, and executable binaries.

Coordinated rollout order:

1. Set the same new `AGENT_TOKEN` in Render and the PC2 print-agent runtime.
2. Set Render `QR_REQUIRED_PRINTER=HPF8EDFC0532A7(HP Laser MFP 330)`.
3. Deploy the cloud server and agent together. Confirm unauthenticated agent
   polling returns `401`; authenticated polling returns `200`.
4. Set PC2 router `Overlay355TargetPrinterOverride` to the same exact queue.
5. Use the approved signed-router staging share for any router EXE update.
6. Run the no-print and controlled physical acceptance checks before normal use.

Never put a token in source, a package, `config.txt`, command history, or logs.

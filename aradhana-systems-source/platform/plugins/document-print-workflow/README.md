# AIS Document Print Workflow

First AIS plugin. Owns delayed document association for Ornate bill printing.

## Locations

```
C:\AradhanaSystems\platform\plugins\document-print-workflow\
  service\             shared LAN API and SQLite state
  renderer\            P355 PDF composition, no printer access
  bridge\              native biller popup; writes a one-time decision file
  contracts\           versioned JSON contracts
  tests\               isolated tests
```

Live deployment locations remain separate until acceptance testing:

```
C:\AradhanaSystems\projects\qr-print-server\       scanner UI and upload producer
C:\AradhanaSystems\projects\print-router\          trusted Ornate/P355 consumer
C:\PrintBridge\                                      live PC2 spool paths; do not edit in development
```

## Safety model

The service never prints. The router never chooses a bundle automatically.
Only a document created in the last 30 minutes can be shown or attached. The
router displays no Alt+P document panel if no eligible bundle exists. It sees
at most the newest three eligible bundles.

`attach` requires a biller-selected bundle. `Print documents` queues only that
bundle to the existing QR/P355 route. `Dismiss` writes no print command and
leaves Ornate's normal bill path untouched. The legacy `wait` API is retained
only so a previously staged Router build cannot fail mid-upgrade; it is not in
the current UI.
The renderer returns a PDF only; the existing trusted P355 route remains responsible for physical printing and final success/failure acknowledgement.

## Router bridge contract

When Ornate opens its real Print dialog, the Router launches `bridge\\biller_popup.py` and waits for a JSON decision file. The popup does not synthesize keys, select printers, or print. A router adapter may consume only one decision file for one detected print session, then delete it after acknowledging the selected route.

## Windows runtime split

* `scripts\\install_document_workflow_service.ps1`: installs `AISDocumentWorkflowApi` as a SYSTEM startup task. It owns API/database availability only.
* `scripts\\install_document_alerts_startup.ps1`: installs `AISDocumentAlerts` as a signed-in-user logon task. It owns top-right notifications only.
* The Router tray app owns the interactive biller popup. This is required because a SYSTEM task cannot safely display UI in the biller's Windows session.
* `scripts\\Set-AISDocumentBridgeToken.ps1`: saves the bridge token as a DPAPI blob for the current Windows user. It does not write the token to router config, task arguments or logs.
* `scripts\\Test-DocumentWorkflowDeployment.ps1`: package/runtime preflight. Use `-RequireApi` only after the local API is running.

## Signed deployment

The full allow-list is in `deployment\\apply.ps1`. It backs up only replaced
plugin files under `C:\ProgramData\AradhanaSystems\backups\document-workflow\...`,
preserves the DPAPI credential, installs/verifies the local API, and registers
the user-session alert task. It requires elevation because it registers the API
task; this is intentional. OTA clients stage by default and apply only after a
reviewed, elevated deployment window.

# Changelog

All notable changes to the Print Server project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.5] - 2026-09-22

### Fixed
- **Sequential Dialog Routing & Window Latch Fix**: Fixed bug in v1.1.4 where `_knownVoucherWindows` locked out voucher evaluation on the first 200ms tick before copy count could be read from the UI, causing all 3 copies to default to 355.
- **Strict Universal Dialog Sequence Invariant**: Dialog 1 of an Ornate bill sequence routes to P1007 (Copy 1 - Office Copy), Dialog 2 routes to 355 (Copy 2 - Customer Copy), and any rapid Dialog 3+ (URD Purchase Voucher or extra copies) is STRICTLY diverted to 355, 100% blocking P1007. Standalone 1-copy vouchers also strictly route to 355.
- **Interactive Rules Checkbox Grid**: Fixed `_gridRules` being globally `ReadOnly = true`. Enabled checkboxes now toggle immediately with a single click via `CurrentCellDirtyStateChanged` and `CellValueChanged` event handlers.
- **Active Console Buttons & Direct Win32 Test Fallback**:
  - `Save Station Settings` and `Save All Rules` now apply changes immediately to memory, disk (`rules.json`), update `CaptureSpoolWatcher`, and signal `PrintNode` on port 8447.
  - `Simulate Ornate Voucher` and `Simulate Tablet Estimate` now log to both service and local ledger with explicit user confirmations.
  - `Spool Diagnostic Test Ticket` features automatic Win32 direct spool fallback if the background service is stopped, ensuring physical test prints always execute.

---

## [1.1.4] - 2026-09-22

### Fixed
- **Strict Universal P1007 2-Copy Invariant**: Enforced universal constraint that `P1007` (pre-printed letterhead) is ONLY permitted for Copy 1 of an Ornate voucher when exactly 2 copies are requested.
- **URD Purchase Voucher Auto-Protection**: Fixed URD purchase vouchers (which appear immediately after the 2 sales bill copies, or standalone with 1 copy) being misrouted to P1007. Any 3rd copy, extra copy, or 1-copy voucher now strictly routes to `355 Letterhead Capture` (P355), preserving expensive physical letterhead stock.
- **Removed Sequence Fallback Timer**: Replaced the 15-second sequence timer fallback in `PrintDialogInterceptor` with strict routing to 355 whenever no 2-copy session is active, eliminating false P1007 routing on subsequent dialogs.

---

## [1.1.3] - 2026-09-22

### Fixed
- **Automated '355 Letterhead Capture' Virtual Printer Setup**: The installer now automatically discovers, configures, or creates the `355 Letterhead Capture` virtual printer in Windows. If Bullzip is installed, it renames `Bullzip PDF Printer` to `355 Letterhead Capture` and configures `global.ini` for silent PDF output to `C:\PrintBridge\incoming_355\`. If Bullzip is absent, it automatically provisions the native Windows `Microsoft PS Class Driver` on Standard TCP/IP Port `127.0.0.1:9100`.
- **Bundled Letterhead Assets in Installer Payload**: `Package-PrintServer.ps1` now bundles `letterhead_front.jpeg`, `letterhead_back.jpeg`, and `overlay_merge.py` into the self-extracting payload. The installer automatically deploys them to both `C:\ProgramData\AMBIC DIGITAL\Print Server\assets\` and `C:\PrintBridge\` on every target workstation.
- **Protected Active Spool Directory from Migration Deletion**: Excluded `C:\PrintBridge` from legacy directory purges during migration, preventing accidental deletion of active spool folders and letterhead image templates.

---

## [1.1.2] - 2026-09-22

### Fixed
- **Automated Legacy Software Decommissioning**: Installer now scans Windows `Uninstall` registry keys across 32-bit and 64-bit hives to silently execute `msiexec.exe /x` against legacy print routers (e.g. `Aradhana Ornate AutoPrint Router`) and completely purges residual registry entries.
- **Perpetual Background Tray Message Loop**: Implemented custom `PrintServerAppContext` so `Ambic.PrintConsole` stays running indefinitely in the system notification tray even when the main dashboard is closed with the 'X' button or launched with `--tray`.
- **System-Wide Windows 11 Classic Print Dialog Enforcement**: Extended `Windows11PrintDialogEnforcer` to apply `DisablePrintSupportApp = 1` across all active user hives in `HKEY_USERS` and automatically terminate cached `PrintDialog.exe` processes to force immediate adoption of classic `#32770` dialogs.

---

## [1.1.1] - 2026-09-22

### Fixed
- **Ghostscript File Lock Sharing Violation**: Fixed `Last OS error: Permission denied` when converting spooled PostScript from `P1007 (via PC2)` by scoping and closing the `FileStream` before spawning Ghostscript.
- **Ornate Print Sequence Auto-Splitting**: Added intelligent sequential detection for ONX print dialogs. When two dialogs appear in succession, Dialog 1 is routed to Copy 1 (`P1007 (via PC2)`) and Dialog 2 is routed to Copy 2 (`355 Letterhead Capture`), eliminating the issue where all dialogs defaulted to Copy 2 when voucher preview titles differed.
- **Persistent Tray Application Context**: Switched `Ambic.PrintConsole` to run inside an `ApplicationContext` in tray mode, preventing premature message loop exit when running hidden in the background.

---

## [1.1.0] - 2026-09-22

### Added
- **Capture Folder Watcher (`CaptureSpoolWatcher`)**: Native background spool observer monitoring Bullzip output folders (`C:\PrintBridgeTest\incoming`, `C:\PrintBridge\incoming_355`).
- **Physical Printer Auto-Dispatch**: Automatically processes incoming bill PDFs, applies duplex front/back letterhead overlay via PyMuPDF, and dispatches to physical printer (`HPF8EDFC0532A7` / `HP Laser MFP 330`) via silent SumatraPDF integration.
- **PC2 Hub Relay Automation**: Automatically forwards Copy 1 office vouchers to `\\PC2\PrintBridge\incoming` for physical printing on PC2's USB-connected HP LaserJet P1007.
- **Embedded RAW TCP Port 9101 Listener (`RawTcpPrintRelay`)**: Embedded TCP 9101 listener capturing RAW PostScript from Windows printer `P1007 (via PC2)`, converting via Ghostscript, and delivering directly to the relay queue.
- **Win32 Classic Print Dialog Interceptor (`PrintDialogInterceptor`)**: Full Win32 `#32770` automation supporting UI Automation (`SelectionItemPattern`), WOW64 32-bit/64-bit `SysListView32` memory structs, and standard `ComboBox` controls with auto-click (`BM_CLICK`).
- **Standardized Versioning**: Added solution-wide `Directory.Build.props` setting Version `1.1.0`.

### Changed
- Rebranded entire suite to **Print Server** under **AMBIC DIGITAL**; purged legacy vendor names.
- Corrected Windows 11 legacy print dialog registry enforcement key to `HKCU\Software\Microsoft\Print\UnifiedPrintDialog\PreferLegacyPrintDialog = 1`.
- Upgraded installer UI with multi-resolution `.ico` icon support and system tray minimization.

### Fixed
- Fixed Windows 11 modern XAML dialog popup blocking Ornate automation.
- Fixed printer auto-selection failing on `#32770` dialogs.
- Fixed physical print gap caused by decommissioning legacy standalone Python scripts.

---

## [1.0.0] - 2026-09-21
- Initial unified Print Server release replacing fragmented relay scripts.

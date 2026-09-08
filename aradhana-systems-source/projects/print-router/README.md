# Aradhana Ornate Print Routing

**⚠️ This is LIVE PRODUCTION infrastructure, currently running on real bills.**
Read this whole file before changing anything here.

## What this is

Ornate ERP (`D:\Ornnx\ONX.exe` on PC2/Dell server, `C:\Ornnx\ONX.exe` on the
laptop) fires two separate Windows Print dialogs per bill — one per copy —
and someone had to manually pick the right printer for each, every bill.
This automates that.

- **Copy 1 (office copy)** → **P1007** — real pre-printed letterhead stock
  already loaded, printed as-is, single-sided. P1007 **cannot physically
  duplex**.
- **Copy 2 (customer copy)** → **355sdnw** — blank paper. The bill is
  captured to a local PDF, a digital letterhead is composited on
  (`overlay/overlay_merge.py`, PyMuPDF), and the result is duplex-printed:
  page 1 = bill + front letterhead, page 2 = terms & conditions image.

Full narrative + diagram: `docs/print-routing-handover.html`.

## Where this actually runs (as of 2026-09-04)

| Machine | Role | Status |
|---|---|---|
| **PC2** | Hub — P1007 physically attached | Live, tested on real bills |
| **Dell server** | Relay — no P1007 access, relays copy 1 to PC2, does the 355 overlay locally | Live, tested on real bills |
| Laptop | Same pattern as Dell server when resumed | **Not deployed** — on hold |

Both live machines run the **same compiled binary**,
`AradhanaOrnateAutoPrint.exe` — behavior differs entirely via
`C:\ProgramData\Aradhana\OrnateAutoPrintTray\config.txt` per machine (see
the handover doc, section 03, for the exact field values).

## Repo layout

```
src/                          C# source
  AradhanaOrnateAutoPrint.cs  the tray app — window-watching, printer
                               selection, and (merged in) the 355 overlay
                               pipeline trigger
  Aradhana355Watcher.cs       a separate, smaller watcher — same overlay
                               pipeline, no Ornate-window-watching. Found
                               alongside the main app; purpose/deployment
                               status vs. the main app not yet confirmed —
                               ask before assuming it's unused.
overlay/
  overlay_merge.py            the PDF compositing script (PyMuPDF) — the
                               piece most likely to be extended next
  live-images/                letterhead_front.jpeg / letterhead_back.jpeg —
                               EXACTLY what's referenced by the hardcoded
                               paths in AradhanaOrnateAutoPrint.cs
                               (C:\PrintBridge\letterhead_front.jpeg etc.)
                               and verified byte-identical (SHA256) against
                               the live deploy share on 2026-09-04.
  unwired-optimized-images/   letterhead_front_opt.jpg / _back_opt.jpg —
                               smaller (132KB/280KB vs 947KB/1.6MB). ⚠️ SEE
                               "Known discrepancy" BELOW — these do NOT
                               appear to be wired into the live code despite
                               a memory note claiming the live images are
                               already the optimized ones.
known-good-binaries/          Compiled .exe snapshots, hash-verified
                               against the live \\PC2\PrintBridge\deploy
                               share on 2026-09-04. A rollback artifact —
                               if a future deploy goes wrong, this is a
                               known-working binary, not something you'd
                               have to trust a fresh recompile to reproduce.
build-and-install/            Build_*.bat, Install_*.bat, Uninstall_*.bat,
                               the internal signing cert
docs/
  print-routing-handover.html  the full narrative writeup — architecture,
                                 config table, and 6 hard-won debugging
                                 lessons (NPAV false positives, PyMuPDF vs
                                 pypdf, etc.) — READ THIS FIRST for context
  TRAY_APP_README.txt          older install/purpose doc shipped with the
                                 app itself (slightly out of date — written
                                 before the ListView printer-selection and
                                 355-overlay-merge capabilities existed;
                                 kept for historical install instructions)
```

## ⚠️ Known discrepancy — needs a human decision, not fixed here

`AradhanaOrnateAutoPrint.cs` hardcodes reading
`C:\PrintBridge\letterhead_front.jpeg` / `letterhead_back.jpeg` at runtime
(see the `Overlay355FrontImage` / `Overlay355BackImage` constants). Those
are the **947KB / 1.6MB** files in `overlay/live-images/`.

A memory note from the same build session describes those exact filenames
as "optimized, ~130–280KB — full-res originals are too slow to print." But
the actual **~130–280KB files are the separate `_opt.jpg` versions**
(`overlay/unwired-optimized-images/`), which the code never references.

**This has not been changed as part of this commit.** Two possibilities:
the optimization was planned but never wired in, or the note is simply
wrong about which files are which. Confirm with whoever ran the original
optimization before swapping the code to point at the `_opt.jpg` files —
don't do it silently, since it changes what's already live on real bills.

## How to safely change anything here

1. **Never edit files directly on PC2 or the Dell server.** Edit in this
   repo, rebuild via `build-and-install\Build_Aradhana_Ornate_AutoPrint.bat`,
   test the new binary somewhere that isn't live billing.
2. **Deploy only via `\\PC2\PrintBridge\deploy` + `robocopy`.** Never
   `Copy-Item` a freshly-built `.exe` directly onto either live machine —
   NPAV silently deletes any `.exe` written by PowerShell itself,
   regardless of exclusions. See `docs/print-routing-handover.html` §06 and
   the `aradhana-print-routing-lessons` memory for the full list of
   AV/deployment gotchas (all cost real time to find once already).
3. **Prefer extending the existing trusted binary over shipping a new
   `.exe`.** A separate standalone watcher got flagged by a different,
   content-based NPAV heuristic even when correctly deployed — folding
   watcher logic into the already-trusted tray app was the fix that
   actually worked.
4. **Keep `known-good-binaries/` updated with whatever is genuinely live**,
   so there's always a real rollback artifact, not just source you'd have
   to hope recompiles identically.

## Source of truth verification (2026-09-04)

Everything in `src/`, `overlay/overlay_merge.py`,
`overlay/live-images/*.jpeg`, and `known-good-binaries/*.exe` was hash
(SHA256) verified byte-identical against the live `\\PC2\PrintBridge\deploy`
staging share before being committed here. This repo did not exist before
this commit — the only prior copy was a Claude session scratchpad
(ephemeral, not guaranteed to persist).

# Jewellery Catalogue Tool — Claude E2E Handover

Date: 2026-08-15 (Asia/Calcutta)

This document is the authoritative handover for the Aradhana Jewellery Catalogue Tool after the Claude-to-Codex continuation. Read it completely before changing prompts, lifecycle routing, review behavior, cost guards, or Ornate NX publishing.

## 1. Current production state

- Workspace: `C:\Users\kaila\Desktop\JewelleryCatalogTool`
- Main UI: `http://127.0.0.1:7654`
- Capture service: port `7660`
- Main Windows service: `AradhanaCatalogueTool`
- Capture Windows service: `AradhanaCaptureServer`
- Approved-image uploader task: `AradhanaOrnItemUpload`
- Stock workbook used during this handover: `Stock\12082026.xls`
- Stock labels: 2,749
- Catalogue taxonomy: 57 categories
- Categories represented by current Stock Excel: 56
- Captured lifecycle total: 863
- Processed raw masters: 196
- Review-state verdicts: 194 approved, 51 pending, 23 rejected
- Dashboard filesystem totals: 3 needs-review files, 101 rejected files
- Successfully published Ornate NX label images: 192
- Ornate upload queue: 0
- Server2k22 category-image root: `\\Server2k22\D\Ornnx\Orn Images\Orn Item Image`

The review-state rejected count and dashboard rejected-folder count use different sources and therefore differ. Review state counts labelled verdict records. Dashboard rejected total counts rejected delivery files, including variants/history.

## 2. Non-negotiable user requirements

1. BALI 18 and BALI 22 catalogue outputs must use a clear front three-quarter view at approximately 45 degrees.
2. Image 1 is always the product-design authority. Secondary guides control angle and spacing only.
3. Do not burn paid FLUX credits while diagnosing code, locks, prompts, routing, or folder behavior.
4. Follow BFL FLUX.2 prompt/reference constraints. The guarded wrapper makes one paid call and never automatically retries.
5. Approved raw masters move from `capture_intake` to `processed`.
6. Rejected and pending raw masters remain in `capture_intake`.
7. Rejected generated deliveries must never remain in `output`; all delivery variants move to `rejected`.
8. Approved generated deliveries remain in `output` and are copied to Ornate NX.
9. Ornate NX requires exact label-based filenames with `.Jpg`, not PNG.
10. Category Coverage must update every second and show Captured, Processed, Approved, Rejected, Uploaded and three progress bars.

## 3. End-to-end lifecycle

### 3.1 Capture

Raw masters enter:

`capture_intake\<EXACT CATEGORY LABEL>\<SAFE LABEL>.jpg`

Example Stock Excel label and Windows-safe label:

- Excel: `BL18/10`
- Capture/output filename stem: `BL18_10`

The safe transform is implemented by `stock_excel.safe_filename_label`: `/` becomes `_` because Windows filenames cannot contain `/`.

### 3.2 Generation

The production generation path is Azure FLUX.2-pro through:

- `tools\run_azure_flux2_guarded.ps1`
- `tools\azure_flux2_guarded.py`

Guard configuration:

- `config\azure_flux2_guard.json`
- Daily hard cap: `$100`
- Maximum calls per day: `300`
- Lifetime hard cap: `$100`
- No automatic retry after a failed paid call
- Active call lock: `reports\azure_flux2_guard\ACTIVE_CALL.lock`

If a run reports an active-call lock, first confirm no request is active. Never delete an active lock blindly. If the prior process crashed and no network call/process is active, clear the stale lock through the guarded recovery path.

The output remains:

`output\<OUTPUT CATEGORY FOLDER>\<SAFE LABEL>.jpg`

### 3.3 Review routing

Core implementation: `review_queue.py`.

On approval:

- Raw master: `capture_intake` → `processed`
- Generated delivery: stays/moves to `output`
- Approved hash is updated
- Ornate NX publish is attempted
- If the service cannot access the network share, the job is queued locally and the user-context task is triggered

On rejection:

- Raw master stays/moves to `capture_intake`
- Every generated variant for the label moves from `output` to `rejected`
- Reject reason manifest is updated

On pending:

- Raw master stays/moves to `capture_intake`

Startup calls `review_queue.reconcile_source_routes()`. It repairs crash-era or old-version routing while preserving byte-different conflicts for manual resolution.

Never replace this with filename-only deletion. `_relocate_between` and dedup logic preserve conflicting files and remove only byte-identical duplicates.

## 4. Rejected-image repair protocol

Standard protocol requested by the owner:

1. Let the Catalogue Tool reprocess the item first.
2. Wait for the tool review result.
3. Only Codex-repair items that remain rejected.
4. Create the replacement with Codex image generation outside the Catalogue Tool.
5. Import with `codex_repair.py`; do not manually drop a file into output and edit state.
6. The importer validates/converts the delivery, archives the failed version, approves the replacement, routes the raw master, and writes an audit row.

Command:

```powershell
python .\codex_repair.py LABEL C:\absolute\candidate.jpg --note "Exact repair description"
```

Audit log:

`data\codex_repair_imports.jsonl`

## 5. Bali 45-degree implementation

Key files:

- `category_geometry_hints.py`
- `catalogue_reference_guides.py`
- `assets\geometry_guides\bali\compact_huggie_45.jpg`
- `assets\geometry_guides\bali\round_hoop_45.jpg`
- `assets\geometry_guides\bali\BL22_43_front45.jpg`
- `config\flux2_pro_catalogue_prompt.txt`

Every reviewed Bali label is routed to a compatible geometry family:

- `compact_huggie`
- `round_hoop`

`BL22_43` has an exact-item guide. `BL18_10` and `BL22_43` also have item-specific measured prompt contracts.

Important behavior:

- For Bali, Image 1 controls design, silhouette family, proportions, stone count, engraving, dangles, material and component counts.
- Image 2 controls only the reviewed 45-degree camera orientation and pair spacing.
- A Bali SKU without a reviewed profile is blocked before spend with `BLOCKED_BEFORE_SPEND`.
- The secondary guide is prepared at 1 MP.
- Primary reference budget is reduced so references plus output remain inside the BFL 9 billed-MP multi-reference budget.
- The prompt demands visible front and receding side/rear depth, not merely sideways placement.
- Angular/squared items must retain flat planes and crisp corners. Round hoops must retain rounded tubing.

Do not reintroduce generic rounded-hoop language into the `BL18_10` item contract. That previously caused its squared rectangular diamond face to become a smooth rounded tube.

## 6. Random-colour prevention

The tool had false colour prompts caused by shop reflections, clothing, hands, tags, and background objects. The fix is in `reference_color_report.py` and tests.

Current safeguards:

- Product-region localisation
- Gold-proximity gating
- Sharpness gating
- Saturation/value thresholds
- Small-noise rejection
- Jewellery-region-only colour description

The base prompt also explicitly preserves bare gold and allows colour only where Image 1 contains a gemstone or enamel at that exact location.

Do not weaken these checks to a whole-frame dominant-colour scan. That recreates random blue/red/green artifacts.

## 7. Ornate NX publishing

Core implementation: `orn_item_image_sync.py`.

Destination root:

`\\Server2k22\D\Ornnx\Orn Images\Orn Item Image`

Exact naming rule confirmed from the Ornate NX Image Mapping UI:

- Excel label: `BL/100`
- Image 1: `BL_100.Jpg`
- Image 2, if ever supported: `BL_100_2.Jpg`
- Image 3, if ever supported: `BL_100_3.Jpg`

Current publisher creates only Image 1:

`<EXACT STOCK CATEGORY FOLDER>\<SAFE STOCK LABEL>.Jpg`

File requirements:

- RGB JPEG
- `.Jpg` exact casing
- JPEG quality 95
- 4:4:4/no chroma subsampling
- Atomic temporary write, verification, then replace

Ornate NX automatically creates `<LABEL>_Thumb.jpg` after recognising a main image. During verification it created 192 thumbnails from 192 main `.Jpg` files.

All 56 Stock-Excel-represented category folders were created. There are 57 application taxonomy categories, but one has no labels in the current workbook.

### 7.1 Why uploads use a scheduled task

`AradhanaCatalogueTool` runs as `LocalSystem`. LocalSystem cannot authenticate to the Server2k22 share.

Therefore:

1. Approval first attempts direct publish.
2. Network failure records a local queue entry.
3. `AradhanaOrnItemUpload` is triggered.
4. That task runs as user `kaila`, logon type `Interactive`, run level `Limited`.
5. It drains the queue using the user's valid network identity.
6. It also repeats every minute and starts at user logon.

Task command:

```text
C:\Users\kaila\AppData\Local\Programs\Python\Python311\pythonw.exe "C:\Users\kaila\Desktop\JewelleryCatalogTool\orn_item_image_sync.py" --drain-queue
```

Recreate or repair the task with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install_orn_item_upload_task.ps1
```

Local operational files:

- `data\orn_item_upload_queue.json`
- `data\orn_item_upload_status.json`
- `data\orn_item_uploads.json`

Useful checks:

```powershell
Get-ScheduledTask -TaskName AradhanaOrnItemUpload
Get-ScheduledTaskInfo -TaskName AradhanaOrnItemUpload
Get-Content .\data\orn_item_upload_queue.json
Get-Content .\data\orn_item_upload_status.json
```

Two approved labels are intentionally absent from Ornate NX because they are not in the current Stock Excel:

- `ER22_74`
- `GR22_135`

Do not bypass this stock-membership protection. Confirm the workbook first.

## 8. Dashboard and category coverage

Files:

- `category_dashboard.py`
- `app.py`
- `templates\dashboard.html`

Endpoint:

`GET /api/pipeline/category_breakdown`

Each of 57 rows contains:

- Stock
- Captured
- Processed
- Approved
- Rejected
- Uploaded
- Captured progress bar
- Processed progress bar
- Uploaded progress bar

Polling interval: one second.

Captured means lifecycle coverage: current `capture_intake` count plus `processed` count. Approved raws leave capture intake, so counting only capture intake would make coverage fall as work succeeds.

Uploaded counts come from the verified local upload manifest, not direct UNC scanning. This is required because the Flask service runs as LocalSystem and cannot access the network share.

The browser JSON helper now:

- disables caching
- handles JSON explicitly
- redirects expired sessions to login
- shows a controlled transient server error
- retries on the next polling interval

Verified BANGLE 22 state at handover:

- Stock: 88
- Captured: 52
- Processed: 52
- Approved: 52
- Rejected: 0
- Uploaded: 52
- All three progress bars: 59%

## 9. Cost guard and paid-call safety

The owner explicitly raised the cap to:

- 300 calls/day
- `$100` daily cap

These values are in `config\azure_flux2_guard.json`.

Important rules:

- Never silently increase them again.
- Never issue automatic retries.
- Never bypass `ACTIVE_CALL.lock` without proving it is stale.
- Use dry-run/prompt/reference validation before paid calls.
- Confirm prompt approval hash after changing the production prompt.
- `config\prompt_approval.json` contains the currently approved prompt hash.

## 10. Service restart procedure

Preferred controlled restart:

1. Create `data\restart_catalogue.request`.
2. Run scheduled task `AradhanaCatalogueSupervisor`.
3. Supervisor restarts only `AradhanaCatalogueTool` and removes the request.
4. Verify port 7654 and `/api/health`.

Do not kill unrelated capture or printer-relay processes.

Main service logs:

- `service_app_stdout.log`
- `service_app_stderr.log`
- `logs\supervisor.log`

## 11. Validation performed

Focused regression suite:

```powershell
python -m pytest tests/test_orn_item_image_sync.py tests/test_category_dashboard.py tests/test_review_queue_source_routing.py -q
```

Result: `19 passed`.

Additional live verification:

- Main category endpoint returned HTTP 200 JSON with 57 rows.
- Dashboard timestamp changed on successive one-second polls.
- BANGLE 22 rendered exactly three progress bars.
- Upload worker task published a queued `BL18_10` test job and returned the queue to zero.
- 192 expected current-stock approvals matched 192 main `.Jpg` files.
- Every main image validated as RGB JPEG.
- Ornate NX created 192 `_Thumb.jpg` files.
- Obsolete server PNG copies were backed up and removed.
- PNG backup: `reports\ornate_nx_png_backup_20260815`
- No paid FLUX call was used for the infrastructure/routing/dashboard work.

## 12. Tests added or expanded

- `tests\test_azure_flux2_lock.py`
- `tests\test_catalogue_reference_guides.py`
- `tests\test_category_dashboard.py`
- `tests\test_category_geometry_hints.py`
- `tests\test_codex_repair.py`
- `tests\test_orn_item_image_sync.py`
- `tests\test_reference_color_report.py`
- `tests\test_review_queue_source_routing.py`

Tests cover paid-call locking, Bali routing, item hints, colour localisation, Codex repair import, source routing, rejected delivery variants, dashboard lifecycle counts, exact Ornate NX naming, RGB JPEG conversion, queue removal and stock-membership blocking.

## 13. Known constraints and next checks

1. Local `master` and remote `origin/master` have unrelated histories. At handover time local was 2,022 commits ahead and 1,834 behind with no merge base. Never force-push remote master.
2. Use the dedicated remote handover branch recorded in the final Codex message.
3. `AradhanaOrnItemUpload` depends on user `kaila` being logged in because it uses an Interactive task token.
4. If uploads stop, inspect queue/status and Scheduled Task result before touching review state.
5. The tool currently publishes only Ornate NX Image 1. Do not invent `_2`/`_3` output without a product requirement and explicit source-selection design.
6. Current Stock Excel does not contain `ER22_74` or `GR22_135`; their upload failures are expected safeguards.
7. Category dashboard stock-label cache is 60 seconds; lifecycle/upload polling is one second.
8. Mutable reports and review files change during normal operation. Capture a fresh operational snapshot before future handovers.

## 14. Immediate smoke-test checklist for Claude

```powershell
Set-Location C:\Users\kaila\Desktop\JewelleryCatalogTool

Get-Service AradhanaCatalogueTool,AradhanaCaptureServer
Get-ScheduledTaskInfo -TaskName AradhanaOrnItemUpload
Get-Content .\data\orn_item_upload_queue.json

python -m pytest tests/test_orn_item_image_sync.py tests/test_category_dashboard.py tests/test_review_queue_source_routing.py -q

python -c "import orn_item_image_sync as s; print(len(s.uploaded_labels()), s._load_json(s.QUEUE), s._load_json(s.STATUS))"
```

Then open `http://127.0.0.1:7654/dashboard`, confirm Category Coverage says `Live`, and inspect BANGLE 22 for three bars.

## 15. Files central to this handover

- `app.py`
- `review_queue.py`
- `category_dashboard.py`
- `templates\dashboard.html`
- `orn_item_image_sync.py`
- `codex_repair.py`
- `reference_color_report.py`
- `category_geometry_hints.py`
- `catalogue_reference_guides.py`
- `tools\azure_flux2_guarded.py`
- `config\azure_flux2_guard.json`
- `config\flux2_pro_catalogue_prompt.txt`
- `config\prompt_approval.json`

Preserve the separation of authority:

- Stock Excel: valid item identity and exact stock category
- Image 1: jewellery design identity
- Image 2/reviewed guide: pose and spacing only
- Review state: human/tool decision
- Folder routing: lifecycle state
- Upload manifest/queue: Ornate NX delivery state
- Guard ledger/lock: paid-call safety

# Handover to Codex — JewelleryCatalogTool (from Claude, quota exhausted)

## Latest error from user's newest run (after the wrong-bg run was killed and
restarted) — also not yet investigated
`Pair 1 [LR22_2]: BLURRY_OUTPUT: 139KB at 1024×1024 (sharpness 75 < 100.0)`
— same pair (LR22_2) that hit DESIGN_MISMATCH earlier this session (see
`design_verify_local.py` notes below). Blur check is in `app.py` near the
"BLURRY_OUTPUT" string (Laplacian variance on the raw engine output,
`BLUR_LAPLACIAN_MIN` threshold ~100). Worth checking whether this specific
source photo (`input/LR22_2.jpg` — small gold ring, photographed held in
fingers against a white card, not the usual black velvet) is just a
consistently hard case for every downstream quality gate, not only design-
match. May be worth the user re-shooting this one item's source photo before
sinking more debugging time into it.

## Immediate open bug — INVESTIGATE FIRST
User reported: a manual test run via `/api/copilot_run` **correctly rejected a
design-mismatched generation, but used the WRONG background image** for the
pair. The run was killed (process stopped, port 7654 freed) before this was
diagnosed. Nothing else has looked at this yet.

Start here:
- `app.py:698` `_resolve_bg_paths(bg_names, category)` — resolves the
  background name(s) picked in the UI into actual file paths.
- `app.py:724` `_resolve_pair_assets(...)` — picks which background (and
  model config) a given pair actually gets, including any per-pair cycling
  logic (`variety_auto`).
- The Copilot-primary runner is `_run_copilot_job` (~app.py:1720), which
  calls `_resolve_bg_paths` once (~line 1742) then `_resolve_pair_assets`
  per pair (~line 1769).
- Need to find out: what background did the user select in the UI vs what
  actually got used. Likely candidates: `_resolve_bg_paths` returning the
  wrong file for a given category name, or `_resolve_pair_assets`'s cycling
  logic advancing to the wrong index, or a stale/cached bg selection from a
  previous run's config.
- **Ask the user which background they expected vs which one appeared** —
  that wasn't captured before quota ran out.

## Servers — current state
- Both `app.py` (port 7654) and `capture_server.py` (port 7655) were
  relaunched this session via direct `py -3.11 <file>.py` (not the desktop
  shortcut's vbs wrapper) so output could be live-tailed. **The app.py
  process was killed** to stop the bad test run — it is NOT currently
  running. Capture server may still be running; check before restarting
  anything.
- `app.py` now has a single-instance guard (`_enforce_single_instance()`,
  top of `if __name__ == "__main__"`) — a PID lock file at
  `catalogue_tool.lock`, checked via `psutil`. A second `py -3.11 app.py`
  will refuse to start and print which PID is already running. This is
  new and tested working.

## This session's other changes (all done, tests passing — 463/463 as of
last full run)
1. **Gemini engine swapped from browser automation to cookie-based API.**
   `gemini_web_chat.py` (CDP/browser-driven) is no longer used in
   production — `gemini_img.py` (uses `gemini_webapi` + cookies from
   `gemini_web_auth.py`) is now called everywhere `gemini_web_chat` used to
   be (search app.py/autonomous_pipeline.py for `gemini_img` imports aliased
   as `_gwc`/`_g`/`gemini_web_chat` — some are import aliases, check the
   actual `import` line, not just the variable name used). All 5 Gemini
   accounts and all 5 Copilot accounts were verified as distinct (no
   duplicate logins) by end of session.
2. **Tag image dropped from Copilot/Gemini prompts.** `copilot_img.py` and
   `gemini_img.py`'s `generate()` no longer upload a tag/price-tag photo by
   default (item code comes from filename) — added a `send_tag_image: bool
   = False` param, used by `_do_model_shoot` in app.py (~line 1307) which
   sets it `True` because it repurposes `tag_path` to carry a model
   reference photo. **Do not remove this parameter without understanding
   both call patterns** — removing tag upload unconditionally broke model
   shoots once already this session (caught and fixed).
3. **Capture pipeline — tag-closeup-as-main-photo bug.** Root cause:
   `capture_tool.py`'s `save_pair()` did zero content validation on the
   "jewel" photo bytes — a QR/tag close-up submitted as the jewel shot got
   saved as the primary deliverable with no check. Fixed by adding
   `_jewellery_clearly_visible()` (Gemini vision call, fails OPEN on error)
   to `save_pair()`, with a retake-or-save-anyway popup added to
   `templates/capture.html` (mirrors the existing blur-warning UX exactly —
   see `showBlurWarningPopup`/`showVisibilityWarningPopup`). Confirmed rule
   from user: **a tag/QR being visible in frame is fine — only reject if the
   jewellery itself isn't clearly visible.**
4. **Backlog scan in progress** (may have been killed along with app.py —
   check if `_scan_jewellery_clarity.py` process is still alive). It scans
   73 files in `capture_intake` that were flagged by a QR-detection pass
   (`_qr_flagged_main_files.json`) as possibly having this problem, checking
   each against the real "clearly visible" rule via Gemini vision (round-
   robins `GEMINI_API_KEY`/`GEMINI_API_KEY2`, ~6s/request to respect the
   5-req/min free-tier limit per key). Partial results in
   `_jewellery_clarity_results.json` — last checked, 38/73 done, 0 flagged
   as real violations (most QR-detected files are fine per the "jewellery
   clearly visible" rule; only ~4 known examples — LC22/57, /28, /84,
   /59 — were confirmed real problems by the user directly).
5. **Design-mismatch (DESIGN_MISMATCH) threshold — flagged as possibly too
   aggressive, NOT changed.** `design_verify_local.py`'s thresholds
   (`SIMILARITY_HARD_FAIL = 0.55`, `SIMILARITY_ACCEPT = 0.68`) are, by the
   module's own docstring, "provisional, derived from a two-pair margin" and
   were never properly calibrated (`calibrate()` exists but has never been
   run over a real batch — there are only 2 real generated images in the
   whole system to calibrate against: `output/AD/LR22_8.jpg`,
   `output/CALCUTTI/ER22_107.jpg`). A real pair (LR22_2) got rejected at
   similarity 0.474 after a corrective retry, output deleted, with **no
   debug artifact saved** (`verify_design()` supports a `debug_dir` param to
   save segmented cutouts for inspection, but `app.py`'s call site doesn't
   pass one). Proposed but not yet implemented: (a) pass `debug_dir` so
   future rejects are inspectable, (b) stop deleting hard-fail rejects
   outright — move to a `_needs_review` folder instead so nothing is
   silently destroyed on an unproven threshold.

## Hard rule from the user this session
**Never delete/move any file under a production folder (`capture_intake/`,
`output_aradhana/`, `output/`, `master backup/`, etc.) without informing the
user first and getting confirmation** — even a file that's clearly wrong
(e.g. a tag-photo-as-main-file). Saved to Claude's memory as
`catalogue-tool-no-silent-file-deletion`.

## Scratch files from this session (safe to delete, not production data)
`_qr_flagged_main_files.json`, `_jewellery_clarity_results.json`,
`_scan_jewellery_clarity.py`, `_gemini_cookies_*.json`,
`_copilot_acct*.png`, `_gemini_acct*.png` in the project root — all
diagnostic/scratch, not referenced by any production code path.

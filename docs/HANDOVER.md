# Aradhana Catalogue Tool — Handover

Local AI tool that turns raw jewellery photos into unified, branded catalogue tiles for the Aradhana Jewellers app. ~2000 ornaments to process. This doc is the single source of truth for picking the work up.

## TWO MASTER RULES (non-negotiable)
1. **Preserve design always.** Output must be the customer's real photographed piece. No AI redraw/relight that alters geometry. (IC-Light at full denoise redraws → banned from catalogue path; OK only for optional marketing heroes.) Cutout/matting only changes alpha — fine.
2. **Alert on uncertain tag reads, in-process.** If unsure what the price tag says (low confidence, missing field, sources disagree, implausible value), STOP and flag for the operator to fix then & there — never silently guess. CLI: interactive prompt on a TTY else `needs_review.csv`. UI: "needs review" card with inline SKU/weight fix.

## Environment (all installed, working)
- **Python**: `C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe` — has torch **2.12.0.dev+cu128 (Blackwell sm_120 OK)**, ultralytics, segment_anything, pytesseract, opencv, rembg, withoutbg, flask, scipy, pymupdf, PIL.
- **GPU**: RTX 5070 Laptop, **8 GB VRAM** → run VLM (Ollama) and SAM **sequentially**, never together. Engine calls `vision.unload()` to free VRAM before SAM.
- **Ollama** (v0.30.10) running on :11434. Vision model **`qwen2.5vl:7b`** (the brain). Text models also present (qwen3:14b etc.) for future description-gen.
- **SAM**: `sam_models/sam_vit_h_4b8939.pth` (ViT-H, 2.5 GB).
- **Tesseract**: `C:\Program Files\Tesseract-OCR\tesseract.exe` (legacy OCR; superseded by VLM, kept as `ocr_tag()`).
- **BiRefNet**: via `rembg` (`new_session("birefnet-general")`). SOTA background removal; model (~380 MB) auto-downloads to HF cache on first run. **PRIMARY cutout method** — replaces the brittle brightness-threshold seeding for SAM. No prompt needed, works on any background colour.
- **withoutbg**: `pip install withoutbg` done; models auto-downloaded to HF cache. Apache-2.0, prompt-free matting, CPU. Now **FALLBACK 2** (after BiRefNet fails → SAM fails).
- **ComfyUI + IC-Light** (marketing-hero experiments only): `C:\pinokio\api\comfy.git` (env Blackwell-OK after a `sitecustomize.py` SSL patch; model `models/unet/iclight_sd15_fc.safetensors`).

## Brand spec
- Gold `#CCA137` / `#F7CA5B`; brand blue `#23519D`; **EST. 1992**; tagline "Legacy of Purity. Promise of Trust."; 22K.
- Transparent logo (hi-res): `C:\Users\kaila\Desktop\New folder (2)\aradhana_logo_hd.png` (referenced by engine as `LOGO`).
- Brand kit PDF: `C:\Content\Logos\Aradhana Jewellers Logo 4.6.26\...pdf`.

## Files (in `C:\Users\kaila\Desktop\JewelleryCatalogTool`)
- `aradhana_engine.py` — pipeline: cutout → enhance → straighten/symmetry → branded tile. Importable; also a CLI (`python aradhana_engine.py`).
- `vision.py` — VLM brain (Ollama/qwen2.5vl): `analyze()` (type/pieces/has_tag/upright/tier), `read_tag()` (full-image @2000px → SKU/G.W/N.W/pieces/confidence), `locate()` (grounding — UNRELIABLE, do not use), `qc()`, `unload()`.
- `app.py` — Flask web UI. `templates/index.html` — frontend.
- `backgrounds/` — photographic per-type backgrounds (user-added): bg1_white_leaves, bg2_dark_props, bg3_dark_crystals, bg4_golden_bokeh, bg5_white_satin.
- `inventory.csv` — optional SKU→weight/category (tag is primary source; CSV is a cross-check/override).
- `RUN_CATALOG.bat` — double-click CLI launcher. `CAPTURE_CHECKLIST.md` — staff capture guide.
- `input/` (drop photos), `processing/` (staged), `output_aradhana/` (finished tiles), `needs_review.csv` (Rule-2 log).

## Workflow / how to run
- **UI (preferred):** `Python311\python.exe app.py` → http://127.0.0.1:5000  (or preview config `.claude/launch.json` name `aradhana-ui`).
  - Steps: **1 Load** (from `input\` or file/folder picker → uploads to input) → **2 Ornament type** (Auto, or pick; "Other" reveals a name field) → **3 Rename & Stage (OPTIONAL)** → **4 Run** (background job, **live progress: current file / X-of-N / % / ETA**) → review cards (inline SKU/weight fix → re-generate) → download.
- **Capture model (DECIDED):** photos in **PAIRS — 1st = jewellery, 2nd = its tag**. Tool reads tag → SKU+net weight → names output by SKU. Do NOT ask user to pre-name or supply SKUs.
- VRAM: PASS A = all VLM (tag read + type) → `vision.unload()` → PASS B = SAM/withoutbg cutout + compose.

## What WORKS
- VLM **tag reading on gold** (`JBO612 / 14.390`, gold pair) — solved the OCR problem Tesseract failed.
- VLM **classification** (earrings/ring/etc.) and **tier** (CLASSIC/PREMIUM) suggestion.
- **Cutout — PRIMARY: BiRefNet** (rembg `birefnet-general`): prompt-free, works on dark velvet, red cloth, white tray, any background. Best filigree/chain edge quality. ~0.1–0.5 s/image on GPU.
- **Cutout — FALLBACK 1: dark+SAM** (existing): for specular highlights that BiRefNet may under-threshold. Only triggers if BiRefNet result is below coverage guard or fails.
- **Cutout — FALLBACK 2: withoutbg**: last-resort CPU fallback.
- **Straighten + symmetric pair** (PCA; matched pair = straighten cleaner one + mirror) — matches the "upright & symmetric" target.
- **Branded tile**: per-type backdrop, logo + EST.1992 + faint watermark + SKU + NT.WT + category badge; zoomed into a **safe box** `(0.09,0.23,0.91,0.85)*S` that never overlaps logo/text/edges.
- **Web UI** with optional staging + **live progress** (verified: `/api/run` background thread + `/api/progress` polling).

## OPEN ISSUES / NEXT STEPS (priority order)
1. **Re-test withoutbg fallback (almost done).** Encoding bug fixed (stdout reconfigured to UTF-8 in engine top); withoutbg models now downloaded. Last test only failed because the input file had been **staged** (moved to `processing/001_jewel.jpeg`). **ACTION:** run `cutout()` on `processing/001_jewel.jpeg` and on a fresh silver-on-red shot; confirm method-2 (withoutbg) gives a clean silver matte without red bleed. Engine `cutout()` tries METHOD 1 (dark+SAM) then METHOD 2 (withoutbg) automatically.
2. **Cutout on coloured/cluttered backgrounds.** Brightness-on-dark fails on red velvet / bright trays (flags "reshoot"). withoutbg (method 2) is the fix but currently only triggers when method 1's dark-guard trips OR method 1 yields nothing. Silver-on-red slipped through method 1 with **red bleed + rose tint**. **ACTION:** consider routing to withoutbg whenever VLM material==silver OR background not dark; and add red-bleed cleanup (suppress saturated-red pixels in the matte).
3. **VLM tag false-confidence (Rule 2 gap).** VLM read silver tag `80P 67 / 40.240` as `JB0671 / 240` and said **high** confidence → no alert. **ACTION:** treat every tag-only read as "Confirm" regardless of stated confidence; add sanity checks (SKU regex, weight plausibility vs piece size, G.W≥N.W); cross-check with CSV when present. (App already adds a "Confirm tag read" alert when sku+wt present — make it always-on for tag-only sources.)
4. **Backdrops.** User added photographic backgrounds, but bg3_dark_crystals (used for ring/bracelet) is busy/distracting and silver landed on white satin. **DECISION NEEDED:** clean gradient (earlier approved black+gold for earrings) vs curated photo backgrounds; pick simpler/premium ones per type. Mapping in `TYPE_BG_FILE` (photo) and `TYPE_BG`/`type_bg()` (gradient fallback).
5. **Capture standard.** Reliable results REQUIRE: one item, plain DARK velvet, centered, fill frame, no box/tray clutter — **silver on BLACK, not red**. Update `CAPTURE_CHECKLIST.md` accordingly.
6. **VLM grounding (`vision.locate`)** returns wrong coords via Ollama — do NOT use for SAM boxes.

## ROADMAP (later, local AI)
- 3 variations per ornament, one of which is a **model wearing the piece** (virtual try-on / on-model). All local. On-model is an additional marketing asset — must not replace the design-accurate tile (Rule 1).
- Optional Real-ESRGAN/upscale: NOT a current bottleneck (phone photos are already hi-res) and SR risks hallucinating filigree (Rule 1). **chaiNNer/Upscayl = super-resolution GUIs; skip** — no capability we can't call directly in Python, and not our bottleneck (capture + cutout edges are). Revisit only for genuinely low-res/distant shots, with a conservative model.

## STABILIZATION PASS (Claude, 2026-06-20 PM)
Fixed the regression spiral:
- **Ring "Swiss-cheese" holes FIXED** — SAM path no longer `bitwise_and`s the SAM mask with the brightness mask (that punched holes through shiny/dark gold). SAM mask is trusted as-is. Verified: gent's rings cut out solid.
- **Removed the HSV gold-mask cutout path entirely** — it was inherently hole-prone on specular gold. Mixed/non-dark backgrounds now go to withoutbg (coherent matte) or get flagged.
- **Orientation made DETERMINISTIC** — `_straighten` now only levels a small (<25°) hand tilt; it NEVER flips 180° or rotates 90° (that guessing caused the repeated upside-down output). Removed the VLM `upright` auto-flip.
- **Manual rotate in UI** — every result card has ⟲ / 180° / ⟳ + Apply; calls `/api/relabel` with a `rotate` param → `compose(..., rotate=deg)`. Operator controls orientation.
- **Tag-in-frame: FLAG, never damage** — SAM path runs `_matte_artifact_reason`; if a large flat paper tag is fused into the matte it returns None with "shoot tag separately". (Do NOT try to surgically cut tags — it destroys diamond pavé = breaks Rule 1.)
- **Feedback loop fixed** — `LAUNCH_CATALOG_UI.bat` now kills any server on :5000 before starting (so latest code loads); Flask `TEMPLATES_AUTO_RELOAD` on.

**KEY TRUTH (re-confirmed):** the staged test set (001–012) are NON-CONFORMING captures (tags in the jewellery frame, rings angled on mixed/bright backgrounds, in boxes) → they correctly flag or come out poor. The pipeline + branding are correct for CONFORMING captures (one piece, black velvet, fill frame, NO tag in the jewellery photo, tag as separate 2nd photo). Do not chase bad captures in code — fix capture.

## Current disk state at handover
- `input/` empty; `processing/` has `001_jewel.jpeg` + `001_tag.jpeg` (one pair staged); `output_aradhana/` has test tiles (`JB0671.jpg`, `_wbgtest_*`, `_wbg_silver` attempts).
- A Flask server may be running on :5000 (preview). Engine top now reconfigures stdout to UTF-8 (withoutbg ✓ fix) and sets PYTHONUTF8.

---

## V4 CATALOGUE BACKGROUND SET (Claude/Cowork session, 2026-07-25)

Separate sub-task from the cutout/tagging engine above: generating a **4th catalogue background style** (`_category_bgs_v4`), a luxury-brand direction, on top of the existing 3 sets already produced and reviewed:
- `output_aradhana/generated_backgrounds/_category_bgs/` (v1) — superlight ice-blue (#eaf1fa), clean minimal, made by `_gen_category_bgs.py`.
- `_category_bgs_v2/` — rich cobalt/sky blue (#2f74b5) + Indian-handicraft props (brass/wood stands, lotus/jasmine/marigold accents), made by `_gen_category_bgs_v2.py`.
- `_category_bgs_v3/` — same rich blue but as a silk/satin drape + ONE softly-blurred traditional accent (diya/peacock feather/temple arch) per category, cinematic shallow DOF, made by `_gen_category_bgs_v3.py`.
- `output_aradhana/finished_showcase/{v1_clean,v2_heritage,v3_traditional}/` — product-composited previews of all 3 sets already exist for all 20 categories, so those decisions were already reviewed once before this session.

User's ask this session: make v4 "for a luxury jewellery brand like Aradhana Jewellers Boisar," covering every category, but **share 3 different color/design inspirations first** before generating the full set — i.e. don't mass-generate blind again.

### What's done
- Read all 3 existing generator scripts to confirm the established pattern (`OUT_DIR`, a `STYLE_SUFFIX` string, a `CATEGORIES` dict of `category -> prop/accent description`, loop that calls `codex_img.generate_background_only()` first then falls back to `copilot_img.generate_background_only()` per category, skips any category whose output file already exists).
- Picked 3 v4 concepts, deliberately NOT more blue (to give real contrast vs v1–v3):
  - **A_ivory_gold** — champagne-ivory field (#F3E9D8), warm gold glow, carved ivory-marble stand + brass trim. Minimalist global-luxury-boutique look (Cartier/Tiffany-adjacent). Plays best against a light website UI; lets brand gold (#CCA137/#F7CA5B) lead.
  - **B_emerald** — deep emerald silk (#0B4D3A), carved rosewood + gold-leaf stand, one softly-blurred brass diya (reuses v3's cinematic-blur trick, new color family). Traditional Indian heritage/bridal, warm and festive.
  - **C_wine_regal** — deep burgundy velvet (#5C1A2B), mahogany + gold-filigree stand, single dramatic spotlight with hard shadow falloff. Most opulent/editorial of the three — flagship bridal hero-shot feel.
- Wrote `_gen_category_bgs_v4_preview.py` (repo root) — generates ONE sample image per concept (necklace only, the flagship shape) to `output_aradhana/generated_backgrounds/_category_bgs_v4_preview/preview_{concept}.jpg`, so the user can pick a direction before the full ~21-category batch is built. Follows the exact same Codex→Copilot-fallback pattern as v1–v3.

### BLOCKED as of 2026-07-25 ~19:30 IST — read before touching this again
Ran the preview script 3x. Neither generation engine is currently usable:
- **Codex**: `CODEX_RATE_LIMIT`. The `reset=` timestamp climbed higher on each successive attempt in this session (…1067 → …1480 → …1568) — i.e. **each retry appears to restart its own ~1hr countdown** rather than counting down to a fixed clock time. **Do not rerun the script repeatedly** — that is actively what's kept Codex rate-limited. Leave it genuinely untouched for a full hour minimum, then try exactly once.
- **Copilot**: got further (opened a session, typed + submitted the prompt) but hit `COPILOT_IMAGE_QUOTA: daily image-generation limit reached` — a **daily cap**, not a short cooldown. Won't clear until the next day regardless of retries.
- The Claude/Cowork built-in image-gen tool (`mcp__babd46cd...__generate_image`) is also at 0 credits on a free plan (confirmed via its `balance` tool) — would need a paid top-up/plan upgrade to use as an immediate unblocker instead of waiting on Codex/Copilot.

### Next steps (pick up here)
1. Once Codex has sat untouched for a real hour (or it's the next day and Copilot's daily quota has reset), run **exactly once** from an already-open terminal — NOT a double-click, which closes the console instantly and hides the error output:
   ```
   cd "C:\Users\kaila\Desktop\JewelleryCatalogTool"
   C:\Users\kaila\AppData\Local\Programs\Python\Python311\python.exe _gen_category_bgs_v4_preview.py
   ```
2. Once the 3 `preview_*.jpg` files exist in `_category_bgs_v4_preview/`, view them with the user and get a pick (A/B/C, or a blend/tweak request).
3. Once a concept is picked, build the FULL v4 script mirroring `_gen_category_bgs_v3.py`'s structure exactly: a 21-entry `CATEGORIES` dict (same 21 keys as v1–v3: earrings, ladies_rings, gents_rings, ladies_chains, gents_chains, ladies_bracelet, gents_bracelet, ladies_kada, gents_kada, locket, pendant, tops, wati, mangalsutra_short, mangalsutra_long, bangles, ladies_bali, mens_bali, necklace, silver, diamond), each with a category-matched prop description in the chosen concept's palette/material language, plus that concept's `STYLE_SUFFIX`. Save to `output_aradhana/generated_backgrounds/_category_bgs_v4/`. After that, probably also want a `finished_showcase/v4_*` composite pass like the other 3 sets got.
4. Alternative unblocker if the user doesn't want to wait: top up Claude/Cowork image credits and generate the 3 previews (and/or the full set) directly in chat instead of depending on Codex/Copilot.

### Key files (this sub-task)
- `_gen_category_bgs_v4_preview.py` — new this session, 3-concept preview generator (necklace only).
- `_gen_category_bgs.py` / `_gen_category_bgs_v2.py` / `_gen_category_bgs_v3.py` — existing pattern the full v4 script should follow.
- `output_aradhana/generated_backgrounds/_category_bgs{,_v2,_v3,_v4_preview}/` — output folders (v4_preview created but still empty at handover time — nothing has generated successfully yet).
- `copilot_cooldown.json` / rate-limit state files — transient engine state, don't hand-edit.

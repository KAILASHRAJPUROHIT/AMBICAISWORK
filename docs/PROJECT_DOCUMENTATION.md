# Aradhana Jewellers — Auto Catalogue Tool
## Complete Project Documentation

---

## What This Tool Does

This tool automates the creation of professional jewellery catalogue images for Aradhana Jewellers. Given raw camera photos of jewellery items and their price tags, it:

1. **Composites** each jewellery piece onto a branded Aradhana studio background
2. **Labels** each image with the item code read from the price tag
3. **Generates a model lifestyle shot** — jewellery worn by a model in a professional pose
4. **Deduplicates** against a 30-day database to catch re-submissions
5. **Saves** final images organised by jewellery category

Input: raw DSLR photos (jewel + tag pairs)
Output: `output_aradhana/{category}/{ItemCode}.jpg` + `{ItemCode}_model.jpg`

---

## Folder Structure

```
C:\Users\kaila\Desktop\JewelleryCatalogTool\
│
├── app.py                    ← Flask server (main entry point)
├── LAUNCH_CATALOG_UI.bat     ← One-click launcher (starts Chrome sessions + server)
│
├── input\                    ← Drop raw DSLR photos here
│   └── TRAY 1\              ← Subdirectory for trays (copy to root before processing)
│
├── processing\               ← Staged files (renamed _jewel/_tag after staging)
│
├── output_aradhana\          ← FINAL OUTPUT — organised by category
│   └── tops\                ← e.g. tops/TP22_30.jpg + tops/TP22_30_model.jpg
│
├── output_copilot\           ← Temp staging for Copilot raw outputs
│   └── _upload_tmp\         ← Temp copies for CDP upload (auto-deleted)
│
├── backgrounds\              ← Plain backgrounds (not watermarked)
│
├── models\                   ← Pre-generated model reference images (71 files)
│   ├── female\
│   └── male\
│
├── dataset\                  ← Training/reference dataset images
│
├── templates\
│   └── index.html           ← Web UI (single-page tool interface)
│
├── progress_{category}.json  ← Resume checkpoint per category (e.g. progress_tops.json)
├── catalogue_db.json         ← 30-day duplicate detection database
├── copilot_cooldown.json     ← Persisted 15-min rate-limit cooldown for Copilot
├── port.txt                  ← Flask port (default 7654)
├── keys.py                   ← API keys (Gemini, HuggingFace — KEEP PRIVATE)
│
├── app_log.txt               ← Flask server log
├── server_err.log            ← Stderr capture from server process
│
│── Engine modules (Python):
│   ├── copilot_img.py        ← Engine 1: Microsoft Copilot via Chrome CDP
│   ├── codex_img.py          ← Engine 2: ChatGPT Plus via backend-api/codex
│   ├── chatgpt_conv_img.py   ← Engine 3: ChatGPT conversation API (last resort)
│   ├── gemini_api_img.py     ← Engine 4: Google Gemini API (free AI Studio key)
│   ├── adobe_firefly_img.py  ← Engine 6: Adobe Firefly API (experimental)
│   ├── model_engine.py       ← Model shoot prompt builder + model roster
│   ├── catalogue_db.py       ← Duplicate detection + 30-day DB
│   ├── chatgpt_auth.py       ← ChatGPT token extraction from Chrome profile
│   ├── gemini_auth.py        ← Gemini browser session auth
│   ├── gemini_bg.py          ← Gemini browser engine (CDP-based)
│   ├── gemini_img.py         ← Gemini API image generation
│   └── vdesk.py              ← Virtual desktop manager (off-screen Chrome windows)
│
└── Diagnostics / dev scripts (prefix _diag_, _test_, adobe_*):
    ├── _diag_*.py            ← Development diagnostic scripts
    ├── _test_*.py            ← Engine test scripts
    └── adobe_*.py            ← Adobe API exploration scripts
```

**External dependency — Backgrounds folder:**
```
C:\Users\kaila\Desktop\Backgrounds\Watermarked\
    earrings.png, tops.png, necklace.png, etc.   ← Aradhana watermarked studio backgrounds
    1.png, 2.jpg … 14.jpg                         ← Numbered generic backgrounds
```

---

## How to Start the Tool

### Option A — BAT launcher (recommended)
Double-click `LAUNCH_CATALOG_UI.bat`

This automatically:
- Kills any previously running server
- Starts Chrome on port 9222 (ChatGPT), 9223 (Gemini), 9224 (Copilot) — off-screen
- Starts Flask server (`app.py`) hidden
- Opens the tool UI in your default browser at `http://127.0.0.1:7654`

### Option B — Manual
```powershell
# Start Flask server
cd "C:\Users\kaila\Desktop\JewelleryCatalogTool"
python app.py

# Start Copilot Chrome (must be logged in to copilot.microsoft.com)
Start-Process chrome.exe --remote-debugging-port=9224 `
    --user-data-dir="...\CopilotCatalogChrome" https://copilot.microsoft.com
```

---

## Processing Pipeline — Step by Step

### Step 1 — Drop photos into `input\`

Raw DSLR photos go into `input\`. They come in pairs:
- Shot N (odd) = jewellery photo
- Shot N+1 (even) = price tag photo

The tool sorts files by the **last numeric sequence in the filename** (camera roll order).

For tray-based workflows (e.g. `input\TRAY 1\`), copy tray files to `input\` root first:
```powershell
Copy-Item "input\TRAY 1\*.JPG" "input\" -ErrorAction SilentlyContinue
```

### Step 2 — Stage (optional)

Click **Stage** in the UI → calls `/api/stage`

Renames files with `_jewel` / `_tag` suffixes and moves to `processing\`:
```
001_DSC00256_jewel.jpg
001_DSC00256_tag.jpg
002_DSC00258_jewel.jpg
...
```

Staging is optional — the batch runner works with unstaged `input\` files too.

### Step 3 — Select background + category in UI

Choose from the watermarked backgrounds at `C:\Users\kaila\Desktop\Backgrounds\Watermarked\`.
Choose the jewellery type (earrings, tops, necklace, etc.).

### Step 4 — Run batch

Click **Run Copilot** in the UI → calls `/api/copilot_run`

The server starts `_run_copilot_job()` in a background thread.

---

## Engine Cascade — Studio Shot

For each pair the tool tries engines in order, falling back if one fails:

```
┌─────────────────────────────────────────────────────┐
│  Engine 1: Copilot (copilot_img.py)                │
│  - Drives Chrome on port 9224 via Chrome DevTools   │
│    Protocol (CDP / WebSocket)                       │
│  - Navigates to copilot.microsoft.com               │
│  - Uploads 3 images: jewel + tag + background       │
│  - Sends compositing prompt                         │
│  - Listens for imageGenerated WebSocket event       │
│  - Downloads result image                           │
│  - Rate limit: 15-min cooldown on HTTP 429          │
└────────────────────┬────────────────────────────────┘
                     │ FAIL (any error, timeout, or 429)
                     ▼
┌─────────────────────────────────────────────────────┐
│  Engine 2: Codex (codex_img.py)                    │
│  - Pure HTTP — no browser, no CDP                   │
│  - Uses ChatGPT Plus OAuth token from               │
│    ~/.codex/auth.json (from npx @openai/codex login)│
│  - POST to chatgpt.com/backend-api/codex/responses  │
│  - Supports token pool: auth.json + auth_2.json …   │
│    (rotates accounts on 429 rate limit)             │
└────────────────────┬────────────────────────────────┘
                     │ FAIL
                     ▼
┌─────────────────────────────────────────────────────┐
│  Engine 3: chatgpt_conv_img (chatgpt_conv_img.py)  │
│  - ChatGPT conversation API (last resort)           │
│  - Uses Bearer token from Chrome cookie DB          │
│  - Full conversation flow: sentinel → PoW → upload  │
│    → stream SSE → poll for image → download         │
└─────────────────────────────────────────────────────┘
```

Additional engines available (not in default cascade):
- **Gemini API** (`gemini_api_img.py`) — free Google AI Studio key, 1500 req/day
- **Photoshop** (`photoshop_engine.py`) — local Photoshop "Select Subject" AI
- **Adobe Firefly** (`adobe_firefly_img.py`) — Adobe generative fill API

---

## Engine Cascade — Model Shoot

After every successful studio shot, the tool immediately generates a **model lifestyle image** — the same jewellery worn by a model. Same cascade order:

```
Copilot → Codex → chatgpt_conv_img (wrapper)
```

The model is selected from `models\` folder. The tool rotates through 3 variants per batch (1→2→3→1) for variety. Model prompts are built by `model_engine.py`:

| Category | Body zone | Model type |
|---|---|---|
| earrings, tops | face | F1 or F2 (contemporary/festive woman) |
| necklace, locket, pendant | neck | F1 or F2 |
| ladies_rings | hand | F1 |
| ladies_bracelet, ladies_kada | wrist | F1 |
| gents_rings | hand | M1 |
| bangles | wrist | F1 |
| mangalsutra_short/long | neck/bridal | F2 or F3 (bride) |

Model personas defined in `model_engine.py`:
- `F1` — Contemporary Indian woman, 20s, luxury aesthetic
- `F2` — Traditional festive Indian woman
- `F3` — Indian bride
- `F4` — Mature sophisticated woman
- `M1/M2/M3` — Male models
- `KG/KB` — Girl/Boy child

---

## Post-Generation Pipeline (`_finalise_output`)

Every engine output passes through **10 mandatory checks** before being saved:

| Step | Check | Action on fail |
|---|---|---|
| 1 | **Size floor** — file > 30 KB | Delete + reject |
| 2 | **Input-match** — output MD5 ≠ any input MD5 | Delete + reject (engine echoed the input) |
| 3 | **Blurry check** — JPEG size ratio at resolution | Delete + reject |
| 4 | **Gemma jewellery check** — AI confirms jewellery present | Reject (no jewellery detected) |
| 5 | **Per-run pixel hash** — not duplicate of another SKU this run | Reject (cross-SKU duplicate) |
| 6 | **In-run tag dedup** — same label not already saved this run | Skip |
| 7 | **Move to final path** — `output_aradhana/{category}/{Label}.jpg` | — |
| 8 | **30-day DB check** — `catalogue_db.json` for cross-run duplicates | Warning (logged) |
| 9 | **Save progress** — `progress_{category}.json` | — |
| 10 | **Model shoot** — triggers model image generation | Warns if fails |

---

## Label / Item Code Extraction

Each output image is named after the item code on the price tag. The tool reads the code in this priority:

1. **Engine text response** — AI returns `LABEL: TP22/30` in its reply
2. **Gemma 4 OCR** — `gemma-4-31b-it` reads the tag image directly
3. **Fallback** — `AJ-{pair_number:03d}` (e.g. `AJ-003`)

Special characters (`/ \ : * ? " < > |`) are replaced with `_` for the filename:
- `TP22/30` → `TP22_30.jpg`

---

## Resume System

Progress is saved per category to `progress_{category}.json`:

```json
{
  "1": {"label": "TP22/30",  "output": "tops/TP22_30.jpg"},
  "2": {"label": "TP22/328", "output": "tops/TP22_328.jpg"},
  ...
}
```

**Key**: pair number (sequential integer, 1-indexed)
**Value**: label + relative output path

On batch start, any pair whose key exists in progress is **skipped immediately** without re-processing. Progress is only saved after BOTH studio shot AND model shot succeed.

To reprocess a pair: delete its entry from the JSON file.
To reprocess all: delete the entire `progress_{category}.json` file.

---

## Copilot Engine — Technical Details (`copilot_img.py`)

Copilot requires a live Chrome session because Microsoft's Auth0-based login blocks synthetic HTTP calls with a 403.

**Setup:**
- Chrome runs on port 9224 with `--remote-debugging-port=9224`
- Must be logged in to `copilot.microsoft.com` manually
- Profile stored at `C:\Users\kaila\AppData\Local\CopilotCatalogChrome`

**How it works per generation:**
1. GET `http://127.0.0.1:9224/json` → find the Copilot page tab + WebSocket URL
2. Connect WebSocket to Chrome DevTools Protocol (CDP)
3. `Page.navigate` → `https://copilot.microsoft.com/` (fresh conversation)
4. Wait 5 seconds for React to hydrate
5. Poll up to 80× (0.5s each = 40s max) for `input[type=file]` to appear
6. `DOM.setFileInputFiles` → uploads jewel.jpg + tag.jpg + background.jpg
7. `Runtime.evaluate` → type compositing prompt into textarea
8. `Runtime.evaluate` → click submit button
9. Monitor `Network.webSocketFrameReceived` events for `imageGenerated` payload
10. Download image URL → save to `output_copilot\`

**Rate limiting:**
- HTTP 429 on `/c/api/attachments` → sets 15-min cooldown in `copilot_cooldown.json`
- All subsequent calls check cooldown first and skip to Codex immediately
- Cooldown survives server restarts

**Critical CDP ordering note:**
`Page.navigate` MUST be called before `DOM.enable`/`Network.enable`. Sending `.enable` first on a tab with a stale CDP backlog hangs indefinitely.

---

## Codex Engine — Technical Details (`codex_img.py`)

Pure HTTP — no browser required.

**Auth:** reads `~/.codex/auth.json` (OAuth token from `npx @openai/codex login`)

**Token pool:** supports multiple ChatGPT Plus accounts:
- `~/.codex/auth.json` (account 1)
- `~/.codex/auth_2.json` (account 2)
- Up to `~/.codex/auth_10.json`

On 429 rate limit, auto-rotates to the next account.

**Endpoint:** `POST https://chatgpt.com/backend-api/codex/responses`

Sends 3 images (jewel + tag + background) as base64 with the compositing prompt. Receives a streaming SSE response; parses for the generated image.

---

## Gemini API Engine — Technical Details (`gemini_api_img.py`)

Pure HTTP — uses Google AI Studio free key.

**Key file:** `C:\Users\kaila\.gemini\api_key.txt`
**Also in:** `keys.py` as `GEMINI_API_KEY`

**Models tried in order:**
1. `gemini-2.0-flash-exp` — image input + image output (free, 15 RPM)
2. `gemini-2.0-flash-preview-image-generation` — alternate name
3. `gemini-2.0-flash` — text-only fallback (will fail image output)

**Free tier limits:**
- Flash: 15 RPM, 1500 req/day
- Imagen 3: 3 RPM, 150 req/day

---

## Duplicate Detection (`catalogue_db.py`)

The 30-day database (`catalogue_db.json`) catches:

| Situation | Alert |
|---|---|
| Same pixel hash + same tag | Exact duplicate — already processed on DATE |
| Same pixel hash + different tag | Same design, different tag — possible mislabel |
| Same tag + different hash | Tag reused on different design — data integrity issue |

Detection uses **perceptual hash (phash)** with a threshold of 12, confirmed by Gemma vision for borderline cases.

Entries auto-expire after 30 days.

---

## Jewellery Categories Supported

```
earrings       ladies_rings    gents_rings
ladies_chains  gents_chains    ladies_bracelet
gents_bracelet ladies_kada     gents_kada
locket         pendant         tops
wati           mangalsutra_short  mangalsutra_long
bangles        ladies_bali     mens_bali
necklace       silver          diamond
```

---

## Web UI (`templates/index.html`)

Single-page tool at `http://127.0.0.1:7654`

**Key API endpoints:**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/backgrounds` | GET | List available background files |
| `/api/load` | GET | List input images available |
| `/api/stage` | POST | Rename + move files to processing\ |
| `/api/copilot_run` | POST | Start Copilot-primary batch |
| `/api/chatgpt_run` | POST | Start ChatGPT conversation batch |
| `/api/codex_run` | POST | Start Codex-only batch |
| `/api/ps_run` | POST | Start Photoshop batch |
| `/api/chatgpt_progress` | GET | Poll batch status + results |
| `/api/ps_progress` | GET | Poll Photoshop batch status |
| `/api/stop` | POST | Stop running batch |
| `/api/model_images` | GET | List model reference images |
| `/api/reject` | POST | Mark an output as rejected |
| `/api/admin/reset_db` | POST | Wipe duplicate detection DB |
| `/api/auto_status` | GET | Auto-mode status |
| `/api/auto_config` | POST | Configure auto-mode |

---

## Authentication — What Needs to Be Logged In

| Service | How | Profile/File |
|---|---|---|
| Microsoft Copilot | Manual login in Chrome on port 9224 | `C:\Users\kaila\AppData\Local\CopilotCatalogChrome` |
| ChatGPT (Codex) | `npx @openai/codex login` | `~/.codex/auth.json` |
| ChatGPT (conversation) | Chrome on port 9222, logged in | `C:\Users\kaila\AppData\Local\AutoCatalogueChrome` |
| Gemini (browser) | Chrome on port 9223, logged in | `C:\Users\kaila\AppData\Local\GeminiCatalogChrome` |
| Gemini API | Key in `keys.py` + `~/.gemini/api_key.txt` | — |
| HuggingFace (RMBG) | Token in `keys.py` as `HF_TOKEN` | — |

---

## Gemma 4 — AI Used Internally

`gemma-4-31b-it` (via Gemini API) is used in two places:

1. **Tag reading** (`_gemma_read_tag`) — OCRs the price tag to extract item code
2. **Jewellery validation** (`_finalise_output` step 4) — confirms jewellery is present in the generated image

Both use the free Gemini API key from `keys.py`.

---

## File Naming Convention

```
Studio shot:  output_aradhana/{category}/{ItemCode}.jpg
              e.g.  output_aradhana/tops/TP22_30.jpg

Model shot:   output_aradhana/{category}/{ItemCode}_model.jpg
              e.g.  output_aradhana/tops/TP22_30_model.jpg
```

`/` in item codes is replaced with `_` in filenames.

---

## Key Config Files

| File | Purpose | Format |
|---|---|---|
| `progress_{cat}.json` | Resume checkpoint per category | `{"1": {"label":"TP22/30","output":"tops/TP22_30.jpg"}, ...}` |
| `catalogue_db.json` | 30-day duplicate DB | `{"entries": [{hash, tag, ts, path, ...}]}` |
| `copilot_cooldown.json` | Copilot rate-limit timer | `{"until": 1751650800.0}` |
| `keys.py` | API keys | Python constants |
| `port.txt` | Flask port | Plain text integer |
| `slot_log.json` | Multi-slot batch log | JSON array |

---

## YOLO Models

Two YOLO model files are present for object detection:
- `yolov8n.pt` — YOLOv8 nano (6.5 MB)
- `yolo26n.pt` — custom/newer variant (5.5 MB)

Used for jewellery detection in the validation pipeline.

---

## Common Operations

### Process a new tray of tops photos
```powershell
# 1. Copy tray files to input root
Copy-Item "C:\...\JewelleryCatalogTool\input\TRAY 1\*.JPG" "C:\...\JewelleryCatalogTool\input\"

# 2. Start the tool
# Double-click LAUNCH_CATALOG_UI.bat

# 3. In the UI: select "tops" category, choose background, click Run Copilot
```

### Restart a failed batch from scratch
```powershell
# Delete progress file
Remove-Item "C:\...\JewelleryCatalogTool\progress_tops.json" -ErrorAction SilentlyContinue
# Clear Copilot cooldown if active
Remove-Item "C:\...\JewelleryCatalogTool\copilot_cooldown.json" -ErrorAction SilentlyContinue
# Then restart the server via LAUNCH_CATALOG_UI.bat and re-run
```

### Reprocess specific pairs (e.g. pairs 3 and 5)
Edit `progress_tops.json` and delete entries for keys `"3"` and `"5"`.

### Check batch progress via API
```powershell
Invoke-WebRequest "http://127.0.0.1:7654/api/chatgpt_progress" | ConvertFrom-Json
```

### Trigger batch via API (bypasses UI)
```powershell
$body = '{"pairs":[{"pair":1}],"category":"tops","bg":""}'
Invoke-WebRequest "http://127.0.0.1:7654/api/copilot_run" -Method POST -Body $body -ContentType "application/json"
```

---

## Current Batch Status (as of session — July 2026)

**Category: tops — 14 pairs — COMPLETE**

| Pair | Item Code | Studio | Model |
|---|---|---|---|
| 1 | TP22/30 | ✅ | ✅ |
| 2 | TP22/328 | ✅ | ✅ |
| 3 | TP22/322 | ✅ | ✅ |
| 4 | TP22/317 | ✅ | ✅ |
| 5 | TP22/332 | ✅ | ✅ |
| 6 | TP22/251 | ✅ | ✅ |
| 7 | TP22/249 | ✅ | ✅ |
| 8 | TP22/312 | ✅ | ✅ |
| 9 | TP22/197 | ✅ | ✅ |
| 10 | TP18/8 | ✅ | ✅ |
| 11 | TP22/78 | ✅ | ✅ |
| 12 | TP22/131 | ✅ | ✅ |
| 13 | TP22/106 | ✅ | ✅ |
| 14 | TP22/333 | ✅ | ✅ |

All 28 files in `output_aradhana\tops\`.

---

## Known Issues & Fixes Applied

| Issue | Fix |
|---|---|
| Copilot file input not found (2.5s sleep too short) | Increased to 5s + 80 polls × 0.5s = 45s total wait |
| DOM.getDocument called once with stale root | Now refreshed each poll iteration |
| Progress stored relative path (`tops/x.jpg`) but existence check used absolute | Check uses pair key presence only (not file existence) |
| WinError32 — PIL holds file handle during os.replace | Wrapped PIL open in `with` block |
| `json.load(p.open())` broke after path became string | Fixed to `with open(p) as f: json.load(f)` |
| TRAY 1 files not found by `_derive_pairs_from_disk` | Copy tray files to input root before running |
| Copilot rate limit (429) blocks all pairs | 15-min cooldown persisted; auto-fallback to Codex |

"""
capture_tool.py — the phone/tablet capture workflow: a staff member picks an
ornament category, then repeatedly shoots a front jewellery photo, an
optional studs photo, a close-up detail photo, and a tag photo.
The tag photo's barcode/QR is decoded CLIENT-SIDE in the browser (see
capture.html) — this module just receives the already-decoded code string
alongside the two images.

Kept as its own module rather than growing app.py further, matching the
pattern already used for engine_cascade.py / verification.py.

SAVE FORMAT: the front jewellery photo is kept as the primary deliverable,
named directly from the confirmed tag code (e.g. tag "JB22/8" -> file
"JB22_8.jpg" — "/" isn't legal in a Windows filename, so it's replaced with
"_", matching the same substitution the main catalogue pipeline already uses
when turning a resolved SKU into a filename, see engine_cascade.py's
`re.sub(r'[/\\:*?"<>|]', "_", fin["sku"])`). Optional studs and detail
close-ups are stored as sidecar images beside it, using the same stem with
suffixes. The tag photo is used only to read the code; its decoded data is
stamped into the saved front image metadata, and the raw tag shot is not kept
as a separate archive.

Since filenames are no longer sequential, "which item was captured most
recently" (needed for Undo) is tracked via each dedup entry's timestamp
instead of a pair number.

Dedup today is SESSION/LIFETIME scoped (has this exact barcode value ever
been captured by this tool before) via capture_dedup.json — a full cross-
reference against the entire Ornate stock export requires the master Excel
schema and drop-folder path, which aren't available yet. That step is a
clearly-marked TODO (see check_master_stock) rather than silently skipped.
"""
import os
import re
import time
import json
import threading
import functools

import cv2
import numpy as np

import capture_voids
import sam_locate

BASE = os.path.dirname(os.path.abspath(__file__))
CAPTURE_ROOT = os.path.join(BASE, "capture_intake")
DEDUP_PATH = os.path.join(BASE, "data", "capture_dedup.json")
VOID_REGISTRY_PATH = str(capture_voids.configured_void_registry_path())
TAG_ARCHIVE_DIRNAME = "_tag_archive"

# Laplacian-variance focus check on the jewellery photo — same technique
# used elsewhere for image-quality gating (see model_postprocess.py's edge
# detection), just applied here to catch an out-of-focus phone shot before
# it's saved as the deliverable rather than after generation. The image is
# downscaled to a fixed max dimension first because Laplacian variance scales
# with resolution — without that, a sharp 4032x3024 phone photo and a blurry
# one at the same resolution aren't comparable against one fixed threshold.
# Threshold picked conservatively (favors false "looks blurry" warnings,
# which just cost one confirm tap, over false negatives that let a genuinely
# blurry catalogue photo through) — tune BLUR_VARIANCE_THRESHOLD up/down if
# the team finds it's too trigger-happy or too lax in real use.
BLUR_MAX_DIM = 1000
BLUR_VARIANCE_THRESHOLD = 60.0


def _stock_write_guard(function):
    """Serialize capture mutations against daily stock reconciliation."""
    @functools.wraps(function)
    def guarded(*args, **kwargs):
        import stock_reconciliation
        with stock_reconciliation.data_lock():
            return function(*args, **kwargs)
    return guarded


def _embed_tag_metadata(jpeg_path: str, *, tag_code: str, category: str, staff_name: str) -> None:
    """Best-effort metadata stamp for the saved front image.

    Uses a JPEG comment marker so the image is not re-encoded.
    """
    try:
        payload = {
            "tag_code": str(tag_code),
            "category": str(category),
            "staff": str(staff_name or ""),
            "embedded_at": time.time(),
        }
        comment = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(comment) > 65533:
            return
        with open(jpeg_path, "rb") as source:
            data = source.read()
        if not data.startswith(b"\xff\xd8"):
            return
        segment = b"\xff\xfe" + (len(comment) + 2).to_bytes(2, "big") + comment
        temporary = f"{jpeg_path}.meta.tmp"
        with open(temporary, "wb") as output:
            output.write(data[:2])
            output.write(segment)
            output.write(data[2:])
        os.replace(temporary, jpeg_path)
    except Exception:
        pass


def _jewellery_clearly_visible(image_bytes: bytes) -> dict:
    """Local gold-presence gate. No cloud model, account, or network call."""
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            return {"ok": True, "reason": "Local check unavailable: image could not be decoded", "unverified": True}
        image = cv2.resize(image, (640, max(1, int(image.shape[0] * 640 / image.shape[1]))))
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        gold = cv2.inRange(hsv, np.array([8, 65, 45]), np.array([38, 255, 255]))
        gold = cv2.morphologyEx(gold, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(gold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        largest = max((cv2.contourArea(c) for c in contours), default=0.0)
        ratio = largest / float(image.shape[0] * image.shape[1])
        ok = ratio >= 0.002
        reason = f"Local gold region {ratio:.2%} of frame"
        return {"ok": ok, "reason": reason, "unverified": False}
    except Exception as e:
        return {"ok": True, "reason": f"Local check unavailable: {type(e).__name__}: {e}", "unverified": True}


def _blur_variance(image_bytes: bytes):
    """Returns the Laplacian variance of the image (lower = blurrier), or
    None if the bytes couldn't be decoded as an image — decode failures fail
    OPEN (no blur warning) since save_pair separately validates the file is
    a real image; this is purely a quality signal, not a correctness gate."""
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        h, w = img.shape[:2]
        scale = min(1.0, BLUR_MAX_DIM / max(h, w))
        if scale < 1.0:
            img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))))
        return float(cv2.Laplacian(img, cv2.CV_64F).var())
    except Exception:
        return None

os.makedirs(CAPTURE_ROOT, exist_ok=True)

_lock = threading.RLock()


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _load_dedup() -> dict:
    if os.path.exists(DEDUP_PATH):
        try:
            with open(DEDUP_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# The 57 real stock categories from \\Server2k22\D\01082026.xls (2814 real
# tags, verified 2026-08-01 with zero mismatches against every real Label No
# in that report — see ornament_code_map.py). Supersedes the earlier
# 47-category stock_category_map.py list (a prior, less complete sheet);
# capture itself never touches backgrounds/model assets, so all 57 are
# immediately usable for accurate tagging regardless of processing readiness.
import ornament_code_map as _ocm

CATEGORY_LABELS = {c.key: c.label for c in _ocm.CATEGORIES}
CATEGORY_LABELS.update({
    # Not covered by the new sheet at all — a different concern (metal type,
    # not ornament category) — kept as-is.
    "silver": "Silver",
    "diamond": "Diamond",
    "test": "Test (practice — not real stock)",
})

# A dedicated practice category — deliberately NOT part of app.py's TYPES
# list (which also drives the main catalogue tool's own category dropdown;
# adding "test" there would surface it in real production processing, which
# has no matching templates/backgrounds for it). Capture-only, added
# separately by the /capture route. Every save under this category lands in
# the SAME single fixed folder, never tray-numbered like real categories —
# "Start new tray" is a no-op here — so staff can freely try the capture
# flow (testing the read-status overlay, camera framing, etc.) without ever
# creating "Test 1", "Test 2"... clutter or touching real stock folders.
TEST_CATEGORY = "test"
TEST_FOLDER_NAME = "_TEST"


def category_list(types: list) -> list:
    return [{"value": t, "label": CATEGORY_LABELS.get(t, t.replace("_", " ").title())} for t in types]


MASTER_STOCK_DIR = os.path.join(BASE, "Stock")

# Filename is DDMMYYYY.xls, a fresh drop each day (confirmed with the user
# 2026-08-02: "C:\...\Stock\01082026.xls") — never hardcode a specific day's
# filename, always resolve to whichever one is actually newest on disk.
_STOCK_FILENAME_RE = re.compile(r"^(\d{2})(\d{2})(\d{4})\.xls$", re.IGNORECASE)

_master_stock_lock = threading.Lock()
_master_stock_cache = {"path": None, "mtime": None, "labels": {}}


def _latest_stock_file() -> str | None:
    """Newest DDMMYYYY.xls in MASTER_STOCK_DIR by the date encoded in its own
    filename (not just mtime — a re-copied older file would otherwise win)."""
    if not os.path.isdir(MASTER_STOCK_DIR):
        return None
    best_path, best_date = None, None
    for fn in os.listdir(MASTER_STOCK_DIR):
        m = _STOCK_FILENAME_RE.match(fn)
        if not m:
            continue
        dd, mm, yyyy = m.groups()
        try:
            date_key = (int(yyyy), int(mm), int(dd))
        except ValueError:
            continue
        if best_date is None or date_key > best_date:
            best_date, best_path = date_key, os.path.join(MASTER_STOCK_DIR, fn)
    return best_path


_STOCK_SECTION_TITLE_RE = re.compile(
    r"Label/Tags Closing Stock Report\s*\(([^)]+)\)", re.IGNORECASE
)


_STOCK_HEADER_COLS = ("Label No", "Old BarcodeNo", "Prefix", "Carat", "Variety Name",
                      "Gross Wt", "Net Wt", "Pcs", "HUID")


def _parse_master_stock(path: str) -> dict:
    """Parse the "Label/Tags Closing Stock Report" export. The category name
    is NOT always a per-row column — it appears in a title row
    ("Label/Tags Closing Stock Report (BABY BRACLET 22) As On Date : ...")
    that precedes each category's block, followed by that section's own
    repeated header row. Two schemas have been seen from this daily export
    (confirmed with the user 2026-08-02 — the reduced one arrived on
    01/08, the full one on 31/07; which shows up on a given day isn't
    predictable), so the header row itself is used to detect column layout
    rather than assuming a fixed position:
      - Full: Label No | Old BarcodeNo | Prefix | Carat | Variety Name |
        Gross Wt | Net Wt | Pcs | HUID
      - Reduced: ItemName | Label No  (only these two fields)
    The sheet ends with a totals row (blank Label No, numeric sums) that
    must be skipped, not mistaken for a stock item.
    Returns {label_no: {item_name, old_barcode, prefix, carat, variety,
    gross_wt, net_wt, pcs, huid}} — fields absent in the reduced schema are
    None rather than missing, so callers don't need to branch on schema."""
    import pandas as pd
    df = pd.read_excel(path, engine="xlrd", header=None)
    labels = {}
    current_category = None
    label_col, item_col = None, None  # column layout for the CURRENT header row
    for _, row in df.iterrows():
        col0 = row.get(0)
        if isinstance(col0, str):
            m = _STOCK_SECTION_TITLE_RE.search(col0)
            if m:
                current_category = m.group(1).strip()
                continue
            cells = [str(row.get(i)).strip() if row.get(i) is not None else ""
                     for i in range(len(row))]
            if "Label No" in cells:
                label_col = cells.index("Label No")
                item_col = cells.index("ItemName") if "ItemName" in cells else None
                continue  # this row IS the header, not data

        if label_col is None:
            continue  # haven't seen a header row yet — nothing to parse against
        label_no = row.get(label_col)
        label_no = label_no.strip() if isinstance(label_no, str) else None
        if not label_no or "/" not in label_no:
            continue  # blank/title/totals row — a real Label No always has a "/"

        if item_col is None:
            # Full schema: Label No is column 0, the rest follow in order.
            labels[label_no] = {
                "item_name": current_category,
                "old_barcode": row.get(1),
                "prefix": row.get(2),
                "carat": row.get(3),
                "variety": row.get(4),
                "gross_wt": row.get(5),
                "net_wt": row.get(6),
                "pcs": row.get(7),
                "huid": row.get(8),
            }
        else:
            # Reduced schema: only ItemName + Label No are present.
            item_name = row.get(item_col)
            item_name = item_name.strip() if isinstance(item_name, str) else current_category
            labels[label_no] = {
                "item_name": item_name, "old_barcode": None, "prefix": None,
                "carat": None, "variety": None, "gross_wt": None, "net_wt": None,
                "pcs": None, "huid": None,
            }
    return labels


def _load_master_stock_labels() -> dict:
    """Lazy, cached by (path, mtime) — re-parses only when a newer day's file
    has actually appeared, not on every single capture."""
    path = _latest_stock_file()
    if not path:
        return {}
    mtime = os.path.getmtime(path)
    with _master_stock_lock:
        if _master_stock_cache["path"] == path and _master_stock_cache["mtime"] == mtime:
            return _master_stock_cache["labels"]
        labels = _parse_master_stock(path)
        _master_stock_cache.update(path=path, mtime=mtime, labels=labels)
        return labels


def check_master_stock(tag_code: str) -> dict:
    """
    Cross-reference tag_code against the master Ornate stock Excel (dropped
    daily into `Stock/`, see _latest_stock_file). Confirms the scanned tag
    corresponds to a real, currently-listed stock item and surfaces its
    catalogued item name for a second confirmation on the capture screen.

    Returns {"known": bool, "row": dict|None}. Fails open (known=False,
    row=None) on any read/parse error — a malformed or missing daily export
    must never block a live capture session, only skip this extra check.
    """
    try:
        labels = _load_master_stock_labels()
    except Exception:
        return {"known": False, "row": None}
    row = labels.get(tag_code)
    if row is None:
        return {"known": False, "row": None}
    return {"known": True, "row": {"label_no": tag_code, **row}}


TRAY_STATE_PATH = os.path.join(BASE, "data", "capture_current_tray.json")


def _load_tray_state() -> dict:
    if os.path.exists(TRAY_STATE_PATH):
        try:
            with open(TRAY_STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_tray_state(state: dict):
    _atomic_write_json(TRAY_STATE_PATH, state)


_GLOBAL_TRAY_NUMBER_RE = re.compile(r"^(\d+)\s+\S.*$")


def _tray_folder_name(category: str, n: int) -> str:
    """'<N> <Label>' — number first, GLOBAL across every category, e.g.
    '33 Ladies Rings'. Changed 2026-07-31 alongside the one-time global
    renumbering (tray_sequence_migration.py) from the old '<Label> <N>'
    per-category form: numbering used to restart at 1 for every category
    independently, so folder #47 told you nothing about capture order
    across categories. See _next_tray_number for the matching read side."""
    label = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
    return f"{n} {label}"


def _next_tray_number() -> int:
    """GLOBAL, category-agnostic sequence: the next number is the highest
    leading number across EVERY capture folder (any category) plus one, so
    the sequence never resets just because a different category starts its
    next tray — "1 ornament may have multiple folders based on capture
    order but the number sequence never breaks" was the explicit
    requirement. Deliberately takes no category argument any more: the
    whole point is that the counter no longer belongs to one category.

    A folder that doesn't match "<digits> <space> ..." (e.g. the fixed
    '_TEST' practice folder) is ignored, not treated as 0 — it was never
    part of any sequence.

    Also considers every number already reserved in tray state, not just
    what's materialized on disk — a tray is assigned to a category the
    moment it becomes "current," but its folder is deliberately not created
    until the first real capture (see start_new_tray). Two categories can
    both be sitting on an uncaptured tray at once, and without this, both
    would compute the same "next" number from disk (since neither folder
    exists yet) and collide the moment either one is finally captured
    into."""
    nums = []
    if os.path.isdir(CAPTURE_ROOT):
        for name in os.listdir(CAPTURE_ROOT):
            match = _GLOBAL_TRAY_NUMBER_RE.match(name)
            if match:
                nums.append(int(match.group(1)))
    for folder in _load_tray_state().values():
        match = _GLOBAL_TRAY_NUMBER_RE.match(folder or "")
        if match:
            nums.append(int(match.group(1)))
    return (max(nums) + 1) if nums else 1


def start_new_tray(category: str) -> dict:
    """Allocates a brand-new tray folder NAME for this category and makes
    it the 'current tray' every subsequent save for this category lands
    in — until the next start_new_tray call.

    Deliberately does NOT create the folder on disk. A folder that exists
    with nothing captured in it is indistinguishable from a real, useful
    tray to every downstream consumer (the capture-memory admin list, Auto
    Mode, dashboards) — it was showing up as clutter the moment a category
    was merely selected or an empty tray was Forgotten and immediately
    reappeared. The one and only place a tray folder is created is
    save_pair, at the moment a real item is actually captured into it
    (see its os.makedirs call there).

    For TEST_CATEGORY this is a no-op that always resolves to the same
    fixed folder — practice captures never get their own numbered tray."""
    with _lock:
        if category == TEST_CATEGORY:
            state = _load_tray_state()
            state[category] = TEST_FOLDER_NAME
            _save_tray_state(state)
            return {"folder": TEST_FOLDER_NAME, "tray_number": None}

        n = _next_tray_number()
        folder = _tray_folder_name(category, n)
        state = _load_tray_state()
        state[category] = folder
        _save_tray_state(state)
        return {"folder": folder, "tray_number": n}


def get_current_tray(category: str) -> dict:
    """The tray currently being filled for this category — auto-assigns
    tray #1 the first time a category is ever used, so staff don't have to
    remember to click 'Start new tray' before their very first item.

    Trusts the recorded assignment regardless of whether its folder has
    been created on disk yet — it may not have been, since start_new_tray
    no longer creates it eagerly. A category keeps its assigned tray until
    something explicitly reassigns it (a real start_new_tray call, or
    _advance_active_trays after that folder is Forgotten); merely being
    unmaterialized is not a reason to hand out a new one."""
    if category == TEST_CATEGORY:
        state = _load_tray_state()
        if state.get(category):
            return {"folder": state[category], "tray_number": None}
        return start_new_tray(category)  # always the same fixed folder

    state = _load_tray_state()
    folder = state.get(category)
    if folder:
        # Folders are "<N> <Label>" (leading number, global sequence) since
        # the 2026-07-31 renumbering — a TRAILING-number match here was a
        # leftover from the old "<Label> <N>" scheme and silently returned
        # tray_number=None for every real tray ever since.
        m = _GLOBAL_TRAY_NUMBER_RE.match(folder)
        return {"folder": folder, "tray_number": int(m.group(1)) if m else None}
    return start_new_tray(category)


def _safe_filename_from_tag(tag_code: str) -> str:
    """'JB22/8' -> 'JB22_8' — matches the same "/" -> "_" substitution the
    main catalogue pipeline already uses for resolved SKUs, so filenames
    stay consistent across both tools."""
    return re.sub(r'[/\\:*?"<>|]', "_", tag_code).strip() or "untitled"


DEDUP_SETTINGS_PATH = os.path.join(BASE, "data", "capture_dedup_settings.json")


def dedup_enabled() -> bool:
    """Master switch for duplicate blocking.

    When OFF, captures are still RECORDED (so history and per-folder clearing
    keep working) but a prior record never blocks a new capture. This is for
    deliberate re-shoots of an existing tray, where every single item would
    otherwise raise "already captured" and need individual overriding.
    Defaults to ON — silently not checking for duplicates is a worse failure
    than being asked to confirm one.
    """
    try:
        if os.path.exists(DEDUP_SETTINGS_PATH):
            with open(DEDUP_SETTINGS_PATH, encoding="utf-8") as f:
                return bool(json.load(f).get("enabled", True))
    except Exception:
        pass
    return True


def set_dedup_enabled(enabled: bool) -> bool:
    with _lock:
        _atomic_write_json(DEDUP_SETTINGS_PATH, {"enabled": bool(enabled),
                                                 "updated": time.time()})
    return bool(enabled)


def dedup_folders() -> list:
    """Folders present in the dedup memory, with record counts.

    Deliberately sourced from the dedup store rather than from disk: a tray
    can be deleted off disk while its records linger, and that is exactly the
    case where "already captured" blocks a re-shoot of something that is no
    longer there. Listing from disk would make those folders unclearable.
    """
    counts = {}
    for rec in _load_dedup().values():
        if isinstance(rec, dict):
            f = rec.get("folder") or "(unknown)"
            counts[f] = counts.get(f, 0) + 1
    return sorted(({"folder": k, "records": v} for k, v in counts.items()),
                  key=lambda r: r["folder"].lower())


@_stock_write_guard
def clear_folder_memory(folder: str) -> dict:
    """Forget every dedup record belonging to `folder` so its items can be
    captured again.

    Records only — images on disk are untouched. Forgetting and deleting are
    separate decisions, and conflating them would make a routine "let me
    re-shoot this tray" quietly destroy the existing photos.
    """
    if not folder:
        return {"ok": False, "error": "no folder given", "removed": 0}
    with _lock:
        dedup = _load_dedup()
        drop = [k for k, v in dedup.items()
                if isinstance(v, dict) and (v.get("folder") or "(unknown)") == folder]
        for k in drop:
            del dedup[k]
        if drop:
            _atomic_write_json(DEDUP_PATH, dedup)
    return {"ok": True, "folder": folder, "removed": len(drop),
            "remaining": len(dedup)}


def check_duplicate(tag_code: str) -> dict | None:
    """Returns the prior capture record if tag_code was already captured
    before (by anyone, any session), else None.

    Returns None when the master switch is off, so callers that treat a
    non-None result as "block this capture" stop blocking without needing to
    know the switch exists.
    """
    if not tag_code or not dedup_enabled():
        return None
    dedup = _load_dedup()
    prior = dedup.get(tag_code)
    if not isinstance(prior, dict):
        return prior
    folder = prior.get("folder")
    filename = prior.get("filename")
    if folder and filename:
        try:
            if capture_voids.is_voided(
                os.path.join(folder, filename), VOID_REGISTRY_PATH
            ):
                return None
        except capture_voids.VoidRegistryError:
            # Duplicate blocking fails closed.  Pipeline intake also refuses
            # to run while registry status is unknown.
            return prior
    return prior


def _segment_jewel_async(jewel_path: str) -> None:
    """Replace the saved jewel photo in-place with a SAM2/DINO segmentation
    crop, off the request thread.

    This runs after save_pair() has already written the file and is about to
    return its response to the phone -- segmentation is real GPU inference
    (SAM2-large + Grounding DINO) and the save confirmation shouldn't wait on
    it. tight_crop() is already fail-open (returns the original path
    untouched on any error), so a slow/missing model never blocks a capture,
    it just leaves the digital fill-crop from capture.html as the final
    result for that piece.
    """
    if not sam_locate.available():
        logging.getLogger("capture_tool").warning(
            "sam_locate.available() is False -- skipping segmentation for %s", jewel_path
        )
        return

    def _run():
        log = logging.getLogger("capture_tool")
        try:
            result_path, angle = sam_locate.tight_crop(jewel_path, jewel_path, expect=1, straighten=True)
            log.info("sam_locate.tight_crop done for %s (angle=%s)", jewel_path, angle)
        except Exception:
            log.exception("sam_locate.tight_crop FAILED for %s", jewel_path)
        finally:
            sam_locate.release()

    threading.Thread(target=_run, daemon=True).start()


@_stock_write_guard
def save_pair(category: str, jewel_bytes: bytes, tag_bytes: bytes, tag_code: str,
             staff_name: str = "", override_duplicate: bool = False,
             override_blur: bool = False, override_visibility: bool = False) -> dict:
    """
    Persist one item into the CURRENT tray for this category (auto-creates
    tray #1 if none started yet). The jewellery photo (auto-captured, zoomed
    to fill the frame) is saved into the tray as the primary deliverable,
    named directly from tag_code (see _safe_filename_from_tag) — no sequence
    numbers. The tag photo is used only to read the code; its decoded data is
    stamped into the saved jewellery image metadata and the raw tag shot is
    not archived separately. Returns:
      {"ok": True, "folder": ..., "tray_number": N, "filename": ..., "tray_captured": N,
       "blur_score": float|None}
      or {"ok": False, "error": "duplicate", "prior": {...}} if tag_code was
      already captured and override_duplicate is False, or
      {"ok": False, "error": "blurry", "blur_score": float} if the jewellery
      photo looks out of focus (see _blur_variance) and override_blur is False, or
      {"ok": False, "error": "not_clearly_visible", "reason": str} if the
      "jewel" photo doesn't clearly show the jewellery (see
      _jewellery_clearly_visible) and override_visibility is False.
    """
    with _lock:
        is_test = category == TEST_CATEGORY
        if not is_test and not override_duplicate:
            prior = check_duplicate(tag_code)
            if prior:
                return {"ok": False, "error": "duplicate", "prior": prior}

        blur_score = _blur_variance(jewel_bytes)
        if not override_blur and blur_score is not None and blur_score < BLUR_VARIANCE_THRESHOLD:
            return {"ok": False, "error": "blurry", "blur_score": round(blur_score, 1)}

        if not override_visibility:
            vis = _jewellery_clearly_visible(jewel_bytes)
            if not vis["ok"]:
                return {"ok": False, "error": "not_clearly_visible", "reason": vis["reason"],
                        "unverified": vis["unverified"]}

        tray = get_current_tray(category)
        tray_dir = os.path.join(CAPTURE_ROOT, tray["folder"])
        # Tray allocation is deliberately lazy. The first real capture is the
        # operation that materialises the directory; without this, a newly
        # assigned tray failed on its first image with FileNotFoundError.
        os.makedirs(tray_dir, exist_ok=True)

        safe_name = _safe_filename_from_tag(tag_code) if tag_code else f"untagged_{int(time.time())}"
        jewel_path = os.path.join(tray_dir, f"{safe_name}.jpg")
        # Guard against silently overwriting a different piece — happens if
        # the same code is deliberately re-saved via override_duplicate, or
        # (rarer) two untagged captures land in the same second.
        n = 2
        base_safe_name = safe_name
        while os.path.exists(jewel_path):
            safe_name = f"{base_safe_name}_{n}"
            jewel_path = os.path.join(tray_dir, f"{safe_name}.jpg")
            n += 1

        with open(jewel_path, "wb") as f:
            f.write(jewel_bytes)
        _embed_tag_metadata(jewel_path, tag_code=tag_code, category=category, staff_name=staff_name)
        _segment_jewel_async(jewel_path)

        # Test captures never touch the global dedup file — recording them
        # there would risk a practice tag code later blocking (or being
        # blocked by) an unrelated real production capture that happens to
        # reuse the same code.
        if tag_code and not is_test:
            dedup = _load_dedup()
            dedup[tag_code] = {
                "folder": tray["folder"], "filename": f"{safe_name}.jpg",
                "category": category, "staff": staff_name, "ts": time.time(),
            }
            _atomic_write_json(DEDUP_PATH, dedup)

        tray_captured = _count_tray_items(tray_dir)
        return {"ok": True, "folder": tray["folder"], "tray_number": tray["tray_number"],
               "filename": f"{safe_name}.jpg", "tray_captured": tray_captured,
               "blur_score": round(blur_score, 1) if blur_score is not None else None,
               # kept for backward-compat with the current capture.html JS
               "session_captured": tray_captured}


def _count_tray_items(tray_dir: str) -> int:
    if not os.path.isdir(tray_dir):
        return 0
    sidecar_suffixes = ("_studs.jpg", "_detail.jpg", "_tag.jpg")
    return len([
        f for f in os.listdir(tray_dir)
        if f.lower().endswith(".jpg")
        and not f.lower().endswith(sidecar_suffixes)
        and os.path.isfile(os.path.join(tray_dir, f))
    ])


def session_summary(category: str) -> dict:
    """Current tray's folder name, number, and how many items are in it so
    far — the live 'Tray N · X captured' display on the capture screen."""
    tray = get_current_tray(category)
    tray_dir = os.path.join(CAPTURE_ROOT, tray["folder"])
    return {"captured": _count_tray_items(tray_dir), "folder": tray["folder"], "tray_number": tray["tray_number"]}


def tray_items(folder: str) -> list:
    """Every tag code captured so far in a given tray folder, oldest first —
    the source of truth for the capture screen's live list (reads real
    server state, not just this browser tab's in-memory session, so a page
    reload or a second device on the same tray sees the same list)."""
    dedup = _load_dedup()
    items = [(rec.get("ts", 0), code) for code, rec in dedup.items() if rec.get("folder") == folder]
    items.sort()
    return [{"pair": i + 1, "code": code} for i, (_, code) in enumerate(items)]


def find_item(tag_code: str) -> dict | None:
    """Look up a single captured item by its exact tag code, for the search
    UI that replaced whole-folder Forget — review one specific item before
    deciding to delete it, rather than an entire tray's history at once."""
    dedup = _load_dedup()
    rec = dedup.get(tag_code)
    if not isinstance(rec, dict):
        return None
    folder = rec.get("folder")
    filename = rec.get("filename")
    if not folder or not filename:
        return None
    jewel_path = os.path.join(CAPTURE_ROOT, folder, filename)
    stem = os.path.splitext(filename)[0]
    studs_path = os.path.join(CAPTURE_ROOT, folder, f"{stem}_studs.jpg")
    detail_path = os.path.join(CAPTURE_ROOT, folder, f"{stem}_detail.jpg")
    return {
        "tag_code": tag_code,
        "folder": folder,
        "filename": filename,
        "category": rec.get("category"),
        "staff": rec.get("staff"),
        "ts": rec.get("ts"),
        "jewel_exists": os.path.isfile(jewel_path),
        "studs_exists": os.path.isfile(studs_path),
        "detail_exists": os.path.isfile(detail_path),
        "tag_exists": False,
        "tag_embedded": True,
    }


@_stock_write_guard
def delete_item(tag_code: str) -> dict:
    """Permanently delete ONE captured item's images and
    remove its dedup record — scoped to exactly this tag, unlike the old
    whole-folder Forget. Resets duplicate-blocking for this specific tag
    only; every other item in the same folder is untouched."""
    with _lock:
        item = find_item(tag_code)
        if item is None:
            return {"ok": False, "error": f"no captured item found for tag {tag_code!r}"}

        jewel_path = os.path.join(CAPTURE_ROOT, item["folder"], item["filename"])
        stem = os.path.splitext(item["filename"])[0]

        deleted = []
        sidecar_paths = (
            os.path.join(CAPTURE_ROOT, item["folder"], f"{stem}_studs.jpg"),
            os.path.join(CAPTURE_ROOT, item["folder"], f"{stem}_detail.jpg"),
        )
        for path in (jewel_path, *sidecar_paths):
            try:
                os.remove(path)
                deleted.append(path)
            except FileNotFoundError:
                pass

        dedup = _load_dedup()
        dedup.pop(tag_code, None)
        _atomic_write_json(DEDUP_PATH, dedup)

        return {"ok": True, "tag_code": tag_code, "folder": item["folder"], "deleted_files": len(deleted)}


@_stock_write_guard
def undo_last(category: str) -> dict:
    """Void the most-recent capture while preserving the complete raw pair.

    Undo used to delete the jewellery and archived tag files.  The capture
    tree is now an immutable master, so Undo atomically records a tombstone
    and removes only the duplicate-blocking record.  A deliberate recapture
    receives a new non-overwriting filename and the old bytes remain intact.

    Filenames aren't sequential anymore (they're named from the tag code),
    so 'most recent' is determined by each dedup entry's timestamp rather
    than a pair number. The fast capture flow auto-saves on a clean barcode
    read with no manual review step, so this is the safety net for 'wrong
    item went through' — one tap to remove it and immediately try again."""
    with _lock:
        tray = get_current_tray(category)
        tray_dir = os.path.join(CAPTURE_ROOT, tray["folder"])
        if not os.path.isdir(tray_dir):
            return {"ok": False, "error": "no tray to undo"}

        dedup = _load_dedup()
        candidates = [(rec.get("ts", 0), code, rec) for code, rec in dedup.items()
                     if rec.get("folder") == tray["folder"]]
        if not candidates:
            return {"ok": False, "error": "nothing to undo"}
        candidates.sort()
        _, removed_code, rec = candidates[-1]

        filename = rec.get("filename")
        if not filename or os.path.basename(filename) != filename:
            return {"ok": False, "error": "capture history has an unsafe filename"}
        safe_stem = os.path.splitext(filename)[0]
        jewel_path = os.path.join(tray_dir, filename)
        studs_path = os.path.join(tray_dir, f"{safe_stem}_studs.jpg")
        detail_path = os.path.join(tray_dir, f"{safe_stem}_detail.jpg")
        if not os.path.isfile(jewel_path):
            return {
                "ok": False,
                "error": "raw capture bundle is incomplete; nothing was voided",
                "preserved": True,
            }

        primary_relative = os.path.join(tray["folder"], filename)
        primary_size = os.path.getsize(jewel_path)
        sidecar_sizes = 0
        sidecar_files = 0
        for sidecar in (studs_path, detail_path):
            if os.path.isfile(sidecar):
                sidecar_files += 1
                sidecar_sizes += os.path.getsize(sidecar)
        tombstone = capture_voids.record_void(
            primary_path=primary_relative,
            tag_path=os.path.join(tray["folder"], TAG_ARCHIVE_DIRNAME, f"{safe_stem}_tag.jpg"),
            tag_code=removed_code,
            category=category,
            folder=tray["folder"],
            primary_size=primary_size,
            tag_size=0,
            registry_path=VOID_REGISTRY_PATH,
        )

        del dedup[removed_code]
        _atomic_write_json(DEDUP_PATH, dedup)

        return {
            "ok": True,
            "action": "voided",
            "voided": True,
            "removed_code": removed_code,
            "voided_primary_path": tombstone["primary_path"],
            "voided_tag_path": tombstone["tag_path"],
            "preserved": True,
            "preserved_files": 1 + sidecar_files,
            "preserved_bytes": primary_size + sidecar_sizes,
            "dedup_removed": True,
        }


def all_sessions_summary() -> list:
    """Every capture session folder that exists, newest first — the basis
    for the 'captured vs pending' real-time view."""
    if not os.path.isdir(CAPTURE_ROOT):
        return []
    rows = []
    for name in os.listdir(CAPTURE_ROOT):
        path = os.path.join(CAPTURE_ROOT, name)
        if not os.path.isdir(path):
            continue
        rows.append({"folder": name, "captured": _count_tray_items(path), "mtime": os.path.getmtime(path)})
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows

"""
review_queue.py — post-run review: every item, not just the ones that passed.

WHY
---
A batch currently ends with three piles and no way to see them together:
images in output/, failures in needs_review/, and errors that only ever
existed as a line in a log. Nobody looks at the passes, so a mismatched pair
ships; nobody revisits the failures, so JB22_8 and JB22_10 failed identically
on three consecutive runs without anyone deciding what to do about them.

So review covers the whole batch. Passed, flagged and errored items all land
in one queue, each shown against its ORIGINAL photograph, because design
fidelity is the one thing no automated check can settle — the gates can count
pieces and measure agreement, they cannot tell you it is the right jhumka.

A folder is not "done" when every item has been processed. It is done when
every item has been processed AND a human has approved it. Those are
different states and the dashboard should not conflate them.

Originals come from capture_intake/, the master archive, never from input/ —
the runner moves input files into processing/ as it consumes them, so by the
end of a batch input/ is half empty and useless as a source of truth.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
CAPTURE_INTAKE = os.path.join(BASE, "capture_intake")
PROCESSED_DIR = os.path.join(BASE, "processed")
REJECTED_DIR = os.path.join(BASE, "rejected")
REJECTED_MANIFEST = os.path.join(REJECTED_DIR, "REJECT_REASONS.txt")
OUTPUT_DIR = os.path.join(BASE, "output")
NEEDS_REVIEW = os.path.join(BASE, "needs_review")
INPUT_DIR = os.path.join(BASE, "input")
STATE_PATH = os.path.join(BASE, "data", "review_state.json")
FEEDBACK_PATH = os.path.join(BASE, "data", "feedback.jsonl")
APPROVED_HASHES_PATH = os.path.join(BASE, "data", "approved_hashes.json")
DEDUP_HASH_CACHE_PATH = os.path.join(BASE, "data", "dedup_hash_cache.json")
DEDUP_REPORT_PATH = os.path.join(BASE, "reports", "dedup_check", "latest.json")

_lock = threading.Lock()

# Verdicts a reviewer can record. "pending" is the absence of a decision, not
# a decision — a folder with pending items is not approved.
APPROVED = "approved"
REJECTED = "rejected"
PENDING = "pending"

# Rejection reasons, drawn from defects this pipeline has ACTUALLY produced
# rather than a generic quality taxonomy. Each carries the knob it should
# eventually move, because a reason nobody can act on is just a comment.
#
# The mapping is recorded now and applied later: with a handful of labels a
# calibrator would only be guessing, which is the mistake that set the pair
# threshold to 0.87 on four samples. Collect first, tune when the data can
# carry the conclusion.
REJECTION_REASONS = [
    {"code": "design_mismatch", "key": "1",
     "label": "Design differs from original",
     "tunes": "reference crop quality; refine denoise strength"},
    {"code": "pair_mismatch", "key": "2",
     "label": "Two halves don't match each other",
     "tunes": "per-category pair-similarity flag threshold"},
    {"code": "piece_count", "key": "3",
     "label": "Wrong number of pieces",
     "tunes": "category_topology visible_piece_count for this category"},
    {"code": "fused", "key": "4",
     "label": "Pieces merged / joined together",
     "tunes": "anti-fusion prompt clause weighting"},
    {"code": "wrong_object", "key": "5",
     "label": "Wrong object (tag, stand, background)",
     "tunes": "crop guard threshold; localiser preference for category"},
    {"code": "detail_lost", "key": "6",
     "label": "Fine detail / filigree lost",
     "tunes": "sampler steps; crop occupancy target"},
    {"code": "stones_wrong", "key": "7",
     "label": "Stones wrong colour or position",
     "tunes": "prompt stone clause; reference crop tightness"},
    {"code": "proportion", "key": "8",
     "label": "Proportions distorted",
     "tunes": "aspect handling in compose step"},
    {"code": "finish", "key": "9",
     "label": "Background, shadow or polish wrong",
     "tunes": "shadow QA threshold; background prompt clause"},
    {"code": "other", "key": "0",
     "label": "Other (see note)",
     "tunes": None},
]

_REASON_CODES = {r["code"] for r in REJECTION_REASONS}


def _load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    """Atomic write — a torn review file would lose approvals silently."""
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, STATE_PATH)


def _find_original(label: str) -> str | None:
    """Locate the RAW MASTER photograph for a tag label.

    Searched in capture_intake first (never-yet-approved -- covers both
    unprocessed items and rejected items awaiting requeue), then processed/
    (approved items -- see _relocate_source), then processing/ and input/ as
    fallbacks for items captured outside the normal flow.

    Note: rejected/ is NOT one of these roots. It holds the DELIVERED
    (generated) image for a rejected item, not the raw master -- see
    _find_finished_output / _relocate_finished_output for that side.

    Self-healing: if a label somehow ends up in BOTH capture_intake and
    processed/ at once (observed in practice -- an older code path, or a
    second process, can create this without going through _relocate_source),
    a naive first-match search would just silently return whichever root it
    checks first and never notice the duplicate sitting in the other one.
    Identical bytes get collapsed to a single copy on the spot; a genuine
    content mismatch is left for check_capture_rejected_dedup to surface
    rather than guessed at here.
    """
    fname = f"{label}.jpg"
    found = []
    for root in (CAPTURE_INTAKE, PROCESSED_DIR):
        if not os.path.isdir(root):
            continue
        for folder in os.listdir(root):
            candidate = os.path.join(root, folder, fname)
            if os.path.isfile(candidate):
                found.append(candidate)
    if len(found) > 1:
        primary = found[0]  # capture_intake takes priority, matching the original search order
        for extra in found[1:]:
            if _same_bytes(primary, extra):
                try:
                    os.remove(extra)
                except OSError:
                    pass
        return primary
    if found:
        return found[0]
    for root in (os.path.join(BASE, "processing"), INPUT_DIR):
        candidate = os.path.join(root, fname)
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_all_finished_outputs(label: str) -> list[str]:
    """Every DELIVERED (generated) image on disk for a tag label -- output/
    for anything not rejected, rejected/ once _relocate_finished_output has
    moved it there, or (rarely) both at once if a prior reject/reprocess
    cycle left a stale copy behind (see _relocate_finished_output). Matches
    by _label_from_path, same as collect_items, so a retry-suffixed delivery
    (JB22_10_2.jpg) is found under its clean label -- an exact "{label}.jpg"
    match would silently miss it."""
    found = []
    for root in (OUTPUT_DIR, REJECTED_DIR):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if "_edit_reports" in dirpath:
                continue
            for fname in files:
                if fname.lower().endswith(".jpg") and _label_from_path(fname) == label:
                    found.append(os.path.join(dirpath, fname))
    return found


def _find_finished_output(label: str) -> str | None:
    """Locate the single DELIVERED (generated) image for a tag label. See
    _find_all_finished_outputs for the full picture when more than one
    exists."""
    found = _find_all_finished_outputs(label)
    return found[0] if found else None


def _same_bytes(first: str, second: str) -> bool:
    if os.path.getsize(first) != os.path.getsize(second):
        return False
    def digest(path: str) -> bytes:
        value = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                value.update(chunk)
        return value.digest()
    return digest(first) == digest(second)


def _relocate_between(
    current: str | None, *, target_root: str, managed_roots: tuple[str, ...]
) -> str | None:
    """Shared move-with-mirrored-subfolder logic for both the raw-master
    router (_relocate_source) and the delivered-image router
    (_relocate_finished_output). A move, not a copy, so nothing is ever
    destroyed and every transition is fully reversible. No-ops when the file
    is already on the correct side or living somewhere unmanaged, so it's
    safe to call unconditionally on every set_verdict.
    """
    if not current or not os.path.isfile(current):
        return current
    category_dir = os.path.dirname(current)
    current_root = os.path.dirname(category_dir)
    if os.path.normcase(current_root) == os.path.normcase(target_root):
        return current  # already on the correct side
    if not any(os.path.normcase(current_root) == os.path.normcase(root) for root in managed_roots):
        return current  # living somewhere unmanaged (e.g. processing/input) -- leave alone
    folder_name = os.path.basename(category_dir)
    fname = os.path.basename(current)
    dest_dir = os.path.join(target_root, folder_name)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, fname)
    if os.path.exists(dest):
        if _same_bytes(current, dest):
            os.remove(current)
            return dest
        return current  # genuine conflict -- leave both copies alone
    shutil.move(current, dest)
    return dest


def _relocate_source(label: str, verdict: str) -> str | None:
    """Route the RAW MASTER to the folder matching its verdict: capture_intake/
    holds it for both pending AND rejected items (rejected still needs a
    requeue, so it belongs with the rest of the unprocessed backlog, not off
    on its own); only an approved verdict pulls it into processed/.

    processed_state.record_success (app.py) independently moves each item's
    WORKING copy from input/ into the processed/ tree the moment its
    generation succeeds -- before any human has reviewed it, regardless of
    the eventual verdict. So by the time an item gets approved here, the
    destination frequently already exists (byte-identical, since that copy
    traces back to the same capture_intake master). In that case the
    capture_intake master is now redundant, not blocked: verify the bytes
    match and delete it rather than leaving two copies lying around. A
    genuine content mismatch (should never happen) is left untouched on both
    sides rather than risk destroying either copy.
    """
    target_root = PROCESSED_DIR if verdict == APPROVED else CAPTURE_INTAKE
    return _relocate_between(
        _find_original(label),
        target_root=target_root,
        managed_roots=(CAPTURE_INTAKE, PROCESSED_DIR),
    )


def reconcile_source_routes() -> dict:
    """Repair raw-master locations from persisted review verdicts.

    ``set_verdict`` routes every new decision immediately. This startup pass
    closes the remaining crash/old-process gap: approvals belong only in
    processed/, while pending and rejected masters belong only in
    capture_intake/. Byte-different conflicts are preserved and reported.
    """
    with _lock:
        state = dict(_load_state())

    result = {
        "checked": 0,
        "repaired": 0,
        "compliant": 0,
        "missing": [],
        "conflicts": [],
        "delivery_repaired": 0,
        "delivery_conflicts": [],
    }
    for label, saved in sorted(state.items()):
        verdict = str((saved or {}).get("verdict") or PENDING)
        if verdict not in (APPROVED, REJECTED, PENDING):
            continue
        result["checked"] += 1
        before_capture = _paths_for_label(CAPTURE_INTAKE, label)
        before_processed = _paths_for_label(PROCESSED_DIR, label)
        _relocate_source(label, verdict)
        after_capture = _paths_for_label(CAPTURE_INTAKE, label)
        after_processed = _paths_for_label(PROCESSED_DIR, label)

        expected_processed = verdict == APPROVED
        correct = after_processed if expected_processed else after_capture
        wrong = after_capture if expected_processed else after_processed
        if len(correct) == 1 and not wrong:
            if before_capture != after_capture or before_processed != after_processed:
                result["repaired"] += 1
            else:
                result["compliant"] += 1
        elif not correct and not wrong:
            result["missing"].append(label)
        else:
            result["conflicts"].append({
                "label": label,
                "verdict": verdict,
                "capture_intake": after_capture,
                "processed": after_processed,
            })

        if verdict not in (APPROVED, REJECTED):
            continue
        before_finished = _find_all_finished_outputs(label)
        if not before_finished:
            continue
        _relocate_finished_output(label, verdict)
        after_finished = _find_all_finished_outputs(label)
        expected_root = REJECTED_DIR if verdict == REJECTED else OUTPUT_DIR
        wrong_root = OUTPUT_DIR if verdict == REJECTED else None
        wrong = [
            path for path in after_finished
            if wrong_root and _path_is_under(path, wrong_root)
        ]
        if wrong:
            result["delivery_conflicts"].append({
                "label": label,
                "verdict": verdict,
                "paths": wrong,
            })
        elif any(_path_is_under(path, expected_root) for path in after_finished):
            if sorted(before_finished) != sorted(after_finished):
                result["delivery_repaired"] += 1
    return result


def _paths_for_label(root: str, label: str) -> list[str]:
    if not os.path.isdir(root):
        return []
    fname = f"{label}.jpg"
    return sorted(
        os.path.join(root, folder, fname)
        for folder in os.listdir(root)
        if os.path.isfile(os.path.join(root, folder, fname))
    )


def _path_is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((os.path.abspath(path), os.path.abspath(root))) == os.path.abspath(root)
    except ValueError:
        return False


def _relocate_finished_output(label: str, verdict: str) -> str | None:
    """Route the DELIVERED (generated) image to the folder matching its
    verdict: rejected/ once rejected, output/ otherwise. Independent of
    _relocate_source, which handles the RAW master's location instead --
    the two images (raw capture vs. FLUX output) are entirely different
    files and can end up on opposite sides at once (e.g. rejected raw master
    back in capture_intake awaiting a reshoot, its rejected delivered image
    parked in rejected/ for the record).

    A label can end up with more than one delivered copy on disk: reject an
    item (image moves to rejected/), requeue and reprocess it (a fresh image
    lands in output/), then review again -- now output/ has the current
    result and rejected/ still has the old one from the first attempt. The
    newest copy by mtime is treated as authoritative and routed to the
    correct side; any OTHER copy is removed ONLY if it's byte-identical to
    the authoritative one (a true redundant leftover). A copy with genuinely
    different content under the same label is left alone no matter what --
    that would mean two different physical deliveries share a label, which
    is a real conflict for a human to resolve, not something to guess away
    by deleting one side.
    """
    found = _find_all_finished_outputs(label)
    if not found:
        return None
    if verdict == REJECTED:
        # A rejected verdict applies to every delivery carrying this label,
        # including retry-suffixed variants. Leaving an older distinct retry
        # in output/ makes the rejected item appear approved. Preserve every
        # file, but route all of them to rejected/.
        moved = []
        for current in sorted(found, key=os.path.getmtime):
            target = _relocate_between(
                current,
                target_root=REJECTED_DIR,
                managed_roots=(OUTPUT_DIR, REJECTED_DIR),
            )
            if target:
                moved.append(target)
        return moved[-1] if moved else None
    target_root = REJECTED_DIR if verdict == REJECTED else OUTPUT_DIR
    primary = max(found, key=os.path.getmtime)
    moved = _relocate_between(primary, target_root=target_root, managed_roots=(OUTPUT_DIR, REJECTED_DIR))
    resolved_moved = os.path.normcase(os.path.abspath(moved)) if moved else None
    for stale in found:
        if os.path.normcase(os.path.abspath(stale)) in {os.path.normcase(os.path.abspath(primary)), resolved_moved}:
            continue
        if not os.path.isfile(stale):
            continue  # already gone (e.g. _relocate_between's own dedup-and-remove already claimed it)
        reference = moved if (moved and os.path.isfile(moved)) else primary
        if os.path.isfile(reference) and _same_bytes(reference, stale):
            try:
                os.remove(stale)
            except OSError:
                pass
        # else: genuinely different content under the same label -- leave it;
        # check_capture_rejected_dedup-style scrutiny should catch this, not
        # a silent delete here.
    return moved


def _hash_cache_load() -> dict:
    try:
        with open(DEDUP_HASH_CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _hash_cache_save(cache: dict) -> None:
    tmp = DEDUP_HASH_CACHE_PATH + ".tmp"
    os.makedirs(os.path.dirname(DEDUP_HASH_CACHE_PATH), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    os.replace(tmp, DEDUP_HASH_CACHE_PATH)


def _cached_sha256(path: str, cache: dict) -> str:
    """Hash a file, skipping the read if size+mtime match a prior hash.

    capture_intake alone runs to 900+ files; rehashing all of them on every
    single batch would make this check slower each time the backlog grows.
    Keyed on path+size+mtime rather than content, so a changed file is always
    re-read -- the cache can only make this faster, never wrong.
    """
    stat = os.stat(path)
    entry = cache.get(path)
    if entry and entry.get("size") == stat.st_size and entry.get("mtime") == stat.st_mtime:
        return entry["sha256"]
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    cache[path] = {"size": stat.st_size, "mtime": stat.st_mtime, "sha256": value}
    return value


def check_capture_rejected_dedup() -> dict:
    """Verify capture_intake/ and processed/ never hold the same physical
    RAW MASTER, checked two ways:

    - By label: the same tag appearing in both roots at once would mean
      _relocate_source left a stale copy behind mid-move -- should be
      structurally impossible, but this is the check that would catch it if
      it ever happened (crash mid-move, manual file copy, etc).
    - By content: the same photo bytes appearing under two DIFFERENT labels
      across the two roots -- a real capture-side mistake (the same physical
      piece photographed and tagged twice), not something _relocate_source
      can prevent since it only ever sees one label at a time.

    Named for its original ask ("capture intake and rejected shouldn't have
    the same files") but checks capture_intake against processed/, not
    rejected/: rejected items keep their raw master in capture_intake
    (awaiting reshoot/reprocess) same as a never-touched item, so
    capture_intake vs rejected/ was folded into this same comparison for
    free. rejected/ itself now holds DELIVERED images, not raw masters --
    different content entirely, so comparing it here would never mean
    anything; a rejected item's raw master and its rejected delivered image
    are two different files by design (see _relocate_finished_output).

    Meant to run once per batch, not per item -- called from app.py after
    each generation run completes. Writes reports/dedup_check/latest.json so
    a violation is visible without digging through logs, and never raises:
    a broken integrity check must not be able to take down a batch.
    """
    cache = _hash_cache_load()
    by_label_root: dict[str, dict[str, list[str]]] = {}
    by_hash: dict[str, list[str]] = {}
    counts = {}
    for root_name, root in (("capture_intake", CAPTURE_INTAKE), ("processed", PROCESSED_DIR)):
        count = 0
        if os.path.isdir(root):
            for folder in os.listdir(root):
                folder_path = os.path.join(root, folder)
                if not os.path.isdir(folder_path):
                    continue
                for fname in os.listdir(folder_path):
                    if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                        continue
                    path = os.path.join(folder_path, fname)
                    count += 1
                    label = os.path.splitext(fname)[0]
                    by_label_root.setdefault(label, {}).setdefault(root_name, []).append(path)
                    digest = _cached_sha256(path, cache)
                    by_hash.setdefault(digest, []).append(path)
        counts[root_name] = count
    _hash_cache_save(cache)

    # A conflict is a label present in BOTH roots at once -- multiple files
    # under one label within a single root (e.g. a .jpg and .png twin) is a
    # separate, unrelated situation this check isn't looking for.
    label_conflicts = {
        label: roots for label, roots in by_label_root.items() if len(roots) > 1
    }
    content_duplicates = {
        digest: paths for digest, paths in by_hash.items()
        if len(paths) > 1
        and len({os.path.splitext(os.path.basename(p))[0] for p in paths}) > 1
    }
    report = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "capture_intake_files": counts.get("capture_intake", 0),
        "processed_files": counts.get("processed", 0),
        "label_conflicts": label_conflicts,
        "content_duplicates": content_duplicates,
        "ok": not label_conflicts and not content_duplicates,
    }
    os.makedirs(os.path.dirname(DEDUP_REPORT_PATH), exist_ok=True)
    tmp = DEDUP_REPORT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    os.replace(tmp, DEDUP_REPORT_PATH)
    return report


def _write_reject_manifest() -> None:
    """Rebuild rejected/REJECT_REASONS.txt from review_state.json.

    One plain-text file, not one sidecar per photo: a reviewer opens it in
    Notepad and reads every reject reason next to its filename in one pass,
    rather than hunting through the JSON or opening each image individually.
    Regenerated wholesale on every verdict change so it can never drift from
    review_state.json -- there is no incremental state to get out of sync.
    """
    state = _load_state()
    rows = sorted(
        (label, row) for label, row in state.items() if row.get("verdict") == REJECTED
    )
    lines = [
        f"Rejected items -- regenerated {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"{len(rows)} item(s)",
        "",
    ]
    for label, row in rows:
        reason_code = row.get("reason")
        reason_label = next(
            (r["label"] for r in REJECTION_REASONS if r["code"] == reason_code),
            reason_code or "(no reason given)",
        )
        note = (row.get("note") or "").strip()
        line = f"{label}.jpg -- {reason_label}"
        if note:
            line += f": {note}"
        lines.append(line)
    os.makedirs(REJECTED_DIR, exist_ok=True)
    tmp = REJECTED_MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, REJECTED_MANIFEST)


def _label_from_path(path: str) -> str:
    """JB22_10_2.jpg -> JB22_10.  Retry suffixes are not distinct items."""
    stem = os.path.splitext(os.path.basename(path))[0]
    parts = stem.split("_")
    # Trailing pure-digit segment is a retry counter only when the stem
    # already has the TAG_NUMBER shape (JB22_10_2). JB22_10 keeps its 10.
    if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        return "_".join(parts[:-1])
    return stem


# A pause longer than this between delivered images means a new run started.
#
# Derived from real timing rather than picked: a healthy item lands every
# ~47s, a slow one on a partial model load takes up to ~10 min, and the gaps
# BETWEEN runs on 2026-08-08 were 12.3 and 10.8 minutes. 5 minutes sits above
# every within-run gap observed and below every between-run gap.
#
# Deliberately inferred from file times rather than requiring a run id: it
# works on batches that were produced before any of this existed, which is
# exactly when a reviewer needs it most.
BATCH_GAP_SECONDS = 300


def list_batches(category: str | None = None) -> list:
    """Group delivered items into runs, newest first.

    A reviewer thinks in batches — "the run before the colour fix" — not in a
    flat list of 91 files. Landing them in one undifferentiated queue is what
    made the review screen jump to a half-finished item with no way to choose.
    """
    items = collect_items(category)
    stamped = []
    for it in items:
        path = it.get("_edited_path")
        try:
            stamped.append((os.path.getmtime(path), it))
        except (OSError, TypeError):
            continue
    stamped.sort(key=lambda row: row[0])

    batches, current, prev_ts = [], [], None
    for ts, item in stamped:
        if prev_ts is not None and (ts - prev_ts) > BATCH_GAP_SECONDS:
            batches.append(current)
            current = []
        current.append((ts, item))
        prev_ts = ts
    if current:
        batches.append(current)

    out = []
    for idx, group in enumerate(batches, start=1):
        rows = [it for _ts, it in group]
        approved = sum(1 for i in rows if i["verdict"] == APPROVED)
        rejected = sum(1 for i in rows if i["verdict"] == REJECTED)
        errored = sum(1 for i in rows if i["status"] == "errored")
        out.append({
            "batch": idx,
            "started": group[0][0],
            "ended": group[-1][0],
            "started_hm": time.strftime("%H:%M", time.localtime(group[0][0])),
            "ended_hm": time.strftime("%H:%M", time.localtime(group[-1][0])),
            "date": time.strftime("%d %b", time.localtime(group[0][0])),
            "total": len(rows),
            "approved": approved,
            "rejected": rejected,
            "pending": len(rows) - approved - rejected,
            "errored": errored,
            "complete": bool(rows) and approved == len(rows),
            "labels": [i["label"] for i in rows],
        })
    out.reverse()          # newest run first — that is the one being reviewed
    return out


def collect_items(category: str | None = None) -> list:
    """Every item from the last run: passed, flagged and errored alike."""
    state = _load_state()
    items: dict[str, dict] = {}

    # Published output — the passes.
    for root, _dirs, files in os.walk(OUTPUT_DIR):
        if "_edit_reports" in root:
            continue
        for fname in files:
            if not fname.lower().endswith(".jpg"):
                continue
            label = _label_from_path(fname)
            rel_cat = os.path.relpath(root, OUTPUT_DIR).split(os.sep)[0]
            if category and rel_cat != category:
                continue
            items[label] = {
                "label": label,
                "category": rel_cat,
                "edited": os.path.join(root, fname),
                "status": "passed",
                "error": None,
            }

    # rejected/ — delivered images already rejected, moved out of output/ by
    # _relocate_finished_output. Still reviewable (a reviewer may want to
    # revisit a call), so they must appear here exactly like a fresh pass.
    if os.path.isdir(REJECTED_DIR):
        for root, _dirs, files in os.walk(REJECTED_DIR):
            for fname in files:
                if not fname.lower().endswith(".jpg"):
                    continue
                label = _label_from_path(fname)
                if label in items:
                    continue
                rel_cat = os.path.relpath(root, REJECTED_DIR).split(os.sep)[0]
                if category and rel_cat != category:
                    continue
                items[label] = {
                    "label": label,
                    "category": rel_cat,
                    "edited": os.path.join(root, fname),
                    "status": "passed",
                    "error": None,
                }

    # needs_review — the failures. These must be reviewable too: an item that
    # errored is a decision waiting to be made, not a thing to forget.
    if os.path.isdir(NEEDS_REVIEW):
        for root, _dirs, files in os.walk(NEEDS_REVIEW):
            for fname in files:
                if not fname.lower().endswith(".jpg"):
                    continue
                label = _label_from_path(fname)
                if label in items:
                    continue          # already published on a later retry
                items[label] = {
                    "label": label,
                    "category": category or "",
                    "edited": os.path.join(root, fname),
                    "status": "errored",
                    "error": os.path.basename(os.path.dirname(root + os.sep)),
                }

    out = []
    for label, item in sorted(items.items()):
        item["original"] = _find_original(label)
        # Kept under a private key so batching can read the delivery time.
        # The API strips it before the browser sees any filesystem path.
        item["_edited_path"] = item.get("edited")
        saved = state.get(label) or {}
        item["verdict"] = saved.get("verdict", PENDING)
        item["reason"] = saved.get("reason")
        item["reviewed_at"] = saved.get("reviewed_at")
        out.append(item)
    return out


def set_verdict(label: str, verdict: str, reason: str | None = None,
                note: str | None = None, features: dict | None = None) -> dict:
    """Record a reviewer decision plus WHY, and the item's measurements.

    The features matter as much as the verdict. "JB22_18 was rejected" teaches
    nothing; "JB22_18 was rejected for pair_mismatch at pair_similarity 0.861,
    crop_method colour_gold, occupancy 0.92" is a row a calibrator can learn a
    threshold from. Everything here is already computed during generation and
    was previously discarded at report time.
    """
    if verdict not in (APPROVED, REJECTED, PENDING):
        raise ValueError(f"unknown verdict: {verdict}")
    if verdict == REJECTED and reason and reason not in _REASON_CODES:
        raise ValueError(f"unknown rejection reason: {reason}")
    with _lock:
        state = _load_state()
        state[label] = {"verdict": verdict, "reason": reason, "note": note,
                        "reviewed_at": time.time()}
        _save_state(state)
        row = {"label": label, "verdict": verdict, "reason": reason,
               "note": note, "ts": time.time()}
        row.update(features or _item_features(label))
        _append_feedback(row)
    _relocate_source(label, verdict)
    delivery = _relocate_finished_output(label, verdict)
    _sync_approved_hash(label, verdict)
    _write_reject_manifest()
    if verdict == APPROVED:
        import orn_item_image_sync

        try:
            if not delivery:
                raise FileNotFoundError(f"approved delivery not found for {label}")
            state[label]["upload"] = orn_item_image_sync.publish_approved(label, delivery)
        except Exception as exc:
            orn_item_image_sync.record_failure(label, exc)
            state[label]["upload"] = orn_item_image_sync.queue_upload(label, delivery or "", exc)
            try:
                orn_item_image_sync.trigger_user_upload_worker()
            except Exception:
                pass
    return state[label]


def _item_features(label: str) -> dict:
    """Measurements recorded for this item during generation, if we kept them.

    Read from the per-item sidecars rather than recomputed: the point is to
    capture what the pipeline BELIEVED at the time it made its decision, which
    is what a future calibrator has to reason about.
    """
    feats: dict = {}
    for folder in (os.path.join(BASE, "input"), os.path.join(BASE, "processing")):
        meta = os.path.join(folder, f".{label}.auto_reference.crop.json")
        if os.path.isfile(meta):
            try:
                with open(meta, "r", encoding="utf-8") as fh:
                    info = json.load(fh)
                guard = info.get("guard") or {}
                feats.update({
                    "crop_method": info.get("method"),
                    "crop_occupancy": info.get("occupancy"),
                    "jewel_score": guard.get("jewel_score"),
                    "jewellery_pieces": guard.get("jewellery_pieces"),
                })
            except Exception:
                pass
            break
    return feats


def _sha256_file(path: str) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _load_approved_hashes() -> dict:
    try:
        with open(APPROVED_HASHES_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_approved_hashes(registry: dict) -> None:
    tmp = APPROVED_HASHES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=1)
    os.replace(tmp, APPROVED_HASHES_PATH)


def _sync_approved_hash(label: str, verdict: str) -> None:
    """Keep approved_hashes.json in lockstep with a verdict.

    Approving a label flags its master photo's sha256 so the same physical
    piece can never be paid-for and processed twice under a different tag.
    Un-approving (rejected/pending) removes the flag -- a rejected item must
    stay reprocessable, not get permanently locked out by its own history.
    """
    with _lock:
        registry = _load_approved_hashes()
        stale = [h for h, row in registry.items() if row.get("label") == label]
        for h in stale:
            registry.pop(h, None)
        if verdict == APPROVED:
            original = _find_original(label)
            digest = _sha256_file(original) if original else None
            if digest:
                registry[digest] = {"label": label, "approved_at": time.time()}
        _save_approved_hashes(registry)


def find_approved_duplicate(source_path: str, exclude_label: str | None = None) -> dict | None:
    """Is this exact photo already an approved item under a different tag?

    Returns the matching {sha256, label, approved_at} row, or None. Checked
    before spending an API call, so a re-uploaded or re-captured duplicate of
    an already-approved piece is caught for free instead of paid for twice.
    """
    digest = _sha256_file(source_path)
    if not digest:
        return None
    registry = _load_approved_hashes()
    row = registry.get(digest)
    if not row or row.get("label") == exclude_label:
        return None
    return {"sha256": digest, **row}


def reason_catalogue() -> list:
    return REJECTION_REASONS


def _append_feedback(row: dict) -> None:
    """Append-only history. Never rewritten, so a bad calibration can always
    be traced back to the labels it was computed from."""
    try:
        with open(FEEDBACK_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


def requeue(labels: list) -> dict:
    """Put items back in input/ to be processed again.

    Copies from wherever the master currently lives (capture_intake or, if it
    was approved and relocated, processed/) rather than moving anything, so a
    requeue can be repeated and can never destroy the only copy of a
    photograph.
    """
    done, missing = [], []
    os.makedirs(INPUT_DIR, exist_ok=True)
    for label in labels:
        src = _find_original(label)
        if not src:
            missing.append(label)
            continue
        try:
            shutil.copy2(src, os.path.join(INPUT_DIR, f"{label}.jpg"))
            done.append(label)
        except Exception:
            missing.append(label)
    return {"requeued": done, "missing": missing}


def folder_summary(category: str | None = None) -> dict:
    """Is this folder actually finished?

    "Processed" and "approved" are tracked separately on purpose. A batch that
    generated 65 images and had none of them looked at is not done, and a
    dashboard that shows it green would be lying.
    """
    items = collect_items(category)
    total = len(items)
    approved = sum(1 for i in items if i["verdict"] == APPROVED)
    rejected = sum(1 for i in items if i["verdict"] == REJECTED)
    pending = total - approved - rejected
    errored = sum(1 for i in items if i["status"] == "errored")
    return {
        "category": category,
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "errored": errored,
        # Green ONLY when every item has been seen and approved.
        "complete": bool(total) and approved == total,
    }

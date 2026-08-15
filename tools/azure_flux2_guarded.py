"""Fail-closed Azure FLUX.2-pro caller with local spend caps and hybrid finishing."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import numpy as np
from PIL import Image


def normalize_white_balance(image: Image.Image) -> Image.Image:
    """Correct camera white-balance/exposure drift before sending to FLUX,
    using the black velvet background as a neutral calibration anchor.

    Raw capture photos vary in colour cast (pale/warm/cool) depending on the
    camera and lighting at the time of the shot. FLUX has no colour anchor in
    the API call and reinterprets "realistic gold" independently per item, so
    that per-photo cast becomes per-item colour drift in the finished
    catalogue. The velvet backdrop is meant to be neutral black in every
    shot (see CAPTURE_CHECKLIST.md) -- if the darkest pixels in the frame
    aren't R=G=B, that's the camera's cast, not the jewellery's, and can be
    removed with a per-channel gain before generation ever sees the image.
    """
    arr = np.array(image).astype(np.float32)
    luma = arr.mean(axis=2)
    dark_threshold = np.percentile(luma, 5)
    anchor_pixels = arr[luma <= dark_threshold]
    if anchor_pixels.shape[0] < 50:
        return image
    anchor_mean = anchor_pixels.mean(axis=0)
    neutral = anchor_mean.mean()
    if neutral < 1.0:
        return image
    gains = np.clip(neutral / np.clip(anchor_mean, 1.0, None), 0.85, 1.18)
    corrected = np.clip(arr * gains, 0, 255).astype("uint8")
    return Image.fromarray(corrected, mode="RGB")


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "azure_flux2_guard.json"
REPORT_DIR = ROOT / "reports" / "azure_flux2_guard"
USAGE_FILE = REPORT_DIR / "usage.json"
ACTIVE_LOCK = REPORT_DIR / "ACTIVE_CALL.lock"
DASHBOARD = REPORT_DIR / "COST_DASHBOARD.html"
MODEL = "FLUX.2-pro"
# Fixed across every call in a batch so the model's own random style/colour
# interpretation stays consistent item-to-item, instead of drifting on every
# call. High guidance biases the model to follow the exact hex-coded gold
# palette in the prompt more strictly rather than improvising.
FIXED_SEED = 74203
FIXED_GUIDANCE = 6.5


def find_image_result(payload: object) -> tuple[str, str]:
    """Find the generated image in Azure's response."""
    if isinstance(payload, dict):
        for key in ("b64_json", "base64", "image_base64", "sample"):
            value = payload.get(key)
            if isinstance(value, str) and len(value) > 100:
                if value.startswith(("http://", "https://")):
                    return "url", value
                return "base64", value.split(",", 1)[1] if value.startswith("data:image/") and "," in value else value
        for key in ("url", "image_url", "output_url"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return "url", value
        values = payload.values()
    elif isinstance(payload, list):
        values = payload
    else:
        values = ()
    for value in values:
        try:
            return find_image_result(value)
        except LookupError:
            pass
    raise LookupError("Azure response contained no supported image field")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_usage() -> dict:
    if not USAGE_FILE.exists():
        return {"schema": 1, "records": []}
    return load_json(USAGE_FILE)


def billed_megapixels(width: int, height: int) -> int:
    return max(1, math.ceil((width * height) / 1_000_000))


def estimate_cost(sources: list[Path], output_width: int, output_height: int, safety_factor: float) -> dict:
    input_dimensions = []
    input_mp = 0
    for source in sources:
        with Image.open(source) as image:
            dimensions = [image.width, image.height]
        input_dimensions.append(dimensions)
        input_mp += billed_megapixels(*dimensions)
    output_mp = billed_megapixels(output_width, output_height)
    list_price = input_mp * 0.015 + 0.03 + max(0, output_mp - 1) * 0.015
    reserved = math.ceil(list_price * safety_factor * 100) / 100
    return {
        "input_dimensions": input_dimensions,
        "input_billed_mp": input_mp,
        "output_dimensions": [output_width, output_height],
        "output_billed_mp": output_mp,
        "list_price_estimate_usd": round(list_price, 4),
        "reserved_usd": round(reserved, 2),
    }


def prepare_reference(source: Path, maximum_megapixels: float) -> tuple[Path, dict]:
    maximum_pixels = max(1, int(maximum_megapixels * 1_000_000))
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    native_pixels = image.width * image.height
    metadata = {
        "native_dimensions": [image.width, image.height],
        "native_megapixels": round(native_pixels / 1_000_000, 4),
        "reference_resize": "none",
    }
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    prepared_dir = REPORT_DIR / "prepared_references"

    if native_pixels <= maximum_pixels:
        prepared = prepared_dir / f"{source.stem}_{digest}_wb.png"
        if not prepared.exists():
            prepared_dir.mkdir(parents=True, exist_ok=True)
            normalize_white_balance(image).save(prepared, format="PNG", optimize=True)
        metadata["reference_dimensions"] = [image.width, image.height]
        metadata["reference_megapixels"] = round(native_pixels / 1_000_000, 4)
        metadata["white_balance_normalized"] = True
        return prepared, metadata

    scale = math.sqrt(maximum_pixels / native_pixels)
    resized_width = max(1, int(image.width * scale))
    resized_height = max(1, int(image.height * scale))
    while resized_width * resized_height > maximum_pixels:
        if resized_width >= resized_height:
            resized_width -= 1
        else:
            resized_height -= 1
    prepared = prepared_dir / f"{source.stem}_{digest}_{maximum_megapixels:g}mp.png"
    if not prepared.exists():
        prepared_dir.mkdir(parents=True, exist_ok=True)
        resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        normalize_white_balance(resized).save(prepared, format="PNG", optimize=True)
    metadata.update(
        reference_resize="Lanczos; aspect ratio preserved; no crop; no upscale",
        reference_dimensions=[resized_width, resized_height],
        reference_megapixels=round((resized_width * resized_height) / 1_000_000, 4),
        white_balance_normalized=True,
    )
    return prepared, metadata


def totals(config: dict, usage: dict) -> dict:
    """Sum only records that either succeeded or are still unresolved
    (RESERVED_BEFORE_NETWORK left dangling by a crash mid-call). A
    FAILED_NO_RETRY record never reached Azure with a completed image, so it
    isn't real spend -- counting it here inflated lifetime/daily totals used
    for cap enforcement and the dashboard well above what Azure actually
    billed (confirmed: all-records sum overstated the SUCCEEDED-only sum by
    ~$3.73 on the first 60-image live run).
    """
    historical = float(config.get("historical_estimated_spend_usd", 0))
    billable = [record for record in usage["records"] if record.get("status") != "FAILED_NO_RETRY"]
    reserved = sum(float(record.get("reserved_usd", 0)) for record in billable)
    today = datetime.now(timezone.utc).date().isoformat()
    today_records = [record for record in billable if record.get("reserved_at_utc", "").startswith(today)]
    return {
        "historical": historical,
        "guarded_reserved": round(reserved, 2),
        "lifetime_reserved": round(historical + reserved, 2),
        "today_reserved": round(sum(float(record.get("reserved_usd", 0)) for record in today_records), 2),
        "today_calls": len(today_records),
    }


def enforce_caps(config: dict, usage: dict, requested: float) -> None:
    summary = totals(config, usage)
    lifetime_cap = float(config["lifetime_hard_cap_usd"])
    daily_cap = float(config["daily_hard_cap_usd"])
    daily_calls = int(config["maximum_calls_per_day"])
    if summary["lifetime_reserved"] + requested > lifetime_cap + 1e-9:
        raise RuntimeError(f"BLOCKED: lifetime hard cap ${lifetime_cap:.2f} would be exceeded")
    if summary["today_reserved"] + requested > daily_cap + 1e-9:
        raise RuntimeError(f"BLOCKED: daily hard cap ${daily_cap:.2f} would be exceeded")
    if summary["today_calls"] + 1 > daily_calls:
        raise RuntimeError(f"BLOCKED: maximum {daily_calls} calls per UTC day reached")


def render_dashboard(config: dict, usage: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary = totals(config, usage)
    cap = float(config["lifetime_hard_cap_usd"])
    remaining_cap = max(0.0, cap - summary["lifetime_reserved"])
    trial_start = float(config.get("trial_credit_start_usd", 0))
    estimated_credit = max(0.0, trial_start - summary["lifetime_reserved"])
    rows = []
    for record in reversed(usage["records"][-100:]):
        rows.append(
            "<tr>"
            f"<td>{escape(record.get('reserved_at_utc', ''))}</td>"
            f"<td>{escape(Path(record.get('source', '')).name)}</td>"
            f"<td>{escape(record.get('status', ''))}</td>"
            f"<td>${float(record.get('list_price_estimate_usd', 0)):.3f}</td>"
            f"<td>${float(record.get('reserved_usd', 0)):.2f}</td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Azure FLUX.2 Cost Guard</title>
<style>body{{font-family:Segoe UI,Arial;margin:32px;background:#f7f8fa;color:#18202a}}.cards{{display:flex;gap:16px;flex-wrap:wrap}}.card{{background:white;border:1px solid #dfe3e8;border-radius:12px;padding:18px;min-width:210px}}.big{{font-size:28px;font-weight:700}}.warn{{background:#fff4ce;border-color:#f0c000}}table{{border-collapse:collapse;width:100%;background:white;margin-top:20px}}th,td{{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left}}a{{color:#075db3}}code{{background:#eef1f4;padding:2px 5px}}</style></head>
<body><h1>Azure FLUX.2 Pro Cost Guard</h1><p>Updated {escape(utc_now())}</p>
<div class="cards">
<div class="card"><div>Estimated lifetime usage</div><div class="big">${summary['lifetime_reserved']:.2f}</div></div>
<div class="card"><div>Local lifetime hard cap</div><div class="big">${cap:.2f}</div><div>${remaining_cap:.2f} remaining</div></div>
<div class="card"><div>Today</div><div class="big">${summary['today_reserved']:.2f}</div><div>{summary['today_calls']} calls; cap ${float(config['daily_hard_cap_usd']):.2f}</div></div>
<div class="card warn"><div>Estimated trial credit</div><div class="big">${estimated_credit:.2f}</div><div>Estimate only; Azure is authoritative.</div></div>
</div>
<h2>Immediate local protection</h2><p>Calls are blocked before network access when either local cap would be exceeded. Failed calls remain reserved conservatively. Automatic retries: <strong>0</strong>.</p>
<h2>Authoritative Azure checks</h2>
<p><a href="https://portal.azure.com/#view/Microsoft_Azure_CostManagement/Menu/~/costanalysis">Open Azure Cost Analysis</a> · <a href="https://portal.azure.com/#view/Microsoft_Azure_Billing/BillingAccountsBlade">Open Billing Accounts / Azure Credits</a></p>
<p>Azure Cost Management commonly lags 8–24 hours. Budgets send alerts but do not stop usage. At the billing-account scope open <strong>Payment methods → Azure credits</strong> and inspect <strong>transactions</strong>. FLUX.2-pro was deployed from the <strong>Direct from Azure</strong> collection; confirm the actual charge appears against Azure credits before raising the local $5 cap.</p>
<h2>Guarded calls</h2><table><tr><th>UTC time</th><th>Source</th><th>Status</th><th>List estimate</th><th>Reserved</th></tr>{''.join(rows) or '<tr><td colspan="5">No guarded calls yet.</td></tr>'}</table>
</body></html>"""
    DASHBOARD.write_text(html, encoding="utf-8")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        # ERROR_ACCESS_DENIED still proves that a process owns this PID.
        return ctypes.get_last_error() == 5
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_pid() -> int | None:
    try:
        content = ACTIVE_LOCK.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    match = re.search(r"(?:^|\s)pid=(\d+)(?:\s|$)", content)
    return int(match.group(1)) if match else None


def acquire_lock() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(str(ACTIVE_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            existing_pid = _lock_pid()
            if existing_pid is not None and _pid_is_running(existing_pid):
                raise RuntimeError(
                    f"BLOCKED: active-call lock exists for live PID {existing_pid}: {ACTIVE_LOCK}"
                ) from exc
            try:
                ACTIVE_LOCK.unlink()
            except FileNotFoundError:
                continue
            except OSError as unlink_error:
                raise RuntimeError(
                    f"BLOCKED: stale active-call lock could not be removed: {ACTIVE_LOCK}"
                ) from unlink_error
    else:
        raise RuntimeError(f"BLOCKED: could not acquire active-call lock: {ACTIVE_LOCK}")
    os.write(descriptor, f"pid={os.getpid()} utc={utc_now()}".encode("utf-8"))
    return descriptor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hybrid-output", type=Path)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument("--background", type=Path)
    parser.add_argument("--dashboard-only", action="store_true")
    parser.add_argument("--open-dashboard", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.config.is_file():
        raise RuntimeError(f"BLOCKED: run secure setup first; missing {args.config}")
    config = load_json(args.config)
    usage = load_usage()
    render_dashboard(config, usage)
    if args.dashboard_only:
        if args.open_dashboard:
            webbrowser.open(DASHBOARD.as_uri())
        print(DASHBOARD)
        return 0
    if not args.input or not args.output:
        raise RuntimeError("BLOCKED: --input and --output are required")
    source = args.input.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    prompt_file = (args.prompt_file or Path(config["default_prompt_file"])).resolve()
    prompt = prompt_file.read_text(encoding="utf-8").strip()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import karat_from_label
    # Real, confirmed bug (2026-08-15): the prompt used to hardcode
    # "22-karat" for every item, including genuinely 18kt pieces (BALI 18,
    # LOCKET 18, LADIES RING 18, TOPS 18, ...) -- wrong for every 18kt
    # category run all session, not just this one. The label already
    # encodes its own real karat; falls back to 22 (documented, this
    # business's dominant karat) only when a label doesn't parse, which
    # should not happen for a real capture_intake file.
    karat = karat_from_label.karat_from_label(source.stem) or "22"
    prompt = prompt.replace("{KARAT}", karat)
    import category_geometry_hints
    geometry_hint = category_geometry_hints.hint_for(args.category, source.stem)
    if geometry_hint:
        # Category/item geometry is front-loaded because BFL's FLUX.2
        # guidance says the most important edit constraint belongs first.
        # Appending this after the long catalogue prompt produced two
        # confirmed BL18_10 failures: correct angle, generic round tube.
        prompt = f"{geometry_hint}\n\n{prompt}"
    import reference_color_report
    color_report = reference_color_report.analyze(str(source))
    prompt = f"{prompt}\n\n{color_report['prompt_line']}"
    width = int(config["output_width"])
    height = int(config["output_height"])
    background_reference = None
    secondary_reference_source = None
    secondary_reference_role = None
    secondary_reference_profile = None
    primary_reference_limit = float(config["maximum_reference_megapixels"])
    if args.background:
        secondary_reference_source = args.background.resolve()
        secondary_reference_role = "explicit_user_reference"
    else:
        import catalogue_reference_guides
        secondary_reference_source = catalogue_reference_guides.guide_for(
            args.category, source.stem
        )
        if secondary_reference_source:
            secondary_reference_role = "automatic_reviewed_item_angle_guide"
            secondary_reference_profile = catalogue_reference_guides.profile_for(
                args.category, source.stem
            )
    if secondary_reference_source:
        if not secondary_reference_source.is_file():
            raise FileNotFoundError(secondary_reference_source)
        background_reference, _ = prepare_reference(secondary_reference_source, 1.0)
        with Image.open(background_reference) as angle_image:
            angle_reference_billed_mp = billed_megapixels(angle_image.width, angle_image.height)
        # Official BFL FLUX.2 [pro] multi-reference guidance limits the
        # combined references plus output to 9 billed MP. Keep the angle
        # guide at 1 MP and assign the remaining budget to the design source.
        available_primary_mp = max(
            1,
            9 - billed_megapixels(width, height) - angle_reference_billed_mp,
        )
        primary_reference_limit = min(primary_reference_limit, float(available_primary_mp))
    reference, reference_metadata = prepare_reference(source, primary_reference_limit)
    reference_metadata["effective_reference_limit_megapixels"] = primary_reference_limit
    references = [reference] + ([background_reference] if background_reference else [])
    cost = estimate_cost(references, width, height, float(config["cost_safety_factor"]))
    enforce_caps(config, usage, float(cost["reserved_usd"]))
    if args.dry_run:
        print(json.dumps({
            "status": "SAFE_DRY_RUN",
            "secondary_reference_source": str(secondary_reference_source) if secondary_reference_source else None,
            "secondary_reference_role": secondary_reference_role,
            "secondary_reference_profile": secondary_reference_profile,
            **reference_metadata,
            **cost,
            **totals(config, usage),
        }, indent=2))
        return 0

    endpoint = os.environ.get("AZURE_ENDPOINT", "").strip().rstrip("/")
    api_key = os.environ.get("AZURE_API_KEY", "").strip()
    if not endpoint or not api_key:
        raise RuntimeError("BLOCKED: secure PowerShell runner did not provide credentials")
    if endpoint != config["endpoint"].rstrip("/"):
        raise RuntimeError("BLOCKED: endpoint does not match guarded configuration")

    descriptor = acquire_lock()
    record = {
        "id": hashlib.sha256(f"{source}|{utc_now()}".encode()).hexdigest()[:16],
        "reserved_at_utc": utc_now(),
        "status": "RESERVED_BEFORE_NETWORK",
        "model": MODEL,
        "source": str(source),
        "prepared_reference": str(reference),
        "prepared_background_reference": str(background_reference) if background_reference else None,
        "secondary_reference_source": str(secondary_reference_source) if secondary_reference_source else None,
        "secondary_reference_role": secondary_reference_role,
        "secondary_reference_profile": secondary_reference_profile,
        "output": str(output),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "automatic_retries": 0,
        "reference_color_report": color_report,
        "category": args.category,
        "category_geometry_hint_applied": bool(geometry_hint),
        **reference_metadata,
        **cost,
    }
    usage["records"].append(record)
    atomic_json(USAGE_FILE, usage)
    render_dashboard(config, usage)
    try:
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "width": width,
            "height": height,
            "output_format": "png",
            "num_images": 1,
            "prompt_upsampling": False,
            "seed": FIXED_SEED,
            "guidance": FIXED_GUIDANCE,
            "input_image": base64.b64encode(reference.read_bytes()).decode("ascii"),
        }
        if background_reference:
            payload["input_image_2"] = base64.b64encode(background_reference.read_bytes()).decode("ascii")
        request = urllib.request.Request(
            f"{endpoint}/providers/blackforestlabs/v1/flux-2-pro?api-version=preview",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=240) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        kind, value = find_image_result(response_payload)
        if kind == "base64":
            image_bytes = base64.b64decode(value, validate=True)
        else:
            parsed = urllib.parse.urlparse(value)
            if parsed.scheme != "https":
                raise RuntimeError("Generated-image URL is not HTTPS")
            with urllib.request.urlopen(value, timeout=60) as response:
                image_bytes = response.read()
        if len(image_bytes) < 1024:
            raise RuntimeError("Azure returned an implausibly small image")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(image_bytes)
        record["status"] = "SUCCEEDED"
        record["completed_at_utc"] = utc_now()
        record["output_bytes"] = len(image_bytes)
        # local_finish's crop/upscale/colour-correct pass is disabled here as
        # of 2026-08-12 -- its output was always discarded downstream by
        # app.py's _publish_delivery, which does its own independent
        # resize/pad/sharpen pipeline and is the one that actually becomes
        # the delivered {tag}.jpg. Computing and then throwing away a second
        # finishing pass every call was pure waste, and local_finish's
        # crop-to-foreground-bbox step is unreliable once a real composed
        # background is in the frame (confirmed on a real generation --
        # see local_catalogue_finish.normalize_gold_tone's docstring).
        print(output)
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:4000]
        record["status"] = "FAILED_NO_RETRY"
        record["error"] = f"Azure HTTP {exc.code}: {detail}"
        raise RuntimeError(record["error"]) from exc
    except Exception as exc:
        record["status"] = "FAILED_NO_RETRY"
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        atomic_json(USAGE_FILE, usage)
        render_dashboard(config, usage)
        os.close(descriptor)
        ACTIVE_LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

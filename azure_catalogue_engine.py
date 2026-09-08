"""Single-provider catalogue adapter for the guarded Azure FLUX.2 Pro call."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "tools" / "run_azure_flux2_guarded.ps1"
PROMPT = ROOT / "config" / "flux2_pro_catalogue_prompt.txt"
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_PROCESS: subprocess.Popen[str] | None = None


class AzureCatalogueError(RuntimeError):
    pass


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    subprocess.run(
        ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if process.poll() is None:
        process.kill()


def cancel_active() -> bool:
    """Cancel the in-flight Azure runner and every child it launched."""

    with _ACTIVE_LOCK:
        process = _ACTIVE_PROCESS
    if process is None or process.poll() is not None:
        return False
    _terminate_process_tree(process)
    return True


def generate(
    source: str | Path,
    output: str | Path,
    *,
    background: str | Path | None = None,
    category: str | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Run exactly one guarded Azure call. Never retries or falls back."""

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if not source_path.is_file():
        raise AzureCatalogueError(f"Source image missing: {source_path}")
    if not RUNNER.is_file():
        raise AzureCatalogueError(f"Azure runner missing: {RUNNER}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RUNNER),
        "-InputImage",
        str(source_path),
        "-OutputImage",
        str(output_path),
        "-PromptFile",
        str(PROMPT),
    ]
    if background is not None:
        background_path = Path(background).resolve()
        if not background_path.is_file():
            raise AzureCatalogueError(f"Background image missing: {background_path}")
        command.extend(["-BackgroundImage", str(background_path)])
    if category is not None:
        command.extend(["-Category", category])
    if cancel_event is not None and cancel_event.is_set():
        raise AzureCatalogueError("CANCELLED: batch stopped before Azure call")

    global _ACTIVE_PROCESS
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    with _ACTIVE_LOCK:
        _ACTIVE_PROCESS = process
    try:
        if cancel_event is not None and cancel_event.is_set():
            _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=360)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            # This drain MUST be bounded. The runner is PowerShell which
            # spawns python; if the grandchild survives the tree kill it keeps
            # the stdout pipe open and an unbounded communicate() blocks
            # forever -- the batch then sits with no active call and never
            # advances (observed 2026-09-01, stuck 8+ minutes on LR22_108).
            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = "", "child did not exit after termination"
            raise AzureCatalogueError("Azure call timed out after 360 seconds")
    finally:
        with _ACTIVE_LOCK:
            if _ACTIVE_PROCESS is process:
                _ACTIVE_PROCESS = None

    if cancel_event is not None and cancel_event.is_set():
        output_path.unlink(missing_ok=True)
        raise AzureCatalogueError("CANCELLED: batch stopped safely")
    if process.returncode != 0:
        detail = (stderr or stdout or "unknown Azure failure").strip()
        raise AzureCatalogueError(detail[-3000:])
    if not output_path.is_file() or output_path.stat().st_size < 30_000:
        raise AzureCatalogueError("Azure call completed without a valid output image")
    hybrid_path = output_path.with_name(output_path.stem + "_hybrid.png")
    return {
        "output": str(output_path),
        "hybrid_output": str(hybrid_path) if hybrid_path.is_file() else None,
        "engine": "azure_flux2_pro",
    }

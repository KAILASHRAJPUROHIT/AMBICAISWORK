"""Engine-specific prompt research, review and approval gate."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPT_FILE = ROOT / "config" / "flux2_pro_catalogue_prompt.txt"
RESEARCH_FILE = ROOT / "config" / "prompt_research.json"
APPROVAL_FILE = ROOT / "config" / "prompt_approval.json"
ENGINE = "azure_flux2_pro"
MODEL = "FLUX.2-pro"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current() -> dict:
    prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()
    research = json.loads(RESEARCH_FILE.read_text(encoding="utf-8-sig"))
    return {
        "engine": ENGINE,
        "model": MODEL,
        "prompt": prompt,
        "prompt_sha256": _sha256(prompt),
        "researched_at": research["researched_at"],
        "sources": research["sources"],
        "guidelines": research["guidelines"],
    }


def approval_status() -> dict:
    state = current()
    try:
        approval = json.loads(APPROVAL_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        approval = {}
    approved = (
        approval.get("engine") == state["engine"]
        and approval.get("model") == state["model"]
        and approval.get("prompt_sha256") == state["prompt_sha256"]
    )
    return {**state, "approved": approved, "approval": approval if approved else None}


def approve(reviewer: str) -> dict:
    state = current()
    record = {
        "engine": state["engine"],
        "model": state["model"],
        "prompt_sha256": state["prompt_sha256"],
        "reviewed_by": reviewer.strip() or "catalogue owner",
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = APPROVAL_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.replace(temporary, APPROVAL_FILE)
    return {**state, "approved": True, "approval": record}

#!/usr/bin/env python3
"""update-14r.py -- keeps the Redmi 14R on the same agent version as the rest of the fleet, wirelessly.

Why this exists
---------------
The 14R (model 2411DRN47C, China HyperOS) was provisioned as a Device Owner with THIS laptop's Android *debug*
certificate. Android refuses any update signed with a different key (INSTALL_FAILED_UPDATE_INCOMPATIBLE), so the
normal release APK and the fleet's over-the-air rollout can never update it. It can only be updated by an APK built
here and signed with the same debug key, installed with `adb install -r`. This script does that automatically
whenever a new release appears on GitHub.

What it does, each run (a scheduled task runs it every 15 minutes and at logon)
-------------------------------------------------------------------------------
 1. Looks for the 14R in `adb devices` (wireless debugging, paired once; see docs/14R-UPDATES.md). Not there -> exits.
 2. Asks GitHub for the latest published release tag (for example v0.2.95) and works out its version code.
 3. Reads the version installed on the 14R. Already at or above the release -> exits.
 4. Checks the 14R is still Device Owner of com.mdmesh.agent. If not -> refuses (never installs onto the wrong state).
 5. Builds the China in-place variant from that exact release tag in a throw-away git worktree
    (:app:assembleAospDebug -PchinaInPlaceReplacement=true), so work in progress here never leaks into it.
 6. Verifies the APK: right package, right version code, and the signing certificate equals the one on the phone.
 7. `adb install -r` (replace in place: never uninstalls, never clears data, never resets), then re-checks the version
    and that it is still Device Owner. A failed attempt backs off for 2 hours.

Usage
-----
    python update-14r.py                  # normal run (what the scheduled task does)
    python update-14r.py --dry-run        # say what it would do, change nothing
    python update-14r.py --build-only     # build + verify the APK for the latest release, do not install
    python update-14r.py --tag v0.2.95    # use a specific release instead of the latest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_DIR = TOOLS_DIR.parent
AGENT_REL = Path("agent-android")
LOG_FILE = TOOLS_DIR / "logs" / "update-14r.log"
STATE_FILE = TOOLS_DIR / "logs" / "update-14r.state.json"
LOCK_FILE = TOOLS_DIR / "logs" / "update-14r.lock"
WORKTREE = REPO_DIR / ".update14r-worktree"
HANDOVER = Path(r"C:\AradhanaSystems\handover")

GH_REPO = "KAILASHRAJPUROHIT/AMBICAISWORK"
GIT_REMOTE = "ambic"                # the only remote this project pushes to
MODEL = "2411DRN47C"                # Redmi 14R
PACKAGE = "com.mdmesh.agent"        # the CN in-place build keeps the production package name
# SHA-256 of the Android debug certificate the 14R was provisioned with (public fingerprint, not a secret).
PINNED_CERT_SHA256 = "d77678ef231293af3b88b6e6a24ca4e4d5d5b45491142b5b36a6675bccfedd15"

JAVA_HOME = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
SDK = Path(os.environ.get("ANDROID_HOME") or r"C:\Users\kaila\AppData\Local\Android\Sdk")

BACKOFF_SECONDS = 2 * 3600
LOCK_STALE_SECONDS = 60 * 60
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    if sys.stdout and sys.stdout.isatty():
        print(line)


def run(cmd: list[str], timeout: int = 120, env: dict | None = None, cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd,
                           creationflags=_NO_WINDOW, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as e:
        return 127, str(e)


def tool(name: str, *fallbacks: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for f in fallbacks:
        if Path(f).exists():
            return f
    return name


ADB = tool("adb", r"C:\platform-tools\adb.exe")
GH = tool("gh", r"C:\Program Files\GitHub CLI\gh.exe")
GIT = tool("git")


def build_tool(name: str) -> str | None:
    found = sorted((SDK / "build-tools").glob(f"*/{name}*"))
    return str(found[-1]) if found else None


# ------------------------------------------------------------------------------------------------ device

def find_14r() -> str | None:
    """adb serial/address of the 14R if it is connected (wirelessly or by USB), else None."""
    rc, out = run([ADB, "devices", "-l"], timeout=30)
    for line in out.splitlines():
        if f"model:{MODEL}" in line and re.search(r"\sdevice\s", line):
            return line.split()[0]
    return None


def adb_shell(serial: str, command: str, timeout: int = 60) -> str:
    return run([ADB, "-s", serial, "shell", command], timeout=timeout)[1]


def installed_code(serial: str) -> int | None:
    m = re.search(r"versionCode=(\d+)", adb_shell(serial, f"dumpsys package {PACKAGE}"))
    return int(m.group(1)) if m else None


def is_device_owner(serial: str) -> bool:
    return PACKAGE in adb_shell(serial, "dpm list-owners")


# ------------------------------------------------------------------------------------------------ release

def latest_release_tag() -> str | None:
    rc, out = run([GH, "release", "view", "--repo", GH_REPO, "--json", "tagName,isDraft,isPrerelease"], timeout=60)
    if rc != 0:
        log(f"could not ask GitHub for the latest release: {out.strip()[:200]}")
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if data.get("isDraft") or data.get("isPrerelease"):
        return None
    return data.get("tagName")


def version_of(tag: str) -> tuple[str, int] | None:
    """v0.2.95 -> ("0.2.95", 295). Same rule as release/version.sh: major*10000 + minor*100 + patch."""
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        return None
    a, b, c = map(int, m.groups())
    return f"{a}.{b}.{c}", a * 10000 + b * 100 + c


# ------------------------------------------------------------------------------------------------ build

def gradle_env() -> dict:
    env = dict(os.environ)
    env["JAVA_HOME"] = JAVA_HOME
    env["PATH"] = JAVA_HOME + r"\bin;" + env.get("PATH", "")
    return env


def build_apk(tag: str, name: str, code: int) -> Path | None:
    """Builds the China in-place debug APK from the release tag in a throw-away worktree."""
    run([GIT, "-C", str(REPO_DIR), "fetch", GIT_REMOTE, "tag", tag, "--no-tags"], timeout=120)
    run([GIT, "-C", str(REPO_DIR), "fetch", GIT_REMOTE, f"refs/tags/{tag}:refs/tags/{tag}"], timeout=120)
    cleanup_worktree()
    rc, out = run([GIT, "-C", str(REPO_DIR), "worktree", "add", "--detach", str(WORKTREE), tag], timeout=180)
    if rc != 0:
        log(f"could not check out {tag}: {out.strip()[:300]}")
        return None
    agent = WORKTREE / AGENT_REL
    # Files that are deliberately not in git but the build needs.
    for rel in ("local.properties", "app/google-services.json"):
        src = REPO_DIR / AGENT_REL / rel
        if src.exists():
            shutil.copy2(src, agent / rel)
    cmd = [str(agent / "gradlew.bat"), ":app:assembleAospDebug", "-PchinaInPlaceReplacement=true",
           f"-PversionName={name}", f"-PversionCode={code}", "-q"]
    log(f"building {tag} (version {name}, code {code}) ...")
    rc, out = run(cmd + ["--offline"], timeout=1500, env=gradle_env(), cwd=agent)
    if rc != 0:
        rc, out = run(cmd, timeout=1500, env=gradle_env(), cwd=agent)  # first time a dependency may be missing offline
    if rc != 0:
        log(f"build failed: {out.strip()[-400:]}")
        return None
    apk = agent / "app" / "build" / "outputs" / "apk" / "aosp" / "debug" / "app-aosp-debug.apk"
    if not apk.exists():
        log("build finished but the APK is missing")
        return None
    HANDOVER.mkdir(parents=True, exist_ok=True)
    final = HANDOVER / f"AmbicMDM-14R-{name}-cn-replace-debugsigned.apk"
    shutil.copy2(apk, final)
    return final


def cleanup_worktree() -> None:
    if WORKTREE.exists():
        run([GIT, "-C", str(REPO_DIR), "worktree", "remove", "--force", str(WORKTREE)], timeout=120)
        shutil.rmtree(WORKTREE, ignore_errors=True)
    run([GIT, "-C", str(REPO_DIR), "worktree", "prune"], timeout=60)


def verify_apk(apk: Path, code: int) -> bool:
    aapt = build_tool("aapt.exe")
    signer = build_tool("apksigner.bat")
    if not aapt or not signer:
        log("Android build-tools (aapt / apksigner) not found; refusing to install an unverified APK")
        return False
    out = run([aapt, "dump", "badging", str(apk)], timeout=60)[1]
    m = re.search(r"package: name='([^']+)' versionCode='(\d+)'", out)
    if not m or m.group(1) != PACKAGE or int(m.group(2)) != code:
        log(f"APK identity is wrong: {m.groups() if m else 'unreadable'}")
        return False
    env = dict(os.environ, JAVA_HOME=JAVA_HOME)
    sig = run([signer, "verify", "--print-certs", str(apk)], timeout=60, env=env)[1].lower()
    if PINNED_CERT_SHA256 not in sig.replace(":", ""):
        log("APK is not signed with the key the 14R was provisioned with; refusing to install")
        return False
    return True


# ------------------------------------------------------------------------------------------------ state / lock

def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def take_lock() -> bool:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists() and time.time() - LOCK_FILE.stat().st_mtime < LOCK_STALE_SECONDS:
        return False
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Keep the Redmi 14R on the fleet's agent version.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--tag")
    args = ap.parse_args()

    if not take_lock():
        return 0
    try:
        serial = find_14r()
        if not serial and not args.build_only:
            return 0  # phone not reachable right now: nothing to log every 15 minutes

        tag = args.tag or latest_release_tag()
        if not tag:
            return 0
        ver = version_of(tag)
        if not ver:
            log(f"release tag {tag!r} is not vMAJOR.MINOR.PATCH; ignoring")
            return 0
        name, code = ver

        have = installed_code(serial) if serial else None
        if serial and have is not None and have >= code:
            return 0
        state = load_state()
        failed = state.get("failed", {})
        if not args.build_only and failed.get("tag") == tag and time.time() - failed.get("at", 0) < BACKOFF_SECONDS:
            return 0

        if serial and not is_device_owner(serial):
            log(f"14R is on {have} and a newer release {tag} exists, but it is NOT Device Owner of {PACKAGE}: not touching it")
            return 1
        log(f"14R is on version code {have}, latest release is {tag} ({code}): update needed")
        if args.dry_run:
            log("dry run: would build from the tag, verify the signature and install over wireless adb")
            return 0

        apk = build_apk(tag, name, code)
        try:
            if not apk or not verify_apk(apk, code):
                state["failed"] = {"tag": tag, "at": time.time()}
                save_state(state)
                return 1
        finally:
            cleanup_worktree()
        log(f"built and verified {apk.name}")
        if args.build_only:
            return 0

        rc, out = run([ADB, "-s", serial, "install", "-r", str(apk)], timeout=300)
        if "Success" not in out:
            log(f"install failed: {out.strip()[-300:]}")
            state["failed"] = {"tag": tag, "at": time.time()}
            save_state(state)
            return 1
        time.sleep(20)
        now_code = installed_code(serial)
        owner = is_device_owner(serial)
        log(f"installed {tag}: now version code {now_code}, device owner {'yes' if owner else 'NO - check the phone'}")
        state.pop("failed", None)
        save_state(state)
        return 0 if now_code == code and owner else 1
    finally:
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())

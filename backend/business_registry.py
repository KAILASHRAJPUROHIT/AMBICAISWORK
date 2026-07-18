"""
business_registry.py — per-tenant registry for AMBIC Payment Auditor.

Each business gets its own SQLite database file (see database.py's
get_session_factory) plus a JSON profile here holding branding, alert
routing, and ingestion source config — mirrors the tenant_profile.py /
business_profile.py pattern used by the sibling AMBIC SmartQR and
Catalogue Studio products.

Session-token -> business-slug resolution also lives here (a tiny global
JSON index, deliberately NOT inside any tenant's own database) because a
request must be routed to the correct tenant database before it can look
its session token up inside that database's own `sessions` table — see
tenant_context.py.
"""
import os
import json
import re
import threading

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUSINESSES_DIR = os.path.join(BASE, "businesses")
os.makedirs(BUSINESSES_DIR, exist_ok=True)

_SESSION_INDEX_PATH = os.path.join(BUSINESSES_DIR, "_session_index.json")
_SESSION_INDEX_LOCK = threading.Lock()


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "business"


def _profile_path(slug: str) -> str:
    return os.path.join(BUSINESSES_DIR, slug, "profile.json")


def default_profile(business_name: str) -> dict:
    slug = slugify(business_name)
    return {
        "slug": slug,
        "business_name": business_name,
        # Replaces the old hardcoded personal Gmail address that every
        # critical/financial alert was force-sent to regardless of tenant.
        "alert_emails": [],
        # Replaces the hardcoded IMAP_* env vars — each business polls its
        # own bank-alert mailbox.
        "imap": {"server": "", "port": 993, "user": "", "password": "", "folder": "INBOX"},
        # Replaces the hardcoded EMAIL_HOST/etc — each business sends its
        # own OTP/notification mail from its own address.
        "smtp": {"host": "", "port": 587, "username": "", "password": ""},
        # Replaces the hardcoded \\PC2\AradhanaInvoicePDFs share path.
        "invoice_share_path": "",
    }


def save_profile(profile: dict) -> str:
    slug = profile.get("slug") or slugify(profile.get("business_name", "business"))
    profile["slug"] = slug
    d = os.path.join(BUSINESSES_DIR, slug)
    os.makedirs(d, exist_ok=True)
    path = _profile_path(slug)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    os.replace(tmp, path)
    return slug


def load_profile(slug: str) -> dict | None:
    if not slug:
        return None
    path = _profile_path(slug)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_businesses() -> list[str]:
    if not os.path.isdir(BUSINESSES_DIR):
        return []
    return sorted(
        d for d in os.listdir(BUSINESSES_DIR)
        if os.path.isfile(os.path.join(BUSINESSES_DIR, d, "profile.json"))
    )


# ── Session-token -> business-slug index ──────────────────────────────────
# A request carries only an opaque X-Session-Token header — before that
# token can be looked up inside a tenant's own `sessions` table, something
# has to know WHICH tenant's database to open first. This flat JSON index
# (outside every tenant's own DB, so genuinely global) is that lookup.
# Written at login (create_user_session in auth_service.py), removed at
# logout/expiry. Sized for "tens to low hundreds of businesses" — a flat
# JSON file with a lock is the right amount of infrastructure for that, not
# a dedicated session store.

def _load_session_index() -> dict:
    if not os.path.exists(_SESSION_INDEX_PATH):
        return {}
    try:
        with open(_SESSION_INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_session_index(index: dict):
    tmp = _SESSION_INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f)
    os.replace(tmp, _SESSION_INDEX_PATH)


def register_session(token: str, slug: str):
    with _SESSION_INDEX_LOCK:
        index = _load_session_index()
        index[token] = slug
        _save_session_index(index)


def resolve_session_slug(token: str) -> str | None:
    return _load_session_index().get(token)


def forget_session(token: str):
    with _SESSION_INDEX_LOCK:
        index = _load_session_index()
        if token in index:
            del index[token]
            _save_session_index(index)

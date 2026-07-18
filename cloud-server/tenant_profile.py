"""
tenant_profile.py — multi-tenant business configuration for AMBIC SmartQR.

Each business (tenant) gets a JSON file at tenants/<slug>/profile.json holding
its branding, social links, an optional voice-clip path, and two secrets:
  - admin_secret   — protects that tenant's /admin actions (retry/reprocess/clear)
  - agent_api_key  — what that shop's local print agent authenticates with when
                      polling for jobs, so one tenant's agent can never see
                      another tenant's print queue (see app.py's
                      /api/agent/jobs/pending auth check).

Mirrors the same pattern used in the CatalogueSaaS project's business_profile.py.
"""
import os
import re
import json
import secrets

from cryptography.fernet import Fernet

BASE = os.path.dirname(os.path.abspath(__file__))
TENANTS_DIR = os.path.join(BASE, "tenants")
os.makedirs(TENANTS_DIR, exist_ok=True)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "business"


def _profile_path(slug: str) -> str:
    return os.path.join(TENANTS_DIR, slug, "profile.json")


def default_profile(business_name: str) -> dict:
    slug = slugify(business_name)
    return {
        "business_name": business_name,
        "slug": slug,
        "logo_path": "",
        "brand_colors": {"primary": "#06142E", "accent": "#D4AF37"},
        "instagram_handle": "",
        "facebook_page": "",
        "google_review_url": "",
        "whatsapp_number": "",
        "phone_number": "",
        "voice_clip_path": "",
        "admin_secret": secrets.token_urlsafe(12),
        "agent_api_key": secrets.token_urlsafe(24),
        # Every tenant's uploaded documents are encrypted at rest with this
        # key regardless of secure_documents — see app.py's _encrypt_bytes /
        # _decrypt_bytes. secure_documents additionally deletes the file the
        # moment a job completes instead of keeping it for 30 days.
        "encryption_key": Fernet.generate_key().decode(),
        "secure_documents": False,
    }


def save_profile(profile: dict) -> str:
    slug = profile.get("slug") or slugify(profile.get("business_name", "business"))
    profile["slug"] = slug
    d = os.path.join(TENANTS_DIR, slug)
    os.makedirs(d, exist_ok=True)
    path = _profile_path(slug)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    os.replace(tmp, path)
    return slug


def load_profile(slug: str) -> dict | None:
    path = _profile_path(slug)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_tenants() -> list[str]:
    if not os.path.isdir(TENANTS_DIR):
        return []
    return sorted(
        d for d in os.listdir(TENANTS_DIR)
        if os.path.isfile(os.path.join(TENANTS_DIR, d, "profile.json"))
    )


def find_by_agent_key(agent_api_key: str) -> dict | None:
    """Used by /api/agent/jobs/pending to resolve which tenant a polling
    print agent belongs to, from the key it presents."""
    if not agent_api_key:
        return None
    for slug in list_tenants():
        profile = load_profile(slug)
        if profile and secrets.compare_digest(profile.get("agent_api_key", ""), agent_api_key):
            return profile
    return None


# ── Active-tenant helper (query-param / cookie based, same pattern as
# CatalogueSaaS's business_profile.resolve_active_slug) ──────────────────────

def resolve_active_slug(request) -> str | None:
    slug = request.args.get("tenant") or request.cookies.get("tenant_slug")
    if slug and load_profile(slug):
        return slug
    tenants = list_tenants()
    if len(tenants) == 1:
        return tenants[0]
    return None

"""
tenant_context.py — resolves which business a request belongs to.

Two cases:
  1. Pre-authentication (login/verify/resend-otp): no session token exists
     yet, so the frontend must say which business it's logging into, via
     an X-Business-Slug header or ?business= query param.
  2. Authenticated (everything else): the X-Session-Token header is looked
     up against business_registry's global session index to find which
     tenant's own `sessions` table it belongs to — see that module's
     docstring for why this index has to live outside every tenant's own
     database.

Falls back to the sole registered business if there is exactly one and
neither of the above resolves anything — the same "single-tenant
convenience" fallback used by business_profile.resolve_active_slug in the
sibling AMBIC products, useful while only one business (or none yet, during
initial setup) has been onboarded.
"""
from fastapi import Request

from backend import business_registry as br


def resolve_tenant_slug(request: Request) -> str | None:
    slug = request.headers.get("X-Business-Slug") or request.query_params.get("business")
    if slug and br.load_profile(slug):
        return slug

    token = request.headers.get("X-Session-Token")
    if token:
        slug = br.resolve_session_slug(token)
        if slug and br.load_profile(slug):
            return slug

    businesses = br.list_businesses()
    if len(businesses) == 1:
        return businesses[0]

    return None

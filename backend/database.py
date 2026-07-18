"""
database.py — per-tenant SQLite database resolution.

Every business gets its own SQLite file at businesses/<slug>/data.db,
resolved via get_session_factory(slug). This used to be a single global
engine/SessionLocal bound to one fixed on-disk file (aradhana_dev.db) —
correct when this was a single-business tool, but wrong for a SaaS product
where one process serves many businesses' financial records. Splitting by
file rather than adding a business_id column to every table (the other
approach) means the ~50 existing API endpoints and the reconciliation
engine's query code do not need to be individually audited for a missing
tenant filter — a genuinely higher-risk class of bug on a financial-audit
system than the operational cost of per-tenant files.

get_db() and security_middleware in review_api.py resolve which slug a
request belongs to (see tenant_context.py) and call get_session_factory(
slug) — every existing `db.query(...)` call in every route handler is
then automatically scoped to that one tenant's data, with zero changes to
the handler itself.
"""
import os
import threading
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUSINESSES_DIR = os.path.join(BASE_DIR, "businesses")
os.makedirs(BUSINESSES_DIR, exist_ok=True)

Base = declarative_base()

# Explicit override for tests / single-DB debugging (e.g.
# DATABASE_URL=sqlite:///:memory: or a temp file) — bypasses per-tenant
# file resolution entirely and every slug maps to the same engine. This env
# var was documented in .env.example since before the SaaS conversion but
# never actually read anywhere; that's fixed here, not just added.
_FORCED_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

_ENGINES: dict[str, "Engine"] = {}
_SESSION_FACTORIES: dict[str, sessionmaker] = {}
_ENGINE_LOCK = threading.Lock()


def business_db_path(slug: str) -> str:
    return os.path.abspath(os.path.join(BUSINESSES_DIR, slug, "data.db"))


def get_session_factory(slug: str) -> sessionmaker:
    """Returns a cached sessionmaker bound to this tenant's own database
    file, creating the engine (and the file's schema, via
    Base.metadata.create_all) on first use for that slug. Thread-safe:
    the server runs threaded, and two requests for a brand-new tenant's
    first-ever session could otherwise race on engine creation."""
    cache_key = slug if not _FORCED_DATABASE_URL else "_forced_"
    if cache_key in _SESSION_FACTORIES:
        return _SESSION_FACTORIES[cache_key]

    with _ENGINE_LOCK:
        if cache_key in _SESSION_FACTORIES:  # re-check after acquiring the lock
            return _SESSION_FACTORIES[cache_key]

        if _FORCED_DATABASE_URL:
            url = _FORCED_DATABASE_URL
        else:
            db_path = business_db_path(slug)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            url = f"sqlite:///{db_path}"

        engine = create_engine(url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)  # no-op if tables already exist

        factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        _ENGINES[cache_key] = engine
        _SESSION_FACTORIES[cache_key] = factory
        return factory


def get_engine(slug: str):
    get_session_factory(slug)  # ensures it's created/cached
    cache_key = slug if not _FORCED_DATABASE_URL else "_forced_"
    return _ENGINES[cache_key]


def _default_slug() -> str:
    """Resolves a 'default tenant' for code that hasn't been converted to
    iterate every business yet — the three background pollers
    (pdf_ingestion/email_poller/sms_poller) and invoice_lifecycle still
    call SessionLocal()/engine directly rather than taking a slug, exactly
    like they did before this file had a tenant concept at all. That
    conversion (looping each poller over every business with auto-mode
    configured, instead of one hardcoded mailbox/share) is tracked
    separately — this function exists only so those four modules keep
    importing and running, unchanged, in the meantime. Resolves to the
    forced single-DB override if set (tests), else the sole registered
    business, else raises — there is no reasonable default with zero or
    multiple businesses and no explicit selection."""
    if _FORCED_DATABASE_URL:
        return "_forced_"
    from backend import business_registry
    businesses = business_registry.list_businesses()
    if len(businesses) == 1:
        return businesses[0]
    raise RuntimeError(
        f"No default tenant: {len(businesses)} businesses registered. "
        "This code path (pdf_ingestion/email_poller/sms_poller/"
        "invoice_lifecycle) hasn't been converted to per-tenant operation "
        "yet and only works with exactly one registered business."
    )


class _DefaultTenantSessionLocal:
    """Drop-in replacement for the old module-level `SessionLocal`
    sessionmaker — callable exactly the same way (`SessionLocal()` returns
    a new Session) — for the not-yet-converted callers described in
    _default_slug's docstring above."""
    def __call__(self):
        return get_session_factory(_default_slug())()


SessionLocal = _DefaultTenantSessionLocal()


class _DefaultTenantEngineProxy:
    """Same idea as _DefaultTenantSessionLocal but for the (rarer) direct
    `engine` import — used by pdf_ingestion.py. Proxies attribute access
    through to the real, lazily-resolved Engine so existing code like
    `engine.connect()` keeps working unchanged."""
    def __getattr__(self, name):
        return getattr(get_engine(_default_slug()), name)


engine = _DefaultTenantEngineProxy()


def check_db_integrity(slug: str) -> tuple[bool, str | None]:
    """Fail startup/request if this tenant's configured database does not
    contain the required tables. Unlike the old single-tenant version, a
    missing file is no longer fatal — get_session_factory auto-provisions a
    fresh tenant's schema on first use, which is the correct behavior for
    onboarding a new business rather than a sign of a broken deployment."""
    try:
        engine = get_engine(slug)
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        required = ["bills", "bank_alerts", "sms_alerts", "users"]
        for table in required:
            if table not in existing_tables:
                return False, f"Required table '{table}' missing for tenant '{slug}'"
        return True, None
    except Exception as e:
        return False, f"Database integrity check failed for tenant '{slug}': {e}"

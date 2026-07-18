"""
conftest.py — test isolation for the per-tenant database layer.

database.py reads the DATABASE_URL env var at import time
(_FORCED_DATABASE_URL) to decide whether to resolve a real per-tenant file
under businesses/<slug>/data.db, or route every slug to one forced
database instead. Setting it here — before pytest imports any test module,
which is guaranteed since conftest.py always loads first — means the whole
suite runs against one isolated SQLite file instead of ever touching real
tenant data, and code that still calls the legacy SessionLocal()/engine
shims (see database.py's _default_slug docstring) keeps working without
needing exactly one business registered, since the forced override
bypasses that check entirely.

Must be set before ANY `import backend.*` happens anywhere in the test
session, which is why this file does it at module level before the
pytest import below, and why pytest.ini's testpaths/rootdir must not
import backend modules any earlier than conftest.py itself.
"""
import os
import shutil
import tempfile

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_TEST_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB_PATH}")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

# business_registry.py reads/writes a real on-disk businesses/ directory —
# unaffected by DATABASE_URL, since tenant PROFILES (branding, IMAP config)
# are separate from tenant DATA (which DATABASE_URL's forced override does
# isolate). Redirecting BUSINESSES_DIR to a temp dir too means tests never
# touch real registered businesses, and registering one tenant here gives
# every test the same implicit single-tenant world the app already falls
# back to (resolve_tenant_slug's "exactly one business" convenience) — most
# of this suite predates the multi-tenant conversion and assumes exactly
# that, same as it assumed one hardcoded database file before.
from backend import business_registry

business_registry.BUSINESSES_DIR = tempfile.mkdtemp()
business_registry._SESSION_INDEX_PATH = os.path.join(business_registry.BUSINESSES_DIR, "_session_index.json")

_TEST_PROFILE = business_registry.default_profile("Test Business")
_TEST_PROFILE["slug"] = "test-tenant"
business_registry.save_profile(_TEST_PROFILE)

# backend.models registers every ORM class onto Base.metadata as a side
# effect of being imported — Base itself starts with zero tables known.
# get_session_factory() caches its engine on first call and only runs
# Base.metadata.create_all() at that moment, so if the very first call
# anywhere in the test session happened before models were imported, the
# cached engine would be permanently bound to an empty schema — no amount
# of importing models later fixes an already-cached, already-"created"
# engine. Importing models AND forcing that first call here, in conftest,
# guarantees correct ordering regardless of which test file pytest happens
# to collect or run first.
import backend.models  # noqa: F401
from backend.database import get_session_factory as _get_session_factory
_get_session_factory("test-tenant")


@pytest.fixture
def db_session():
    """A fresh SQLAlchemy session against the shared test database. The
    slug is arbitrary and irrelevant — DATABASE_URL's forced override
    (see module docstring) routes every slug to the same file."""
    from backend.database import get_session_factory
    session = get_session_factory("test-tenant")()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncates every table after each test so tests don't see each
    other's rows, without paying for a fresh DB file per test."""
    yield
    from backend.database import get_engine, Base
    engine = get_engine("test-tenant")
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())

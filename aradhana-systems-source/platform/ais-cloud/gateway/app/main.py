from __future__ import annotations

import json
import os
import secrets
import sqlite3
from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from pathlib import Path
from typing import Generator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


SOURCE_PATH = Path(__file__).resolve()
ROOT = SOURCE_PATH.parents[3] if len(SOURCE_PATH.parents) > 3 else Path("/")
LOCAL_REGISTRY_PATH = ROOT / "core" / "ais.registry.json"
REGISTRY_PATH = Path(os.getenv("AIS_REGISTRY_PATH", str(LOCAL_REGISTRY_PATH if LOCAL_REGISTRY_PATH.exists() else "/app/registry/ais.registry.json")))
ENVIRONMENT = os.getenv("AIS_ENVIRONMENT", "development").lower()
DATABASE_URL = os.getenv("AIS_DATABASE_URL", "sqlite:///./data/ais-cloud.db")
AGENT_TOKEN = os.getenv("AIS_AGENT_TOKEN", "")
OWNER_TOKEN = os.getenv("AIS_OWNER_TOKEN", "")
ADMIN_CREDENTIAL_HASH = os.getenv("AIS_ADMIN_CREDENTIAL_HASH", "")
SESSION_SECRET = os.getenv("AIS_SESSION_SECRET", "")


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, url: str) -> None:
        self.url = url
        self.postgres = url.startswith(("postgres://", "postgresql://"))
        if self.postgres:
            import psycopg  # installed by the container image

            self._psycopg = psycopg
        else:
            path = url.removeprefix("sqlite:///")
            self.path = Path(path).expanduser().resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Generator[object, None, None]:
        if self.postgres:
            with self._psycopg.connect(self.url, autocommit=True) as connection:
                yield connection
        else:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.connection() as connection:
            connection.execute(self._sql(sql), params)

    def all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.connection() as connection:
            cursor = connection.execute(self._sql(sql), params)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.postgres else sql

    def initialise(self) -> None:
        if self.postgres:
            schema = [
                "CREATE TABLE IF NOT EXISTS agent_heartbeats (device_id TEXT PRIMARY KEY, hostname TEXT NOT NULL, ip_address TEXT NOT NULL, status TEXT NOT NULL, capabilities_json TEXT NOT NULL, observed_at TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS audit_events (id BIGSERIAL PRIMARY KEY, event_type TEXT NOT NULL, severity TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
            ]
        else:
            schema = [
                "CREATE TABLE IF NOT EXISTS agent_heartbeats (device_id TEXT PRIMARY KEY, hostname TEXT NOT NULL, ip_address TEXT NOT NULL, status TEXT NOT NULL, capabilities_json TEXT NOT NULL, observed_at TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, severity TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
            ]
        for statement in schema:
            self.execute(statement)


store = Store(DATABASE_URL)
store.initialise()


class Heartbeat(BaseModel):
    device_id: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    hostname: str = Field(min_length=1, max_length=128)
    ip_address: str = Field(min_length=3, max_length=64)
    status: Literal["healthy", "warning", "error"]
    capabilities: list[str] = Field(default_factory=list, max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


def registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def audit(event_type: str, severity: str, actor_type: str, actor_id: str, payload: dict) -> None:
    store.execute(
        "INSERT INTO audit_events(event_type,severity,actor_type,actor_id,payload_json,created_at) VALUES(?,?,?,?,?,?)",
        (event_type, severity, actor_type, actor_id, json.dumps(payload, separators=(",", ":")), now()),
    )


def bearer(value: str | None) -> str:
    if not value or not value.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    return value.removeprefix("Bearer ")


def session_signature(payload: bytes) -> bytes:
    return hmac_new(SESSION_SECRET.encode("utf-8"), payload, sha256).digest()


def issue_session(username: str) -> str:
    if not SESSION_SECRET:
        raise HTTPException(503, "Owner session login is not configured")
    expires_at = int(datetime.now(UTC).timestamp()) + 8 * 60 * 60
    payload = json.dumps({"sub": username, "exp": expires_at}, separators=(",", ":")).encode("utf-8")
    return urlsafe_b64encode(payload).decode("ascii").rstrip("=") + "." + urlsafe_b64encode(session_signature(payload)).decode("ascii").rstrip("=")


def valid_session(value: str | None) -> bool:
    if not value or not SESSION_SECRET or "." not in value:
        return False
    payload_part, signature_part = value.split(".", 1)
    try:
        payload = urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
        signature = urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
        details = json.loads(payload)
        return compare_digest(signature, session_signature(payload)) and int(details["exp"]) > int(datetime.now(UTC).timestamp())
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def owner_access(request: Request, authorization: str | None = Header(default=None)) -> str:
    if authorization:
        token = bearer(authorization)
        if OWNER_TOKEN and secrets.compare_digest(token, OWNER_TOKEN):
            return "owner-token"
    if valid_session(request.cookies.get("ais_owner_session")):
        return "owner-session"
    raise HTTPException(401, "Owner authentication required")


def agent_access(authorization: str | None = Header(default=None)) -> str:
    token = bearer(authorization)
    if not AGENT_TOKEN or not secrets.compare_digest(token, AGENT_TOKEN):
        raise HTTPException(403, "Agent access denied")
    return "agent"


app = FastAPI(title="AIS Gateway", version="0.1.0", docs_url=None, redoc_url=None)
origins = [origin.strip() for origin in os.getenv("AIS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def production_guard(request: Request, call_next):
    has_owner_auth = bool(OWNER_TOKEN or (ADMIN_CREDENTIAL_HASH and SESSION_SECRET))
    if ENVIRONMENT == "production" and (not AGENT_TOKEN or not has_owner_auth):
        return HTMLResponse("AIS gateway is not configured.", status_code=503)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "component": "ais-gateway", "environment": ENVIRONMENT, "timestamp": now()}


@app.get("/api/v1/auth/status")
def auth_status(request: Request) -> dict:
    return {"authenticated": valid_session(request.cookies.get("ais_owner_session")), "login_configured": bool(ADMIN_CREDENTIAL_HASH and SESSION_SECRET)}


@app.post("/api/v1/auth/login")
def login(item: LoginRequest):
    if not ADMIN_CREDENTIAL_HASH or not SESSION_SECRET:
        raise HTTPException(503, "Owner session login is not configured")
    candidate = sha256(f"{item.username.strip().lower()}:{item.password}".encode("utf-8")).hexdigest()
    if not compare_digest(candidate, ADMIN_CREDENTIAL_HASH):
        raise HTTPException(401, "Invalid credentials")
    response = {"authenticated": True, "expires_in_seconds": 8 * 60 * 60}
    from fastapi.responses import JSONResponse

    result = JSONResponse(response)
    result.set_cookie("ais_owner_session", issue_session(item.username.strip().lower()), httponly=True, secure=ENVIRONMENT == "production", samesite="strict", max_age=8 * 60 * 60, path="/")
    audit("owner.login", "info", "user", item.username.strip().lower(), {})
    return result


@app.post("/api/v1/auth/logout")
def logout() -> object:
    from fastapi.responses import JSONResponse

    result = JSONResponse({"authenticated": False})
    result.delete_cookie("ais_owner_session", path="/")
    return result


@app.get("/api/v1/dashboard")
def dashboard(_: str = Depends(owner_access)) -> dict:
    data = registry()
    devices = store.all("SELECT device_id,hostname,ip_address,status,capabilities_json,observed_at FROM agent_heartbeats ORDER BY observed_at DESC")
    events = store.all("SELECT id,event_type,severity,actor_type,actor_id,payload_json,created_at FROM audit_events ORDER BY id DESC LIMIT 30")
    return {
        "organization": data["organization"],
        "platform": data["platform"],
        "projects": data["projects"],
        "plugins": data["plugins"],
        "services": data["services"],
        "devices": [{**item, "capabilities": json.loads(item.pop("capabilities_json"))} for item in devices],
        "events": [{**item, "payload": json.loads(item.pop("payload_json"))} for item in events],
    }


@app.get("/api/v1/plugins")
def plugins(_: str = Depends(owner_access)) -> dict:
    return {"plugins": registry()["plugins"]}


@app.post("/api/v1/agents/heartbeat", status_code=202)
def heartbeat(item: Heartbeat, _: str = Depends(agent_access)) -> dict:
    observed_at = now()
    store.execute(
        "INSERT INTO agent_heartbeats(device_id,hostname,ip_address,status,capabilities_json,observed_at) VALUES(?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET hostname=excluded.hostname,ip_address=excluded.ip_address,status=excluded.status,capabilities_json=excluded.capabilities_json,observed_at=excluded.observed_at",
        (item.device_id, item.hostname, item.ip_address, item.status, json.dumps(item.capabilities), observed_at),
    )
    audit("agent.heartbeat", "info", "agent", item.device_id, item.model_dump())
    return {"accepted": True, "observed_at": observed_at}


@app.get("/", response_class=HTMLResponse)
@app.get("/payments", response_class=HTMLResponse)
@app.get("/documents", response_class=HTMLResponse)
@app.get("/print", response_class=HTMLResponse)
@app.get("/catalogue", response_class=HTMLResponse)
@app.get("/gold", response_class=HTMLResponse)
def portal() -> str:
    return """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>AIS — Aradhana Jewellers</title><style>body{margin:0;background:#07162b;color:#f7f8fa;font-family:Arial,sans-serif}main{max-width:760px;margin:12vh auto;padding:32px}h1{font-size:44px;margin:0;color:#f4c857}p{line-height:1.6;color:#bfd0e4}.tag{display:inline-block;padding:7px 10px;background:#17375e;border-radius:20px}nav{display:flex;gap:10px;flex-wrap:wrap;margin-top:28px}a{color:#f4c857;text-decoration:none;border:1px solid #315a87;border-radius:8px;padding:10px 13px}</style></head><body><main><span class='tag'>Aradhana Jewellers</span><h1>AIS</h1><p>Aradhana Intelligence System is being moved to its permanent cloud-ready foundation. Local operational systems remain active during the controlled migration.</p><nav><a href='/payments'>Payments</a><a href='/documents'>Documents</a><a href='/print'>Print</a><a href='/catalogue'>Catalogue</a><a href='/gold'>Gold rates</a></nav></main></body></html>"""

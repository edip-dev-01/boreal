"""Local-only Boreal API. The role selector is a demonstration, not real identity."""
import hashlib
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import AskRequest, Freshness, LoginRequest, Role
from .query import answer_question, detail_record, iso, parse_bbox, project_records
from .repository import PostgresRepository, Repository

LOGGER = logging.getLogger(__name__)
COOKIE_NAME = "boreal_demo_session"


@dataclass(frozen=True)
class Session:
    role: Role
    csrf_token: str
    expires: float


class Sessions:
    def __init__(self, lifetime=3600, capacity=1000):
        self.values: dict[str, Session] = {}
        self.lock = threading.Lock()
        self.lifetime = lifetime
        self.capacity = capacity

    @staticmethod
    def key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def get(self, token: str | None) -> Session | None:
        if not token or len(token) > 100:
            return None
        with self.lock:
            key = self.key(token)
            value = self.values.get(key)
            if value and value.expires > time.monotonic():
                return value
            self.values.pop(key, None)
        return None

    def remove(self, token: str | None):
        if token:
            with self.lock:
                self.values.pop(self.key(token), None)

    def create(self, role: Role) -> tuple[str, Session]:
        token = secrets.token_urlsafe(32)
        session = Session(role, secrets.token_urlsafe(32), time.monotonic() + self.lifetime)
        with self.lock:
            self.values = {key: value for key, value in self.values.items() if value.expires > time.monotonic()}
            if len(self.values) >= self.capacity:
                raise HTTPException(503, "Demo session capacity reached; retry after a session expires")
            self.values[self.key(token)] = session
        return token, session


def create_app(repository: Repository | None = None, *, testing: bool = False, as_of: datetime | None = None) -> FastAPI:
    if repository is None:
        # Require the DB configuration at startup; never use the ingest/owner URL.
        url = os.environ.get("DATABASE_URL", "")
        repository = PostgresRepository(url)
    app = FastAPI(title="Boreal local synthetic demo API", version="0.1.0", docs_url=None, openapi_url="/api/openapi.json", redoc_url=None)
    app.state.repository = repository
    app.state.sessions = Sessions()
    app.state.testing = testing
    fixed = as_of or datetime.fromisoformat(os.environ.get("AS_OF", "2026-10-11T12:00:00+00:00").replace("Z", "+00:00"))
    if fixed.tzinfo is None:
        raise RuntimeError("AS_OF must include an explicit timezone")
    app.state.as_of = fixed.astimezone(timezone.utc)
    origins = {origin.strip().rstrip("/") for origin in os.environ.get("DEMO_ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",") if origin.strip()}
    if testing:
        origins.add("http://testserver")
    allowed_hosts = [host.strip() for host in os.environ.get("DEMO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
    if testing:
        allowed_hosts.append("testserver")
    if "*" in allowed_hosts or "*" in origins:
        raise RuntimeError("Wildcard hosts/origins are not permitted")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    secure_cookie = os.environ.get("DEMO_SECURE_COOKIE", "false").lower() == "true"

    @app.middleware("http")
    async def security_headers_and_origins(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("origin") not in origins:
                return JSONResponse({"detail": "A trusted same-origin request is required"}, status_code=403)
            if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
                return JSONResponse({"detail": "Cross-site requests are rejected"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def optional_session(request: Request) -> Session | None:
        return app.state.sessions.get(request.cookies.get(COOKIE_NAME))

    def require_session(request: Request) -> Session:
        session = optional_session(request)
        if not session:
            raise HTTPException(401, "Select a demo role to start a session")
        return session

    def mutation_session(request: Request, session: Annotated[Session, Depends(require_session)]) -> Session:
        token = request.headers.get("X-CSRF-Token", "")
        if not token.isascii() or not secrets.compare_digest(token, session.csrf_token):
            raise HTTPException(403, "Missing or invalid CSRF token")
        return session

    def parsed_bbox(value):
        try:
            return parse_bbox(value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def load_view(session, q="", freshness="all", bbox=None):
        bounds = parsed_bbox(bbox)
        try:
            dataset = app.state.repository.load(session.role, bounds)
        except Exception:
            LOGGER.exception("Database read failed")
            raise HTTPException(503, "The demo datastore is temporarily unavailable") from None
        return dataset, project_records(dataset, app.state.as_of, q, freshness, bounds)

    @app.get("/api/health")
    def health():
        try:
            app.state.repository.probe()
        except Exception:
            LOGGER.exception("Datastore health check failed")
            raise HTTPException(503, "Datastore is unavailable or not correctly configured") from None
        return {"status": "ok", "product": "Boreal", "synthetic": True, "runtime": "test-memory" if testing else "postgres", "as_of": iso(app.state.as_of)}

    @app.get("/api/session")
    def session_info(request: Request):
        session = optional_session(request)
        return {"authenticated": True, "role": session.role, "csrf_token": session.csrf_token} if session else {"authenticated": False}

    @app.post("/api/login")
    def login(payload: LoginRequest, request: Request, response: Response):
        # Anyone with local access may select either role. This is NOT production auth.
        app.state.sessions.remove(request.cookies.get(COOKIE_NAME))
        token, session = app.state.sessions.create(payload.role)
        response.set_cookie(COOKIE_NAME, token, max_age=app.state.sessions.lifetime, httponly=True, samesite="strict", secure=secure_cookie, path="/api")
        return {"authenticated": True, "role": session.role, "csrf_token": session.csrf_token}

    @app.post("/api/logout", status_code=204)
    def logout(request: Request, response: Response, session: Annotated[Session, Depends(mutation_session)]):
        app.state.sessions.remove(request.cookies.get(COOKIE_NAME))
        response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, secure=secure_cookie, samesite="strict")

    @app.get("/api/records")
    @app.get("/api/search")
    def records(session: Annotated[Session, Depends(require_session)], q: str = Query(default="", max_length=200), freshness: Freshness = "all", bbox: str | None = Query(default=None, max_length=200)):
        _, items = load_view(session, q, freshness, bbox)
        return {"records": items, "count": len(items), "as_of": iso(app.state.as_of)}

    @app.get("/api/records/{record_id}")
    def record_detail(record_id: str, session: Annotated[Session, Depends(require_session)]):
        dataset, items = load_view(session)
        item = next((record for record in items if record["id"] == record_id), None)
        if item is None:
            # Deliberately identical response for inaccessible and nonexistent IDs.
            raise HTTPException(404, "Record not found")
        return {**detail_record(dataset, item), "as_of": iso(app.state.as_of)}

    @app.get("/api/sources/{source_id}")
    def source_detail(source_id: str, session: Annotated[Session, Depends(require_session)]):
        dataset, items = load_view(session)
        source = next((source for source in dataset.sources if source.id == source_id), None)
        if source is None:
            raise HTTPException(404, "Source not found")
        return {**source.model_dump(exclude={"access"}), "records": [{"record_id": item["id"], "label": item["name"]} for item in items if source_id in item["source_ids"]], "as_of": iso(app.state.as_of)}

    @app.get("/api/counts")
    def counts(session: Annotated[Session, Depends(require_session)], q: str = Query(default="", max_length=200), freshness: Freshness = "all", bbox: str | None = Query(default=None, max_length=200)):
        _, items = load_view(session, q, freshness, bbox)
        return {"count": len(items), "mapped": sum(r["longitude"] is not None for r in items), "fresh": sum(r["freshness"] == "fresh" for r in items), "stale": sum(r["freshness"] == "stale" for r in items), "missing_timestamp": sum(r["freshness"] == "missing" for r in items), "missing_coordinates": sum("coordinates" in r["missing_fields"] for r in items), "conflicts": sum(r["conflict"] for r in items), "as_of": iso(app.state.as_of)}

    @app.get("/api/map")
    def map_geojson(session: Annotated[Session, Depends(require_session)], q: str = Query(default="", max_length=200), freshness: Freshness = "all", bbox: str | None = Query(default=None, max_length=200)):
        _, items = load_view(session, q, freshness, bbox)
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "id": r["id"], "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]}, "properties": r} for r in items if r["longitude"] is not None], "count": len(items), "unmapped_count": sum(r["longitude"] is None for r in items), "as_of": iso(app.state.as_of)}

    @app.post("/api/ask")
    def ask(payload: AskRequest, session: Annotated[Session, Depends(mutation_session)]):
        _, items = load_view(session, payload.q, payload.freshness, payload.bbox)
        return answer_question(payload.question, items, app.state.as_of)

    return app



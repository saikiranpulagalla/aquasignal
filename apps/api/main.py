from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from signallock.benchmark.runner import run_demo_benchmark
from signallock.cap.mapper import cap_info_seed_contract
from signallock.cap.parser import parse_cap_xml
from signallock.cap.verifier import verify_cap_alerts
from signallock.contracts.authority import (
    AuthorityTokenError,
    issue_authority_token,
    semantic_contract_blob,
    verify_authority_token,
)
from signallock.contracts.provenance import validate_provenance
from signallock.contracts.schema import SafetyContract
from signallock.providers.extraction_service import ExtractionService
from signallock.evaluation.release import project_version
from signallock.transforms.service import TransformationService
from signallock.verification.engine import VerificationEngine


ROOT = Path(__file__).resolve().parents[2]
WEB_INDEX = ROOT / "web" / "index.html"
WEB_APP = ROOT / "web" / "app.js"
WEB_CSS = ROOT / "web" / "app.css"
MAX_ALERT_CHARS = int(os.getenv("SIGNALLOCK_MAX_ALERT_CHARS", "12000"))
_AUTHORITY_SECRET_CONFIGURED = bool(os.getenv("SIGNALLOCK_AUTHORITY_SECRET", ""))
_AUTHORITY_SECRET = os.getenv("SIGNALLOCK_AUTHORITY_SECRET", "").encode("utf-8") or secrets.token_bytes(32)
_LIVE_PROVIDER_TOKEN = os.getenv("SIGNALLOCK_LIVE_PROVIDER_TOKEN")
_RATE_WINDOW_SECONDS = 60.0
_RATE_LIMIT = int(os.getenv("SIGNALLOCK_LIVE_PROVIDER_RATE_LIMIT", "20"))
_LIVE_CALLS: dict[str, deque[float]] = defaultdict(deque)
_LIVE_SESSION_TTL_SECONDS = int(os.getenv("SIGNALLOCK_LIVE_SESSION_TTL_SECONDS", "900"))
_LIVE_SESSIONS: dict[str, float] = {}

app = FastAPI(
    title="SignalLock AI",
    version=project_version(ROOT),
    description="Protective-action integrity verification for AI-transformed emergency alerts.",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _valid_live_session(token: str | None) -> bool:
    if not token:
        return False
    now = time.monotonic()
    expired = [value for value, expiry in _LIVE_SESSIONS.items() if expiry <= now]
    for value in expired:
        _LIVE_SESSIONS.pop(value, None)
    expiry = _LIVE_SESSIONS.get(token)
    return bool(expiry and expiry > now)


def _guard_live_provider(request: Request, provider: str, supplied_token: str | None) -> None:
    if provider != "openai":
        return
    host = request.client.host if request.client else "unknown"
    local = host in {"127.0.0.1", "::1", "localhost", "testclient"}
    if _LIVE_PROVIDER_TOKEN:
        cookie_token = request.cookies.get("signallock_demo_session")
        master_ok = bool(supplied_token and secrets.compare_digest(supplied_token, _LIVE_PROVIDER_TOKEN))
        session_ok = _valid_live_session(cookie_token)
        if not (master_ok or session_ok):
            raise HTTPException(status_code=403, detail="Live provider endpoint requires a valid demo session")
        if not _AUTHORITY_SECRET_CONFIGURED:
            raise HTTPException(status_code=503, detail="Public live-provider mode requires a stable SIGNALLOCK_AUTHORITY_SECRET")
    elif not local:
        raise HTTPException(status_code=403, detail="Live provider calls are disabled for public clients unless SIGNALLOCK_LIVE_PROVIDER_TOKEN is configured")

    now = time.monotonic()
    q = _LIVE_CALLS[host]
    while q and now - q[0] > _RATE_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Live provider rate limit exceeded")
    q.append(now)


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)
    language: str = Field(default="en", min_length=2, max_length=20)
    provider: str = Field(default="heuristic", pattern="^(heuristic|openai)$")
    source_id: str | None = None


class VerifyRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)
    candidate_text: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)
    source_language: str = "en"
    candidate_language: str = "en"
    provider: str = Field(default="heuristic", pattern="^(heuristic|openai)$")


class VerifyAgainstContractRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)
    source_contract: SafetyContract
    authority_token: str | None = None
    candidate_text: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)
    candidate_language: str = Field(default="en", min_length=2, max_length=20)
    provider: str = Field(default="heuristic", pattern="^(heuristic|openai)$")


class TransformRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_ALERT_CHARS)
    mode: str = Field(pattern="^(simplify|sms|translate)$")
    language: str | None = None
    source_language: str = Field(default="en", min_length=2, max_length=20)
    max_chars: int = Field(default=360, ge=80, le=1000)
    provider: str = Field(default="heuristic", pattern="^(heuristic|openai)$")


class CAPRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=1_000_000)


class CAPVerifyRequest(BaseModel):
    source_xml: str = Field(min_length=1, max_length=1_000_000)
    candidate_xml: str = Field(min_length=1, max_length=1_000_000)
    source_info_index: int = Field(default=0, ge=0)
    candidate_info_index: int = Field(default=0, ge=0)


@app.get("/")
def home():
    return FileResponse(WEB_INDEX)


@app.get("/app.js")
def app_js():
    return FileResponse(WEB_APP, media_type="application/javascript")


@app.get("/app.css")
def app_css():
    return FileResponse(WEB_CSS, media_type="text/css")


@app.get("/health")
def health():
    return {"status": "ok", "service": "signallock", "version": app.version, "default_provider": os.getenv("SIGNALLOCK_PROVIDER", "heuristic")}


@app.post("/api/live-session")
def live_session(request: Request, x_signallock_demo_token: str | None = Header(default=None)):
    if not _LIVE_PROVIDER_TOKEN:
        raise HTTPException(status_code=404, detail="Live demo session authentication is not configured")
    if not _AUTHORITY_SECRET_CONFIGURED:
        raise HTTPException(status_code=503, detail="Set SIGNALLOCK_AUTHORITY_SECRET before enabling public live-provider mode")
    if not x_signallock_demo_token or not secrets.compare_digest(x_signallock_demo_token, _LIVE_PROVIDER_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid live demo token")
    from fastapi.responses import JSONResponse
    capability = secrets.token_urlsafe(32)
    _LIVE_SESSIONS[capability] = time.monotonic() + _LIVE_SESSION_TTL_SECONDS
    response = JSONResponse({"status": "ok", "expires_in_seconds": _LIVE_SESSION_TTL_SECONDS})
    response.set_cookie(
        "signallock_demo_session", capability, httponly=True, secure=True,
        samesite="strict", max_age=_LIVE_SESSION_TTL_SECONDS, path="/"
    )
    return response


@app.post("/api/extract", response_model=SafetyContract)
async def extract(req: ExtractRequest, request: Request, x_signallock_demo_token: str | None = Header(default=None)):
    _guard_live_provider(request, req.provider, x_signallock_demo_token)
    try:
        return await ExtractionService(req.provider).extract(req.text, language=req.language, source_id=req.source_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/extract-authority")
async def extract_authority(req: ExtractRequest, request: Request, x_signallock_demo_token: str | None = Header(default=None)):
    _guard_live_provider(request, req.provider, x_signallock_demo_token)
    try:
        contract = await ExtractionService(req.provider).extract(req.text, language=req.language, source_id=req.source_id or "authoritative-source")
        token = issue_authority_token(_AUTHORITY_SECRET, req.text, contract)
        return {"source_contract": contract.model_dump(mode="json"), "authority_token": token}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/verify")
async def verify(req: VerifyRequest, request: Request, x_signallock_demo_token: str | None = Header(default=None)):
    _guard_live_provider(request, req.provider, x_signallock_demo_token)
    try:
        service = ExtractionService(req.provider)
        source = await service.extract(req.source_text, language=req.source_language, source_id="source")
        candidate = await service.extract(req.candidate_text, language=req.candidate_language, source_id="candidate")
        return VerificationEngine().verify(source, candidate)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/verify-contract")
async def verify_against_contract(req: VerifyAgainstContractRequest, request: Request, x_signallock_demo_token: str | None = Header(default=None)):
    """Verify against a server-bound authority, never a client-asserted semantic oracle."""
    _guard_live_provider(request, req.provider, x_signallock_demo_token)
    try:
        errors = validate_provenance(req.source_text, req.source_contract, require_p0=True)
        if errors:
            raise ValueError("Invalid source-contract provenance: " + "; ".join(errors))

        if req.authority_token:
            verify_authority_token(_AUTHORITY_SECRET, req.authority_token, req.source_text, req.source_contract)
        elif req.provider == "heuristic":
            # Backward-compatible legacy path: independently reconstruct the authority
            # server-side and require exact agreement. This closes the v0.2 forged-oracle
            # bug without breaking existing local clients.
            derived = await ExtractionService("heuristic").extract(
                req.source_text,
                language=req.source_contract.language,
                source_id=req.source_contract.source_id,
            )
            if semantic_contract_blob(derived) != semantic_contract_blob(req.source_contract):
                raise ValueError("Source contract is not server-derived; use /api/extract-authority and submit its authority_token")
        else:
            raise ValueError("Live-provider source contracts require a server-issued authority_token")

        candidate = await ExtractionService(req.provider).extract(req.candidate_text, language=req.candidate_language, source_id="candidate")
        return VerificationEngine().verify(req.source_contract, candidate)
    except (AuthorityTokenError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/transform")
async def transform(req: TransformRequest, request: Request, x_signallock_demo_token: str | None = Header(default=None)):
    if req.mode == "translate" and not req.language:
        raise HTTPException(status_code=422, detail="language is required for translate mode")
    _guard_live_provider(request, req.provider, x_signallock_demo_token)
    try:
        text, metadata = await TransformationService(req.provider).transform(
            req.text, mode=req.mode, language=req.language, source_language=req.source_language, max_chars=req.max_chars,
        )
        return {"text": text, "metadata": metadata}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/cap")
def cap(req: CAPRequest):
    try:
        parsed = parse_cap_xml(req.xml, profile_strict=True)
        return {
            "identifier": parsed.identifier,
            "status": parsed.status,
            "msg_type": parsed.msg_type,
            "scope": parsed.scope,
            "infos": [
                {
                    "language": info.language,
                    "event": info.event,
                    "instruction": info.instruction,
                    "areas": info.areas,
                    "polygons": info.polygons,
                    "circles": info.circles,
                    "geocodes": info.geocodes,
                    "seed_contract": cap_info_seed_contract(parsed, info).model_dump(mode="json"),
                }
                for info in parsed.infos
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/verify-cap")
def verify_cap(req: CAPVerifyRequest):
    try:
        source_alert = parse_cap_xml(req.source_xml, profile_strict=True)
        candidate_alert = parse_cap_xml(req.candidate_xml, profile_strict=True)
        return verify_cap_alerts(source_alert, candidate_alert, source_info_index=req.source_info_index, candidate_info_index=req.candidate_info_index)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/benchmark")
def benchmark():
    return run_demo_benchmark()

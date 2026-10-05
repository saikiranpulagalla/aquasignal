from __future__ import annotations

import json
import os
import secrets
import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aquasignal import __version__
from aquasignal.domain.context import (
    AquaContext,
    AquaContextSource,
    assess_context_alignment,
    parse_oah_fhir_json,
    parse_resilience_csv,
    validate_fhir_structure,
)
from aquasignal.domain.freshwater import FreshwaterExtractor, FreshwaterProfile, assess_source_readiness
from aquasignal.evaluation.runner import run_cases
from aquasignal.evaluation.evidence import verify_release_evidence
from aquasignal.integrity.authority import (
    AquaAuthorityTokenError,
    AquaContextTokenError,
    AuthorityBinding,
    issue_aqua_authority_token,
    issue_context_token,
    verify_aqua_authority_token,
    verify_context_token,
)
from aquasignal.integrity.receipt import IntegrityReceipt, make_integrity_receipt, verify_integrity_receipt
from aquasignal.integrity.verifier import AquaVerificationEngine
from signallock.contracts.schema import SafetyContract
from signallock.providers.openai_http import ProviderError
from aquasignal.providers.rewrite import FreshwaterRewriteProvider


ROOT = Path(__file__).resolve().parents[2]


def _resolve_resource_root(root: Path) -> Path:
    if (root / "pyproject.toml").is_file() and (root / "web_aqua" / "index.html").is_file():
        return root
    return root / "aquasignal" / "resources"


RESOURCE_ROOT = _resolve_resource_root(ROOT)
WEB = RESOURCE_ROOT / "web_aqua"


def _bounded_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer between {minimum} and {maximum}") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


MAX_ADVISORY_CHARS = _bounded_int_env(
    "AQUASIGNAL_MAX_ADVISORY_CHARS", 8000, minimum=256, maximum=20000
)
MAX_REQUEST_BYTES = _bounded_int_env(
    "AQUASIGNAL_MAX_REQUEST_BYTES", 2_500_000, minimum=65_536, maximum=10_000_000
)
MAX_PROFILE_DIRECTIVES = 32
def _load_authority_secret() -> tuple[bytes, bool, str]:
    raw = os.getenv("AQUASIGNAL_AUTHORITY_SECRET", "")
    mode = os.getenv("AQUASIGNAL_ENV", "development").strip().casefold()
    if raw:
        secret = raw.encode("utf-8")
        if len(secret) < 32:
            raise RuntimeError("AQUASIGNAL_AUTHORITY_SECRET must be at least 32 bytes when configured")
        return secret, True, "configured-persistent"
    if mode in {"production", "prod"}:
        raise RuntimeError("AQUASIGNAL_AUTHORITY_SECRET is required when AQUASIGNAL_ENV=production")
    return secrets.token_bytes(32), False, "ephemeral-development-only"


_AUTHORITY_SECRET, _AUTHORITY_SECRET_CONFIGURED, _AUTHORITY_SECRET_MODE = _load_authority_secret()

extractor = FreshwaterExtractor()
verifier = AquaVerificationEngine()
profile = FreshwaterProfile()

app = FastAPI(
    title="AquaSignal",
    version=__version__,
    description="Verified freshwater risk communication for OneAquaHealth Track 6 Resilience Informatics.",
)


def _safe_validation_detail(exc: RequestValidationError) -> list[dict]:
    # Never echo raw invalid values. Apart from reducing accidental data exposure,
    # this avoids response-serialization failures for malformed Unicode such as lone
    # surrogates that Pydantic correctly rejects before route execution.
    return [
        {
            "type": str(error.get("type", "validation_error")),
            "loc": list(error.get("loc") or ()),
            "msg": str(error.get("msg", "Invalid request")),
        }
        for error in exc.errors()
    ]


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    return _apply_security_headers(
        JSONResponse(status_code=422, content={"detail": _safe_validation_detail(exc)}),
        no_store=request.url.path.startswith("/api/aqua/"),
    )


def _apply_security_headers(response, *, no_store: bool = False):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if no_store:
        response.headers["Cache-Control"] = "no-store"
    return response


class _DuplicateJSONKey(ValueError):
    pass


class _JSONNestingTooDeep(ValueError):
    pass


class _JSONParserLimit(ValueError):
    pass


def _reject_duplicate_json_keys(body: bytes) -> None:
    def pairs_hook(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise _DuplicateJSONKey(key)
            obj[key] = value
        return obj

    try:
        json.loads(body, object_pairs_hook=pairs_hook)
    except _DuplicateJSONKey:
        raise
    except RecursionError as exc:
        # Reject decoder-recursion exhaustion before FastAPI/Pydantic attempts to
        # parse the same hostile body and turns it into an uncontrolled 500.
        raise _JSONNestingTooDeep("JSON nesting exceeds the prototype limit") from exc
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Let FastAPI/Pydantic produce the canonical sanitized validation error for
        # malformed JSON/Unicode. This preflight is only for ambiguity, not parsing.
        return
    except ValueError as exc:
        # Python's JSON decoder can raise plain ValueError for parser resource
        # limits (for example an integer literal exceeding sys.int_max_str_digits).
        # Convert those bounded hostile inputs into a controlled client error rather
        # than letting them escape the middleware as a 500. Duplicate keys are
        # handled above by their dedicated exception.
        raise _JSONParserLimit("JSON value exceeds Python parser limits") from exc


@app.middleware("http")
async def security_headers(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return _apply_security_headers(JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds AquaSignal prototype limit"},
                ), no_store=request.url.path.startswith("/api/aqua/"))
        except ValueError:
            # Never trust an invalid Content-Length for application-level bounds.
            content_length = None

    # Bound the actual body for every mutating request, even when Content-Length is
    # present. This closes understated-length/proxy inconsistencies and gives the
    # JSON ambiguity check one canonical byte sequence.
    if request.method in {"POST", "PUT", "PATCH"}:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                return _apply_security_headers(JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds AquaSignal prototype limit"},
                ), no_store=request.url.path.startswith("/api/aqua/"))
            body.extend(chunk)
        request._body = bytes(body)  # Starlette Request.body()/stream() honors this cache.

        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        # FastAPI/Python can auto-detect JSON encodings (including UTF-16/32) when
        # Content-Type is omitted. Therefore absence of a media type is itself enough
        # to run the ambiguity preflight; non-JSON bodies simply fall through.
        if body and (content_type == "application/json" or content_type.endswith("+json") or not content_type):
            try:
                _reject_duplicate_json_keys(bytes(body))
            except _DuplicateJSONKey:
                return _apply_security_headers(JSONResponse(
                    status_code=422,
                    content={"detail": "Duplicate JSON object keys are not accepted"},
                ), no_store=request.url.path.startswith("/api/aqua/"))
            except _JSONNestingTooDeep:
                return _apply_security_headers(JSONResponse(
                    status_code=422,
                    content={"detail": "JSON nesting exceeds the AquaSignal prototype limit"},
                ), no_store=request.url.path.startswith("/api/aqua/"))
            except _JSONParserLimit:
                return _apply_security_headers(JSONResponse(
                    status_code=422,
                    content={"detail": "JSON value exceeds the Python parser limit"},
                ), no_store=request.url.path.startswith("/api/aqua/"))

    return _apply_security_headers(
        await call_next(request),
        no_store=request.url.path.startswith("/api/aqua/"),
    )


def _guard_text(value: str, label: str) -> str:
    # Validate emptiness using a trimmed view, but preserve the exact submitted
    # advisory text for source/candidate hashing, evidence offsets, and authority
    # binding.  Semantic extraction may normalize whitespace internally; provenance
    # must not silently rewrite the content it claims to bind.
    if not value.strip():
        raise HTTPException(status_code=422, detail=f"{label} cannot be empty")
    if len(value) > MAX_ADVISORY_CHARS:
        raise HTTPException(status_code=413, detail=f"{label} exceeds {MAX_ADVISORY_CHARS} characters")
    for ch in value:
        category = unicodedata.category(ch)
        if category.startswith("C") and ch not in {"\n", "\r", "\t"}:
            raise HTTPException(
                status_code=422,
                detail=f"{label} contains unsupported invisible/control Unicode characters",
            )
    return value


def _guard_identifier(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(status_code=422, detail=f"{label} cannot be blank")
    for ch in value:
        if unicodedata.category(ch).startswith("C"):
            raise HTTPException(
                status_code=422,
                detail=f"{label} contains unsupported invisible/control Unicode characters",
            )
    return value


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CSVContextRequest(_StrictRequest):
    csv_text: str = Field(min_length=1, max_length=2_000_000)
    synthetic_demo: bool = False


class FHIRContextRequest(_StrictRequest):
    resource: dict
    synthetic_demo: bool = False


class FHIRRawContextRequest(_StrictRequest):
    json_text: str = Field(min_length=2, max_length=1_000_000)
    synthetic_demo: bool = False


class AuthorityRequest(_StrictRequest):
    source_text: str = Field(min_length=1, max_length=MAX_ADVISORY_CHARS)
    context: AquaContext
    context_token: str = Field(min_length=20, max_length=5000)
    advisory_id: str = Field(min_length=1, max_length=120)
    revision: int = Field(default=1, ge=1, le=2_147_483_647)


class VerifyRequest(_StrictRequest):
    source_text: str = Field(min_length=1, max_length=MAX_ADVISORY_CHARS)
    source_contract: SafetyContract
    authority_token: str = Field(min_length=20, max_length=20000)
    context: AquaContext
    advisory_id: str = Field(min_length=1, max_length=120)
    revision: int = Field(default=1, ge=1, le=2_147_483_647)
    candidate_text: str = Field(min_length=1, max_length=MAX_ADVISORY_CHARS)


class RewriteRequest(_StrictRequest):
    source_text: str = Field(min_length=1, max_length=MAX_ADVISORY_CHARS)
    mode: str = Field(default="simplify", pattern=r"^(simplify|sms)$")
    max_chars: int = Field(default=360, ge=80, le=1000)


def _static_response(path: Path, *, media_type: str | None = None):
    response = FileResponse(path, media_type=media_type)
    # Judges often refresh immediately after a deployment update.  Require browser
    # revalidation so stale HTML/JS/CSS cannot make the UI disagree with the API.
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return _static_response(WEB / "index.html")


@app.get("/app.js")
def app_js():
    return _static_response(WEB / "app.js", media_type="application/javascript")


@app.get("/app.css")
def app_css():
    return _static_response(WEB / "app.css", media_type="text/css")


@app.get("/api/aqua/health")
def health():
    return {
        "status": "ok",
        "product": "AquaSignal",
        "version": __version__,
        "semantic_profile": profile.profile_id,
        "deterministic_pass_path": True,
        "authority_secret_configured": _AUTHORITY_SECRET_CONFIGURED,
        "authority_secret_mode": _AUTHORITY_SECRET_MODE,
        "authority_tokens_survive_restart": _AUTHORITY_SECRET_CONFIGURED,
    }




@app.get("/api/aqua/ready")
def readiness():
    required_resources = {
        "ui:index": WEB / "index.html",
        "ui:javascript": WEB / "app.js",
        "ui:stylesheet": WEB / "app.css",
        "demo:resilience-context": RESOURCE_ROOT / "data" / "aqua" / "demo_resilience_context.csv",
    }
    # Readiness is public operational metadata; expose stable resource labels rather
    # than filesystem paths from the host/container.
    missing = [label for label, path in required_resources.items() if not path.is_file()]
    evidence = verify_release_evidence()
    errors = []
    if missing:
        errors.append("missing runtime resources: " + ", ".join(missing))
    if not evidence.get("verified"):
        errors.extend(str(x) for x in evidence.get("errors") or ["release evidence is stale or unavailable"])
    if errors:
        raise HTTPException(status_code=503, detail={"state": "NOT_READY", "errors": errors})
    return {
        "status": "ready",
        "product": "AquaSignal",
        "version": __version__,
        "holdout": evidence.get("holdout"),
        "release_evidence_verified": True,
    }


@app.get("/api/aqua/profile")
def freshwater_profile():
    return {
        "profile_id": profile.profile_id,
        "language": profile.language,
        "automatic_pass_policy": "deterministic-only",
        "supported_dimensions": ["ACTION", "PLACE", "TIME", "AUDIENCE", "CONSTRAINT"],
        "supported_actions": [
            "avoid contact", "do not touch", "do not enter", "do not swim",
            "do not wade", "do not fish", "do not drink", "boil water", "keep away",
            "collect samples (restricted profile)",
        ],
        "unsupported_behavior": "REVIEW",
        "recognized_drift_behavior": "BLOCK when a deterministic AquaSignal policy independently proves drift",
        "risk_inference": False,
        "publication_authority": "human",
    }


@app.get("/api/aqua/demo-context")
def demo_context():
    demo_path = RESOURCE_ROOT / "data" / "aqua" / "demo_resilience_context.csv"
    data = demo_path.read_bytes()
    context = parse_resilience_csv(data, synthetic_demo=True)
    return {"context": context.model_dump(mode="json"), "context_token": issue_context_token(_AUTHORITY_SECRET, context=context), "csv_text": data.decode("utf-8")}


@app.post("/api/aqua/context/resilience-csv")
def import_csv(req: CSVContextRequest):
    try:
        context = parse_resilience_csv(req.csv_text.encode("utf-8"), synthetic_demo=req.synthetic_demo)
        return {"context": context.model_dump(mode="json"), "context_token": issue_context_token(_AUTHORITY_SECRET, context=context)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _fhir_context_response(context: AquaContext) -> dict:
    configured = {
        x.strip() for x in os.getenv("AQUASIGNAL_OAH_PROFILE_ALLOWLIST", "").split(",") if x.strip()
    }
    declared = set(context.raw_summary.get("profiles") or [])
    oah_declared = bool(configured and declared.intersection(configured))
    return {
        "context": context.model_dump(mode="json"),
        "context_token": issue_context_token(_AUTHORITY_SECRET, context=context),
        "compatibility": "configured-oah-profile" if oah_declared else "generic-environmental-fhir",
        "claim": (
            "Exact configured OAH profile URI recognized; no FHIR certification is claimed."
            if oah_declared
            else "Generic environmental FHIR R4-subset context import; no OneAquaHealth profile conformance is claimed."
        ),
    }


@app.post("/api/aqua/context/fhir")
def import_fhir(req: FHIRContextRequest):
    try:
        validate_fhir_structure(req.resource)
        raw = json.dumps(req.resource, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        context = parse_oah_fhir_json(raw, synthetic_demo=req.synthetic_demo)
        return _fhir_context_response(context)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/aqua/context/fhir-raw")
def import_fhir_raw(req: FHIRRawContextRequest):
    try:
        raw = req.json_text.encode("utf-8")
        context = parse_oah_fhir_json(raw, synthetic_demo=req.synthetic_demo)
        return _fhir_context_response(context)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/aqua/authority")
def create_authority(req: AuthorityRequest):
    source_text = _guard_text(req.source_text, "Authoritative advisory")
    advisory_id = _guard_identifier(req.advisory_id, "Advisory ID")
    try:
        verify_context_token(_AUTHORITY_SECRET, req.context_token, context=req.context)
    except AquaContextTokenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    contract = extractor.extract(source_text, source_id=f"{advisory_id}:r{req.revision}")
    readiness = assess_source_readiness(contract)
    alignment_status, alignment_reason = assess_context_alignment(req.context, contract)
    reasons = list(readiness.reasons)
    directive_count = len(contract.required_actions) + len(contract.prohibited_actions)
    if directive_count > MAX_PROFILE_DIRECTIVES:
        reasons.append(
            f"Authoritative advisory exceeds the V1 directive complexity limit "
            f"({directive_count} > {MAX_PROFILE_DIRECTIVES})."
        )
    if alignment_status == "MISMATCH":
        reasons.append(alignment_reason)
    if reasons:
        raise HTTPException(
            status_code=422,
            detail={
                "state": "SOURCE_REVIEW",
                "reasons": reasons,
                "context_alignment": alignment_status,
            },
        )
    binding = AuthorityBinding(advisory_id, req.revision, profile.profile_id)
    token = issue_aqua_authority_token(
        _AUTHORITY_SECRET,
        source_text=source_text,
        contract=contract,
        context=req.context,
        binding=binding,
    )
    return {
        "state": "SOURCE_READY",
        "source_contract": contract.model_dump(mode="json"),
        "authority_token": token,
        "semantic_profile": profile.profile_id,
        "context_alignment": alignment_status,
        "context_alignment_reason": alignment_reason,
    }


@app.post("/api/aqua/verify")
def verify(req: VerifyRequest):
    source_text = _guard_text(req.source_text, "Authoritative advisory")
    candidate_text = _guard_text(req.candidate_text, "Citizen-facing rewrite")
    advisory_id = _guard_identifier(req.advisory_id, "Advisory ID")
    binding = AuthorityBinding(advisory_id, req.revision, profile.profile_id)
    try:
        verify_aqua_authority_token(
            _AUTHORITY_SECRET,
            req.authority_token,
            source_text=source_text,
            contract=req.source_contract,
            context=req.context,
            binding=binding,
        )
    except AquaAuthorityTokenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # No-self-approval invariant: candidate verification uses only the deterministic
    # freshwater extractor. An AI provider may generate wording, but never certifies it.
    candidate_contract = extractor.extract(candidate_text, source_id=f"{advisory_id}:candidate")
    candidate_directives = len(candidate_contract.required_actions) + len(candidate_contract.prohibited_actions)
    if candidate_directives > MAX_PROFILE_DIRECTIVES:
        raise HTTPException(
            status_code=422,
            detail={
                "state": "REVIEW",
                "reason": (
                    f"Candidate exceeds the V1 directive complexity limit "
                    f"({candidate_directives} > {MAX_PROFILE_DIRECTIVES}); human review is required."
                ),
            },
        )
    result = verifier.verify(req.source_contract, candidate_contract)
    receipt = make_integrity_receipt(
        secret=_AUTHORITY_SECRET,
        source_text=source_text,
        candidate_text=candidate_text,
        context=req.context,
        advisory_id=advisory_id,
        revision=req.revision,
        profile_id=profile.profile_id,
        result=result,
    )
    return {
        **result.model_dump(mode="json"),
        "display_decision": {"PASS": "PRESERVED", "REVIEW": "REVIEW", "BLOCK": "CRITICAL DRIFT"}[result.decision.value],
        "integrity_receipt": receipt.model_dump(mode="json"),
        "verification_method": "Deterministic Freshwater Protective Communication Profile v1",
    }


@app.post("/api/aqua/receipt/verify")
def verify_receipt(receipt: IntegrityReceipt):
    """Verify that a downloadable AquaSignal receipt has not been modified.

    HMAC receipts are server-verifiable, not third-party/public-key attestations.
    """
    return {
        "valid": verify_integrity_receipt(_AUTHORITY_SECRET, receipt),
        "verification_id": receipt.verification_id,
        "signature_scheme": "HMAC-SHA256 server-verifiable",
    }


@app.post("/api/aqua/rewrite")
async def rewrite(req: RewriteRequest, request: Request):
    source_text = _guard_text(req.source_text, "Authoritative advisory")
    if os.getenv("AQUASIGNAL_REWRITE_ENABLED", "").casefold() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=503, detail="Optional AI rewrite is disabled on this deployment; paste a candidate rewrite manually.")
    expected_token = os.getenv("AQUASIGNAL_REWRITE_TOKEN", "")
    supplied_token = request.headers.get("x-aquasignal-rewrite-token", "")
    if expected_token and len(expected_token.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="Optional AI rewrite deployment token must be at least 32 bytes")
    if not expected_token or not secrets.compare_digest(supplied_token, expected_token):
        raise HTTPException(status_code=401, detail="Optional AI rewrite endpoint requires a deployment token")
    try:
        provider = FreshwaterRewriteProvider()
        text = await provider.transform(source_text, mode=req.mode, max_chars=req.max_chars)
        return {"text": text, "provider": "openai", "model": provider.model, "verification_authority": False}
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/aqua/dev-benchmark")
def dev_benchmark():
    return run_cases()


@app.get("/api/aqua/release-evidence")
def release_evidence():
    report = verify_release_evidence()
    if not report["verified"]:
        raise HTTPException(status_code=503, detail={"state": "STALE_RELEASE_EVIDENCE", "errors": report["errors"]})
    return report

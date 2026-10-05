from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass

from signallock.contracts.schema import SafetyContract
from aquasignal import __version__
from aquasignal.domain.context import AquaContext, context_blob


class AquaAuthorityTokenError(ValueError):
    pass


class AquaContextTokenError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    # urlsafe_b64decode is intentionally lenient and may ignore non-alphabet
    # characters. Integrity tokens must have one canonical textual encoding so even
    # textual tampering cannot be silently accepted. Padding is reconstructed only
    # after validating the unpadded base64url alphabet.
    if not value or not all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in value):
        raise ValueError("non-canonical base64url")
    padded = value + "=" * (-len(value) % 4)
    decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
    if _b64(decoded) != value:
        raise ValueError("non-canonical base64url")
    return decoded


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(secret: bytes, payload: dict) -> str:
    raw = _json_bytes(payload)
    sig = hmac.new(secret, raw, hashlib.sha256).digest()
    return f"{_b64(raw)}.{_b64(sig)}"


def _verify_signed(secret: bytes, token: str, *, kind: str) -> dict:
    try:
        raw_part, sig_part = token.split(".", 1)
        raw = _unb64(raw_part)
        supplied = _unb64(sig_part)
    except Exception as exc:
        raise ValueError(f"malformed {kind} token") from exc
    expected = hmac.new(secret, raw, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, expected):
        raise ValueError(f"{kind} token signature mismatch")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {kind} token payload") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid {kind} token payload")
    return payload


def _contract_blob(contract: SafetyContract) -> str:
    return json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _contract_sha256(contract: SafetyContract) -> str:
    return hashlib.sha256(_contract_blob(contract).encode("utf-8")).hexdigest()


def _context_sha256(context: AquaContext) -> str:
    return hashlib.sha256(context_blob(context).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorityBinding:
    advisory_id: str
    revision: int
    profile_id: str


def issue_context_token(secret: bytes, *, context: AquaContext) -> str:
    """Attest that this exact context object was produced/accepted by the server."""
    return _sign(secret, {
        "v": 2,
        "kind": "aqua-context",
        "context_sha256": _context_sha256(context),
        "dataset_sha256": context.dataset_sha256,
        "source": context.source.value,
        "engine_version": __version__,
    })


def verify_context_token(secret: bytes, token: str, *, context: AquaContext) -> None:
    try:
        payload = _verify_signed(secret, token, kind="AquaSignal context")
    except ValueError as exc:
        raise AquaContextTokenError(str(exc)) from exc
    if payload.get("v") != 2 or payload.get("kind") != "aqua-context":
        raise AquaContextTokenError("unsupported AquaSignal context token")
    if payload.get("engine_version") != __version__:
        raise AquaContextTokenError("context token was issued by a different AquaSignal engine version")
    if payload.get("context_sha256") != _context_sha256(context):
        raise AquaContextTokenError("context token is bound to different environmental context")
    if payload.get("dataset_sha256") != context.dataset_sha256 or payload.get("source") != context.source.value:
        raise AquaContextTokenError("context token provenance binding mismatch")


def issue_aqua_authority_token(
    secret: bytes,
    *,
    source_text: str,
    contract: SafetyContract,
    context: AquaContext,
    binding: AuthorityBinding,
) -> str:
    """Issue a compact hash-bound authority token.

    Full source contracts and context metadata stay in the request/record rather than
    being duplicated inside the token, preventing token-size self-incompatibility.
    """
    return _sign(secret, {
        "v": 2,
        "kind": "aqua-authority",
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "contract_sha256": _contract_sha256(contract),
        "context_sha256": _context_sha256(context),
        "advisory_id": binding.advisory_id,
        "revision": binding.revision,
        "profile_id": binding.profile_id,
        "engine_version": __version__,
    })


def verify_aqua_authority_token(
    secret: bytes,
    token: str,
    *,
    source_text: str,
    contract: SafetyContract,
    context: AquaContext,
    binding: AuthorityBinding,
) -> None:
    try:
        payload = _verify_signed(secret, token, kind="AquaSignal authority")
    except ValueError as exc:
        raise AquaAuthorityTokenError(str(exc)) from exc
    if payload.get("v") != 2 or payload.get("kind") != "aqua-authority":
        raise AquaAuthorityTokenError("unsupported AquaSignal authority token version")
    expected = {
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "contract_sha256": _contract_sha256(contract),
        "context_sha256": _context_sha256(context),
        "advisory_id": binding.advisory_id,
        "revision": binding.revision,
        "profile_id": binding.profile_id,
        "engine_version": __version__,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            labels = {
                "source_sha256": "different advisory text",
                "contract_sha256": "different advisory contract",
                "context_sha256": "different environmental context",
                "advisory_id": "different advisory identity",
                "revision": "different advisory revision",
                "profile_id": "different semantic profile",
                "engine_version": "different AquaSignal engine version",
            }
            raise AquaAuthorityTokenError(f"authority token is bound to {labels[key]}")

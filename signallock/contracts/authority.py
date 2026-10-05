from __future__ import annotations

import base64
import hashlib
import hmac
import json

from signallock.contracts.schema import SafetyContract


class AuthorityTokenError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _contract_blob(contract: SafetyContract) -> str:
    return json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_contract_blob(contract: SafetyContract) -> str:
    # Used only for server-side equality checks when legacy clients do not yet send a
    # signed token. Evidence is retained: a caller may not swap semantics while reusing
    # a legitimate quote.
    return _contract_blob(contract)


def issue_authority_token(secret: bytes, source_text: str, contract: SafetyContract) -> str:
    payload = {
        "v": 1,
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "contract": contract.model_dump(mode="json"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(secret, raw, hashlib.sha256).digest()
    return f"{_b64(raw)}.{_b64(sig)}"


def verify_authority_token(secret: bytes, token: str, source_text: str, contract: SafetyContract) -> None:
    try:
        raw_part, sig_part = token.split(".", 1)
        raw = _unb64(raw_part)
        supplied = _unb64(sig_part)
    except Exception as exc:
        raise AuthorityTokenError("malformed authority token") from exc
    expected = hmac.new(secret, raw, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, expected):
        raise AuthorityTokenError("authority token signature mismatch")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthorityTokenError("invalid authority token payload") from exc
    if payload.get("v") != 1:
        raise AuthorityTokenError("unsupported authority token version")
    actual_source = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    if payload.get("source_sha256") != actual_source:
        raise AuthorityTokenError("authority token is bound to different source text")
    signed = SafetyContract.model_validate(payload.get("contract"))
    if not hmac.compare_digest(_contract_blob(signed).encode("utf-8"), _contract_blob(contract).encode("utf-8")):
        raise AuthorityTokenError("authority token is bound to a different contract")

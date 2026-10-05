from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from signallock.contracts.schema import VerificationResult
from aquasignal import __version__
from aquasignal.domain.context import AquaContext, context_blob


class ReceiptDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    status: str
    criticality: str
    detector: str
    expected: str | None = None
    observed: str | None = None
    reason: str


class IntegrityReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification_id: str
    created_at: datetime
    decision: str
    source_sha256: str
    candidate_sha256: str
    source_contract_sha256: str
    candidate_contract_sha256: str
    dataset_sha256: str
    context_binding_sha256: str
    context_source: str
    context_site: str | None = None
    advisory_id: str
    revision: int
    semantic_profile: str
    engine_version: str
    differences: list[ReceiptDifference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    signature: str


def _unsigned_payload(receipt: IntegrityReceipt | dict) -> dict:
    if isinstance(receipt, IntegrityReceipt):
        return receipt.model_dump(mode="json", exclude={"signature"})
    data = dict(receipt)
    data.pop("signature", None)
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    data["differences"] = [
        x.model_dump(mode="json") if isinstance(x, ReceiptDifference) else x
        for x in data.get("differences", [])
    ]
    return data




def _contract_sha256(contract) -> str:
    raw = json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _signature(secret: bytes, data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret, raw, hashlib.sha256).hexdigest()


def verify_integrity_receipt(secret: bytes, receipt: IntegrityReceipt) -> bool:
    return hmac.compare_digest(receipt.signature, _signature(secret, _unsigned_payload(receipt)))


def make_integrity_receipt(
    *,
    secret: bytes,
    source_text: str,
    candidate_text: str,
    context: AquaContext,
    advisory_id: str,
    revision: int,
    profile_id: str,
    result: VerificationResult,
) -> IntegrityReceipt:
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    candidate_hash = hashlib.sha256(candidate_text.encode("utf-8")).hexdigest()
    context_hash = hashlib.sha256(context_blob(context).encode("utf-8")).hexdigest()
    source_contract_hash = _contract_sha256(result.source_contract)
    candidate_contract_hash = _contract_sha256(result.candidate_contract)
    differences = [
        ReceiptDifference(
            dimension=s.field,
            status=s.status,
            criticality=s.criticality,
            detector=s.detector,
            expected=s.expected,
            observed=s.observed,
            reason=s.reason,
        )
        for s in result.signals if s.status != "PASS"
    ]
    identity = (
        f"{context_hash}:{source_hash}:{candidate_hash}:{source_contract_hash}:{candidate_contract_hash}:"
        f"{advisory_id}:{revision}:{profile_id}:{result.decision.value}:{__version__}"
    )
    base = {
        "verification_id": "AQ-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32].upper(),
        "created_at": datetime.now(timezone.utc),
        "decision": result.decision.value,
        "source_sha256": source_hash,
        "candidate_sha256": candidate_hash,
        "source_contract_sha256": source_contract_hash,
        "candidate_contract_sha256": candidate_contract_hash,
        "dataset_sha256": context.dataset_sha256,
        "context_binding_sha256": context_hash,
        "context_source": context.source.value,
        "context_site": context.site,
        "advisory_id": advisory_id,
        "revision": revision,
        "semantic_profile": profile_id,
        "engine_version": __version__,
        "differences": differences,
        "warnings": result.warnings,
    }
    return IntegrityReceipt(**base, signature=_signature(secret, _unsigned_payload(base)))

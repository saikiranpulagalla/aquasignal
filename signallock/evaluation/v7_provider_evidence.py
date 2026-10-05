from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from signallock.evaluation.holdout import HoldoutError, load_jsonl, sha256_file, verify_seal
from signallock.evaluation.v7 import _canonical_sha256, provider_audit_metadata
from signallock.evaluation.v7_evidence import verify_v7_evidence
from signallock.providers.openai_http import (
    EXTRACTION_SYSTEM_PROMPT,
    OpenAIResponsesProvider,
    contract_from_provider_output,
)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _flatten_input_text(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    chunks: list[str] = []
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"input_text", "text"} and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks)


def _expected_user_input(row: dict) -> str:
    source_id = f"v7-candidate:{row['case_id']}"
    return (
        f"Language: {row['candidate_language']}\n"
        f"Source ID: {source_id}\n\n"
        f"ALERT:\n{row['candidate_text']}"
    )


async def _get_json(client: httpx.AsyncClient, url: str) -> dict:
    try:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HoldoutError(f"provider retrieval failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HoldoutError(f"provider retrieval returned non-object JSON for {url}")
    return payload


async def verify_v7_provider_evidence(
    result_path: Path,
    holdout_path: Path,
    manifest_path: Path,
    *,
    root: Path | None = None,
    require_trusted_runtime: bool = True,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Verify every V7 provider receipt against retrievable OpenAI Responses state.

    This is stronger than local replay: each saved response ID must exist at OpenAI,
    be stored/completed under the frozen model, carry the exact SignalLock run/case
    metadata, expose the exact candidate input, and reproduce the raw structured-output
    hash and post-processed candidate contract used by the verifier.

    It is still process/API evidence rather than a cryptographic signature by OpenAI.
    """
    offline = verify_v7_evidence(
        result_path,
        holdout_path,
        manifest_path,
        root=root,
        require_trusted_runtime=require_trusted_runtime,
    )
    manifest = verify_seal(holdout_path, manifest_path)
    rows = load_jsonl(holdout_path)
    rows_by_id = {str(row["case_id"]): row for row in rows}
    report = json.loads(result_path.read_text(encoding="utf-8"))
    raw_cases = report.get("cases") or []
    execution_binding = report.get("execution_binding") or {}
    run_id = str(report.get("run_id") or "").strip()
    model = str(report.get("model") or execution_binding.get("model") or "").strip()
    provider = str(report.get("provider") or "").strip()
    if provider != "openai":
        raise HoldoutError(f"provider retrieval verification supports openai only, got {provider!r}")
    if not run_id or not model:
        raise HoldoutError("V7 result is missing run/model binding")

    key = api_key or os.getenv("OPENAI_API_KEY")
    owns_client = client is None
    if client is None:
        if not key:
            raise HoldoutError("OPENAI_API_KEY is required for live provider evidence retrieval")
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0),
            headers={"Authorization": f"Bearer {key}"},
        )

    case_receipts: list[dict] = []
    try:
        for raw_case in raw_cases:
            case_id = str(raw_case.get("case_id") or "")
            row = rows_by_id.get(case_id)
            if row is None:
                raise HoldoutError(f"provider verification found unknown case {case_id!r}")
            if raw_case.get("provider_error") is not None:
                raise HoldoutError(f"{case_id}: provider-error case cannot qualify provider retrieval evidence")
            receipt = raw_case.get("provider_receipt")
            if not isinstance(receipt, dict):
                raise HoldoutError(f"{case_id}: provider receipt missing")
            response_id = str(receipt.get("response_id") or "").strip()
            if not response_id:
                raise HoldoutError(f"{case_id}: provider response ID missing")

            response_raw = await _get_json(client, f"{OPENAI_RESPONSES_URL}/{response_id}")
            if str(response_raw.get("id") or "") != response_id:
                raise HoldoutError(f"{case_id}: retrieved provider response ID mismatch")
            if response_raw.get("status") != "completed":
                raise HoldoutError(f"{case_id}: retrieved provider response is not completed")
            if response_raw.get("store") is not True:
                raise HoldoutError(f"{case_id}: retrieved provider response is not stored")
            if str(response_raw.get("model") or "") != model:
                raise HoldoutError(f"{case_id}: retrieved provider model differs from frozen model")

            expected_metadata = provider_audit_metadata(
                row,
                run_id=run_id,
                manifest_sha256=manifest["sha256"],
                execution_binding=execution_binding,
            )
            if response_raw.get("metadata") != expected_metadata:
                raise HoldoutError(f"{case_id}: retrieved provider metadata differs from sealed V7 binding")
            if receipt.get("response_metadata") != expected_metadata:
                raise HoldoutError(f"{case_id}: saved provider metadata differs from sealed V7 binding")

            output_text = OpenAIResponsesProvider._output_text(response_raw)
            output_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
            if output_hash != receipt.get("output_text_sha256"):
                raise HoldoutError(f"{case_id}: retrieved provider output hash differs from saved receipt")

            reconstructed = contract_from_provider_output(
                output_text,
                row["candidate_text"],
                language=row["candidate_language"],
                source_id=f"v7-candidate:{case_id}",
            ).model_dump(mode="json")
            if _canonical_sha256(reconstructed) != raw_case.get("candidate_contract_sha256"):
                raise HoldoutError(f"{case_id}: provider output does not reproduce saved candidate contract")

            input_raw = await _get_json(
                client,
                f"{OPENAI_RESPONSES_URL}/{response_id}/input_items?limit=100&order=asc",
            )
            data = input_raw.get("data")
            if not isinstance(data, list):
                raise HoldoutError(f"{case_id}: provider input-items response is malformed")
            if input_raw.get("has_more") is not False or len(data) != 2 or not all(isinstance(item, dict) for item in data):
                raise HoldoutError(f"{case_id}: provider-stored input does not contain the exact request transcript")
            role_text = [(str(item.get("role") or ""), _flatten_input_text(item)) for item in data]
            if role_text[0] != ("system", EXTRACTION_SYSTEM_PROMPT):
                raise HoldoutError(f"{case_id}: provider-stored extraction system prompt differs from frozen prompt")
            if role_text[1] != ("user", _expected_user_input(row)):
                raise HoldoutError(f"{case_id}: provider-stored user input differs from sealed candidate")

            response_created_at = response_raw.get("created_at")
            if not isinstance(response_created_at, (int, float)) or response_created_at <= 0:
                raise HoldoutError(f"{case_id}: retrieved provider created_at is invalid")
            if receipt.get("response_created_at") != response_created_at:
                raise HoldoutError(f"{case_id}: saved provider created_at differs from retrieved response")

            case_receipts.append({
                "case_id": case_id,
                "response_id": response_id,
                "response_created_at": response_created_at,
                "response_model": model,
                "response_metadata": expected_metadata,
                "output_text_sha256": output_hash,
                "candidate_contract_sha256": raw_case.get("candidate_contract_sha256"),
                "retrieved_response_sha256": _canonical_sha256(response_raw),
                "retrieved_input_items_sha256": _canonical_sha256(input_raw),
            })
    finally:
        if owns_client:
            await client.aclose()

    return {
        "kind": "SignalLock V7 live provider retrieval verification",
        "version": "1.0",
        "verified": True,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "result_sha256": sha256_file(result_path),
        "sealed_holdout_sha256": manifest["sha256"],
        "manifest_file_sha256": sha256_file(manifest_path),
        "run_id": run_id,
        "provider": provider,
        "model": model,
        "provider_verified_cases": len(case_receipts),
        "offline_replay_gate": offline["gate"],
        "runtime_identity": offline.get("runtime_identity"),
        "cases": case_receipts,
        "limitation": (
            "Provider retrieval is API/process evidence from OpenAI's stored Responses resource, "
            "not a cryptographic signature by OpenAI. It requires store=true and is incompatible "
            "with organizations where Zero Data Retention forces storage off."
        ),
    }

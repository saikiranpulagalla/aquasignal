from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.providers.openai_http import OpenAIResponsesProvider, ProviderError


async def run() -> dict:
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    token = secrets.token_hex(8)
    metadata = {
        "signallock_smoke": token,
        "signallock_purpose": "v7-provider-retrieval-preflight",
    }
    provider = OpenAIResponsesProvider(model=model)
    text = "Residents must shelter indoors."
    contract, receipt = await provider.extract_contract_with_evidence(
        text,
        language="en",
        source_id=f"provider-smoke:{token}",
        audit_metadata=metadata,
        store=True,
    )
    response_id = str(receipt.get("response_id") or "").strip()
    if not response_id or receipt.get("stored") is not True:
        raise ProviderError(
            "provider did not return a stored response; strict V7 provider retrieval cannot qualify "
            "under this project/data-retention configuration"
        )
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    async with httpx.AsyncClient(timeout=45.0, headers=headers) as client:
        response = await client.get(f"https://api.openai.com/v1/responses/{response_id}")
        response.raise_for_status()
        raw = response.json()
        items_response = await client.get(
            f"https://api.openai.com/v1/responses/{response_id}/input_items",
            params={"limit": 100, "order": "asc"},
        )
        items_response.raise_for_status()
        items = items_response.json()
    if raw.get("id") != response_id or raw.get("status") != "completed" or raw.get("store") is not True:
        raise ProviderError("stored provider response could not be retrieved as a completed stored response")
    if raw.get("metadata") != metadata:
        raise ProviderError("retrieved provider metadata differs from the smoke-check request")
    output_text = OpenAIResponsesProvider._output_text(raw)
    if hashlib.sha256(output_text.encode("utf-8")).hexdigest() != receipt.get("output_text_sha256"):
        raise ProviderError("retrieved provider output hash differs from the creation receipt")
    if not isinstance(items.get("data"), list) or not items["data"]:
        raise ProviderError("provider response input items are not retrievable")
    return {
        "passed": True,
        "purpose": "non-holdout provider storage/retrieval capability smoke check",
        "model": model,
        "response_id": response_id,
        "stored": True,
        "input_items_retrievable": True,
        "output_hash_retrievable": True,
        "contract_sha256": hashlib.sha256(
            json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "qualification_evidence": False,
    }


def main() -> None:
    try:
        report = asyncio.run(run())
    except (ProviderError, httpx.HTTPError, ValueError, OSError) as exc:
        raise SystemExit(f"PROVIDER RETRIEVAL SMOKE FAILED: {exc}") from None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

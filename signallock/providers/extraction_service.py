from __future__ import annotations

from dataclasses import dataclass

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import SafetyContract
from signallock.providers.openai_http import OpenAIResponsesProvider


@dataclass(slots=True)
class ExtractionService:
    provider: str = "heuristic"

    async def extract(self, text: str, *, language: str = "en", source_id: str | None = None) -> SafetyContract:
        if self.provider == "openai":
            return await OpenAIResponsesProvider().extract_contract(text, language=language, source_id=source_id)
        return HeuristicExtractor().extract(text, language=language, source_id=source_id)

    async def extract_with_evidence(
        self,
        text: str,
        *,
        language: str = "en",
        source_id: str | None = None,
        audit_metadata: dict[str, str] | None = None,
        store: bool = False,
    ) -> tuple[SafetyContract, dict | None]:
        if self.provider == "openai":
            return await OpenAIResponsesProvider().extract_contract_with_evidence(
                text, language=language, source_id=source_id,
                audit_metadata=audit_metadata, store=store,
            )
        return HeuristicExtractor().extract(text, language=language, source_id=source_id), None

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from signallock.providers.extraction_service import ExtractionService
from signallock.transforms.service import TransformationService


@dataclass(slots=True)
class SourceSeed:
    case_id: str
    text: str
    language: str = "en"


def load_source_seeds(path: Path) -> list[SourceSeed]:
    rows = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        if not row.get("case_id") or not row.get("text"):
            raise ValueError(f"line {line_no}: case_id and text are required")
        rows.append(SourceSeed(case_id=row["case_id"], text=row["text"], language=row.get("language", "en")))
    if not rows:
        raise ValueError("source seed file is empty")
    return rows


async def generate_review_draft(
    seeds: list[SourceSeed],
    *,
    languages: list[str],
    provider: str = "openai",
) -> list[dict]:
    """Generate only clean translation candidates for later independent review.

    Deliberately does *not* reuse the development fault injectors. Final unsafe holdout
    rows must be independently authored/reviewed so V7 does not test on the same fault
    vocabulary that shaped V4/V5.
    """
    extractor = ExtractionService(provider)
    transformer = TransformationService(provider)
    rows: list[dict] = []

    for seed in seeds:
        source_contract = await extractor.extract(seed.text, language=seed.language, source_id=f"authority:{seed.case_id}")
        source_json = source_contract.model_dump(mode="json")
        for language in languages:
            translated, metadata = await transformer.transform(
                seed.text,
                mode="translate",
                language=language,
                source_language=seed.language,
            )
            rows.append({
                "case_id": f"{seed.case_id}-{language}-clean",
                "source_text": seed.text,
                "source_language": seed.language,
                "source_contract": source_json,
                "candidate_text": translated,
                "candidate_language": language,
                "suggested_expected_decision": "PASS",
                "expected_decision": "UNREVIEWED",
                "expected_fault": "CLEAN_TRANSLATION",
                "human_reviewed": False,
                "candidate_provider": metadata,
                "review_instruction": "Verify meaning independently; do not approve solely because the translation provider produced it.",
            })
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

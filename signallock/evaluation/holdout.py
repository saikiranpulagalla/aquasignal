from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from signallock.contracts.provenance import validate_provenance
from signallock.contracts.schema import SafetyContract
from signallock.evaluation.environment import execution_environment, environment_sha256, require_qualification_environment


REQUIRED_ROW_FIELDS = {
    "case_id",
    "source_text",
    "source_language",
    "candidate_text",
    "candidate_language",
    "source_contract",
    "expected_decision",
    "human_reviewed",
}
ALLOWED_DECISIONS = {"PASS", "REVIEW", "BLOCK"}


class HoldoutError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise HoldoutError(f"holdout input does not exist: {path}")
    rows: list[dict] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HoldoutError(f"line {line_no}: invalid JSON") from exc
        missing = REQUIRED_ROW_FIELDS - row.keys()
        if missing:
            raise HoldoutError(f"line {line_no}: missing fields {sorted(missing)}")
        if row["expected_decision"] not in ALLOWED_DECISIONS:
            raise HoldoutError(f"line {line_no}: invalid expected_decision")
        if row["human_reviewed"] is not True:
            raise HoldoutError(f"line {line_no}: holdout rows must be independently human reviewed")
        if not str(row["source_text"]).strip() or not str(row["candidate_text"]).strip():
            raise HoldoutError(f"line {line_no}: blank source/candidate text")
        try:
            contract = SafetyContract.model_validate(row["source_contract"])
        except Exception as exc:
            raise HoldoutError(f"line {line_no}: invalid source_contract: {exc}") from exc
        if contract.language.split("-")[0].casefold() != str(row["source_language"]).split("-")[0].casefold():
            raise HoldoutError(f"line {line_no}: source_contract language does not match source_language")
        provenance_errors = validate_provenance(str(row["source_text"]), contract, require_p0=True)
        if provenance_errors:
            raise HoldoutError(f"line {line_no}: invalid source_contract provenance: {'; '.join(provenance_errors)}")
        rows.append(row)
    if not rows:
        raise HoldoutError("holdout cannot be empty")
    case_ids = [str(r["case_id"]) for r in rows]
    if len(case_ids) != len(set(case_ids)):
        raise HoldoutError("case_id values must be unique")

    # A repeated authoritative source must have exactly one frozen oracle contract.
    authority_by_source: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (str(row["source_language"]), str(row["source_text"]))
        contract_blob = json.dumps(row["source_contract"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        previous = authority_by_source.get(key)
        if previous is not None and previous != contract_blob:
            raise HoldoutError("same authoritative source has inconsistent frozen source_contract values")
        authority_by_source[key] = contract_blob
    return rows


def canonical_jsonl(rows: Iterable[dict]) -> bytes:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def seal_holdout(
    input_path: Path,
    output_path: Path,
    manifest_path: Path,
    *,
    schema_version: str,
    verifier_version: str,
    extractor_version: str,
    prompt_version: str,
    code_commit: str | None = None,
) -> dict:
    rows = load_jsonl(input_path)
    payload = canonical_jsonl(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    digest = sha256_bytes(payload)
    language_pairs = sorted({f"{r['source_language']}->{r['candidate_language']}" for r in rows})
    decisions = {d: sum(r["expected_decision"] == d for r in rows) for d in sorted(ALLOWED_DECISIONS)}
    manifest = {
        "kind": "SignalLock frozen multilingual holdout",
        "sealed": True,
        "sha256": digest,
        "rows": len(rows),
        "language_pairs": language_pairs,
        "expected_decisions": decisions,
        "schema_version": schema_version,
        "verifier_version": verifier_version,
        "extractor_version": extractor_version,
        "prompt_version": prompt_version,
        "code_commit": code_commit,
        "rules": [
            "Do not edit the sealed JSONL in place.",
            "Do not tune prompts, rules, thresholds, or canonicalization using these results.",
            "If system behavior changes after results are inspected, retire this holdout to development and seal a fresh one.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_code_binding(manifest: dict, current_commit: str) -> None:
    expected = manifest.get("code_commit")
    if not expected:
        raise HoldoutError("holdout manifest is not bound to a code commit")
    if expected != current_commit:
        raise HoldoutError(f"code commit mismatch: holdout bound to {expected}, runtime is {current_commit}")


def verify_seal(holdout_path: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("sealed") is not True:
        raise HoldoutError("manifest is not sealed")
    actual = sha256_file(holdout_path)
    expected = manifest.get("sha256")
    if actual != expected:
        raise HoldoutError(f"holdout hash mismatch: expected {expected}, got {actual}")
    return manifest

# V7 is deliberately stricter than the generic holdout helper above.  The generic
# helper remains useful for unit/dev fixtures; only the V7 sealer may certify a
# competition holdout.
V7_REQUIRED_FAULT_CLASSES = {
    "clean",
    "action_area",
    "action_audience",
    "quantity_exception_binding",
    "modality",
    "temporal",
    "logic_sequence",
}


def _normalize_text_for_diversity(text: str) -> str:
    import re
    import unicodedata
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def _normalize_text_for_family(text: str) -> str:
    """Collapse superficial numeric/punctuation variation for source-diversity checks."""
    import re
    normalized = _normalize_text_for_diversity(text)
    normalized = re.sub(r"\d+(?:[.,]\d+)?", "<num>", normalized)
    normalized = re.sub(r"[^\w\s<>]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _script_fraction(text: str, language: str) -> tuple[int, int, float]:
    root = language.split("-")[0].casefold()
    ranges = {"hi": (0x0900, 0x097F), "te": (0x0C00, 0x0C7F)}
    if root not in ranges:
        return 0, 0, 0.0
    lo, hi = ranges[root]
    letters = [c for c in text if c.isalpha()]
    script_chars = sum(lo <= ord(c) <= hi for c in letters)
    return script_chars, len(letters), (script_chars / len(letters)) if letters else 0.0


def _language_cue_hits(text: str, language: str) -> int:
    """Second deterministic signal beyond Unicode script.

    This is intentionally conservative and limited to the two V7 languages. It is not
    advertised as a general language detector; it prevents a Devanagari/Telugu-script
    label from being accepted solely because of code points.
    """
    import re
    root = language.split("-")[0].casefold()
    normalized = " ".join(text.split())
    cues = {
        "hi": ("में", "को", "से", "और", "या", "नहीं", "मत", "करें", "रहें", "जाएं", "तक", "पहले", "बाद", "यदि", "लोग", "निवासी", "तुरंत", "सलाह", "बचें", "चाहिए"),
        "te": ("లో", "కి", "కు", "ను", "మరియు", "లేదా", "వద్దు", "చేయండి", "ఉండండి", "వరకు", "ముందు", "తర్వాత", "ప్రజలు", "నివాసితులు", "వెంటనే", "సలహా"),
    }
    if root not in cues:
        return 0
    hits = 0
    for cue in cues[root]:
        if cue in normalized:
            hits += 1
    # Count a common finite/imperative ending as an additional weak cue.
    if root == "hi" and re.search(r"(?:ें|ना|िए)(?:\s|[।.!?,;:]|$)", normalized):
        hits += 1
    if root == "te" and re.search(r"(?:ండి|ాలి|వద్దు)(?:\s|[.!?,;:]|$)", normalized):
        hits += 1
    return hits


def _identity_key(value: object) -> str:
    """Canonicalize human-role labels, including invisible Unicode format aliases."""
    import unicodedata
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")
    return " ".join(normalized.split()).casefold()


def validate_v7_quality(rows: list[dict]) -> dict:
    """Reject label/diversity/reviewer shortcuts before a V7 dataset can be sealed."""
    from datetime import datetime
    from difflib import SequenceMatcher

    if len(rows) < 24:
        raise HoldoutError("V7 requires at least 24 independently reviewed rows")

    by_language: dict[str, list[dict]] = {}
    reviewer_ids: set[str] = set()
    second_reviewer_ids: set[str] = set()
    author_ids: set[str] = set()
    authors_by_fault: dict[str, set[str]] = {}
    fault_counts: dict[str, int] = {}
    pair_seen: set[tuple[str, str, str]] = set()

    for i, row in enumerate(rows, start=1):
        lang = str(row["candidate_language"]).split("-")[0].casefold()
        if lang not in {"hi", "te"}:
            raise HoldoutError(f"row {i}: V7 candidate_language must be hi or te, got {lang!r}")
        source_lang = str(row.get("source_language", "")).split("-")[0].casefold()
        if source_lang != "en":
            raise HoldoutError(f"row {i}: V7 authoritative source_language must be English ('en'), got {source_lang!r}")
        script_chars, letters, fraction = _script_fraction(str(row["candidate_text"]), lang)
        if script_chars < 3 or fraction < 0.50:
            raise HoldoutError(
                f"row {i}: candidate text does not independently validate as {lang} script "
                f"({script_chars}/{letters} alphabetic characters)"
            )
        cue_hits = _language_cue_hits(str(row["candidate_text"]), lang)
        if cue_hits < 1:
            raise HoldoutError(f"row {i}: candidate has {lang} script but lacks an independent {lang} language cue")

        author_id = str(row.get("author_id", "")).strip()
        authority_reviewer = str(row.get("authority_reviewer_id", "")).strip()
        authority_reviewed_at = str(row.get("authority_reviewed_at", "")).strip()
        if not author_id or not authority_reviewer or not authority_reviewed_at:
            raise HoldoutError(
                f"row {i}: strict V7 requires author_id, authority_reviewer_id, and authority_reviewed_at"
            )
        if _identity_key(author_id) == _identity_key(authority_reviewer):
            raise HoldoutError(f"row {i}: candidate author cannot review the source authority contract")
        author_ids.add(_identity_key(author_id))
        try:
            authority_time = datetime.fromisoformat(authority_reviewed_at.replace("Z", "+00:00"))
            if authority_time.tzinfo is None:
                raise ValueError("timezone missing")
        except ValueError as exc:
            raise HoldoutError(f"row {i}: authority_reviewed_at must be an ISO-8601 timestamp with timezone") from exc

        try:
            source_contract = SafetyContract.model_validate(row["source_contract"])
        except Exception as exc:
            raise HoldoutError(f"row {i}: invalid source_contract during strict V7 validation: {exc}") from exc
        if not (source_contract.required_actions or source_contract.prohibited_actions):
            raise HoldoutError(f"row {i}: authoritative source contract has no operational directive; cannot certify V7")
        if source_contract.unresolved_operational_text:
            raise HoldoutError(f"row {i}: authoritative source contract contains unresolved operational text")

        reviewer = str(row.get("reviewer_id", "")).strip()
        reviewed_at = str(row.get("reviewed_at", "")).strip()
        source_reference = str(row.get("source_reference", "")).strip()
        fault_class = str(row.get("fault_class", "")).strip().casefold()
        if not reviewer or not reviewed_at or not source_reference or not fault_class:
            raise HoldoutError(
                f"row {i}: strict V7 requires reviewer_id, reviewed_at, source_reference, and fault_class"
            )
        try:
            parsed_time = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                raise ValueError("timezone missing")
        except ValueError as exc:
            raise HoldoutError(f"row {i}: reviewed_at must be an ISO-8601 timestamp with timezone") from exc
        if _identity_key(reviewer) == _identity_key(author_id):
            raise HoldoutError(f"row {i}: primary reviewer must be independent of candidate author")
        if _identity_key(reviewer) == _identity_key(authority_reviewer):
            raise HoldoutError(f"row {i}: primary reviewer must be independent of authority reviewer")
        if parsed_time < authority_time:
            raise HoldoutError(f"row {i}: primary review predates authority-contract review")
        reviewer_ids.add(_identity_key(reviewer))
        reviewer_ids.add(_identity_key(authority_reviewer))

        if row["expected_decision"] == "PASS" and fault_class != "clean":
            raise HoldoutError(f"row {i}: expected-PASS rows must use fault_class='clean'")
        if row["expected_decision"] == "BLOCK":
            second = str(row.get("second_reviewer_id", "")).strip()
            second_reviewed_at = str(row.get("second_reviewed_at", "")).strip()
            if not second or _identity_key(second) in {
                _identity_key(reviewer), _identity_key(author_id), _identity_key(authority_reviewer)
            }:
                raise HoldoutError(
                    f"row {i}: expected-BLOCK rows require a second reviewer distinct from primary, authority reviewer, and author"
                )
            if not second_reviewed_at:
                raise HoldoutError(f"row {i}: expected-BLOCK rows require second_reviewed_at")
            try:
                second_time = datetime.fromisoformat(second_reviewed_at.replace("Z", "+00:00"))
                if second_time.tzinfo is None:
                    raise ValueError("timezone missing")
            except ValueError as exc:
                raise HoldoutError(f"row {i}: second_reviewed_at must be an ISO-8601 timestamp with timezone") from exc
            if second_time < authority_time:
                raise HoldoutError(f"row {i}: secondary review predates authority-contract review")
            second_reviewer_ids.add(_identity_key(second))
        fault_counts[fault_class] = fault_counts.get(fault_class, 0) + 1
        authors_by_fault.setdefault(fault_class, set()).add(_identity_key(author_id))
        by_language.setdefault(lang, []).append(row)

        key = (
            _normalize_text_for_diversity(str(row["source_text"])),
            _normalize_text_for_diversity(str(row["candidate_text"])),
            lang,
        )
        if key in pair_seen:
            raise HoldoutError(f"row {i}: duplicate source/candidate semantic pair")
        pair_seen.add(key)

    missing_faults = V7_REQUIRED_FAULT_CLASSES - set(fault_counts)
    if missing_faults:
        raise HoldoutError(f"V7 missing required fault classes: {sorted(missing_faults)}")
    if len(author_ids) < 2:
        raise HoldoutError("V7 requires at least 2 independent candidate authors overall")
    for cls in sorted(V7_REQUIRED_FAULT_CLASSES - {"clean"}):
        if fault_counts.get(cls, 0) < 2:
            raise HoldoutError(f"V7 fault class {cls!r} needs at least 2 independently authored cases")
        if len(authors_by_fault.get(cls, set())) < 2:
            raise HoldoutError(f"V7 fault class {cls!r} requires at least 2 distinct candidate authors")

    unique_sources = {_normalize_text_for_diversity(str(r["source_text"])) for r in rows}
    unique_source_families = {_normalize_text_for_family(str(r["source_text"])) for r in rows}
    unique_candidates = {_normalize_text_for_diversity(str(r["candidate_text"])) for r in rows}
    if len(unique_sources) < 6:
        raise HoldoutError("V7 requires at least 6 unique authoritative source texts")
    if len(unique_source_families) < 6:
        raise HoldoutError("V7 requires at least 6 semantically distinct authoritative source families")
    if len(unique_candidates) < 12:
        raise HoldoutError("V7 requires at least 12 unique candidate texts")

    # Reject punctuation/minor-edit clones for the same source/language.  Comparing
    # within a source avoids falsely rejecting semantically similar translations of
    # different authoritative alerts.
    for lang, lang_rows in by_language.items():
        if len(lang_rows) < 12:
            raise HoldoutError(f"V7 {lang}: requires at least 12 cases")
        if sum(r["expected_decision"] == "PASS" for r in lang_rows) < 4:
            raise HoldoutError(f"V7 {lang}: requires at least 4 expected-PASS cases")
        if sum(r["expected_decision"] == "BLOCK" for r in lang_rows) < 6:
            raise HoldoutError(f"V7 {lang}: requires at least 6 expected-BLOCK cases")
        if len({_normalize_text_for_diversity(str(r["source_text"])) for r in lang_rows}) < 4:
            raise HoldoutError(f"V7 {lang}: requires at least 4 unique source texts")
        if len({_normalize_text_for_family(str(r["source_text"])) for r in lang_rows}) < 4:
            raise HoldoutError(f"V7 {lang}: requires at least 4 distinct source families")
        if len({_normalize_text_for_diversity(str(r["candidate_text"])) for r in lang_rows}) < 8:
            raise HoldoutError(f"V7 {lang}: requires at least 8 unique candidate texts")

        groups: dict[str, list[str]] = {}
        for row in lang_rows:
            groups.setdefault(_normalize_text_for_diversity(str(row["source_text"])), []).append(
                _normalize_text_for_diversity(str(row["candidate_text"]))
            )
        for source, candidates in groups.items():
            for a_idx in range(len(candidates)):
                for b_idx in range(a_idx + 1, len(candidates)):
                    a, b = candidates[a_idx], candidates[b_idx]
                    if a != b and SequenceMatcher(None, a, b).ratio() >= 0.985:
                        raise HoldoutError(
                            f"V7 {lang}: near-duplicate candidates detected for one source; author an independent case"
                        )

    return {
        "total": len(rows),
        "unique_sources": len(unique_sources),
        "unique_source_families": len(unique_source_families),
        "unique_candidates": len(unique_candidates),
        "unique_fault_classes": len(fault_counts),
        "fault_class_counts": dict(sorted(fault_counts.items())),
        "reviewer_count": len(reviewer_ids | second_reviewer_ids),
        "author_count": len(author_ids),
        "authors_by_fault": {k: len(v) for k, v in sorted(authors_by_fault.items())},
        "by_language": {
            lang: {
                "total": len(lang_rows),
                "unique_sources": len({_normalize_text_for_diversity(str(r["source_text"])) for r in lang_rows}),
                "unique_source_families": len({_normalize_text_for_family(str(r["source_text"])) for r in lang_rows}),
                "unique_candidates": len({_normalize_text_for_diversity(str(r["candidate_text"])) for r in lang_rows}),
                "expected_pass_total": sum(r["expected_decision"] == "PASS" for r in lang_rows),
                "expected_block_total": sum(r["expected_decision"] == "BLOCK" for r in lang_rows),
            }
            for lang, lang_rows in sorted(by_language.items())
        },
    }


def _actual_provider_config(provider: str) -> dict:
    if provider == "openai":
        from signallock.providers.openai_http import v7_provider_config
        return v7_provider_config()
    return {}


def _runtime_binding(*, provider: str, model: str, provider_config: dict | None = None) -> dict:
    from signallock.contracts.schema import SafetyContract
    from signallock.providers.openai_http import EXTRACTION_SYSTEM_PROMPT, _strict_schema

    environment = execution_environment()
    environment_hash = environment_sha256(environment)
    config = dict(provider_config or {"store": True})
    prompt_sha256 = sha256_bytes(EXTRACTION_SYSTEM_PROMPT.encode("utf-8"))
    schema_payload = json.dumps(
        _strict_schema(SafetyContract.model_json_schema()), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    schema_sha256 = sha256_bytes(schema_payload)
    canonical = json.dumps(
        {
            "provider": provider,
            "model": model,
            "provider_config": config,
            "prompt_sha256": prompt_sha256,
            "structured_schema_sha256": schema_sha256,
            "execution_environment": environment,
            "environment_sha256": environment_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "provider": provider,
        "model": model,
        "provider_config": config,
        "prompt_sha256": prompt_sha256,
        "structured_schema_sha256": schema_sha256,
        "execution_environment": environment,
        "environment_sha256": environment_hash,
        "fingerprint_sha256": sha256_bytes(canonical),
    }


def seal_v7_holdout_strict(
    input_path: Path,
    output_path: Path,
    manifest_path: Path,
    *,
    schema_version: str,
    verifier_version: str,
    extractor_version: str,
    prompt_version: str,
    code_commit: str,
    provider: str,
    model: str,
    provider_config: dict | None = None,
) -> dict:
    rows = load_jsonl(input_path)
    quality = validate_v7_quality(rows)
    require_qualification_environment()
    manifest = seal_holdout(
        input_path,
        output_path,
        manifest_path,
        schema_version=schema_version,
        verifier_version=verifier_version,
        extractor_version=extractor_version,
        prompt_version=prompt_version,
        code_commit=code_commit,
    )
    actual_config = _actual_provider_config(provider)
    if provider_config is not None and dict(provider_config) != actual_config:
        raise HoldoutError(
            f"V7 provider_config must equal the code-owned runtime configuration: {actual_config!r}"
        )
    manifest["strict_v7"] = True
    manifest["quality"] = quality
    manifest["runtime_binding"] = _runtime_binding(
        provider=provider, model=model, provider_config=actual_config
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_v7_runtime_binding(manifest: dict, *, provider: str, model: str) -> None:
    if manifest.get("strict_v7") is not True:
        raise HoldoutError("V7 manifest was not created by the strict V7 sealer")
    expected = manifest.get("runtime_binding") or {}
    if expected.get("provider") != provider or expected.get("model") != model:
        raise HoldoutError(
            f"V7 runtime provider/model mismatch: sealed {expected.get('provider')}/{expected.get('model')}, "
            f"runtime {provider}/{model}"
        )
    actual_config = _actual_provider_config(provider)
    if expected.get("provider_config") != actual_config:
        raise HoldoutError(
            f"V7 sealed provider_config does not match code-owned runtime config: {actual_config!r}"
        )
    actual = _runtime_binding(provider=provider, model=model, provider_config=actual_config)
    if not expected.get("execution_environment") or not expected.get("environment_sha256"):
        raise HoldoutError("V7 runtime binding lacks execution environment evidence")
    if actual != expected:
        raise HoldoutError("V7 model/config/prompt/schema fingerprint does not match the sealed runtime")

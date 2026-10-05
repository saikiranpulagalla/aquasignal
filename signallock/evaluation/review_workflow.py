from __future__ import annotations

import hashlib
import json
import random
import secrets
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

from signallock.contracts.provenance import validate_provenance
from signallock.contracts.schema import SafetyContract
from signallock.evaluation.holdout import HoldoutError, V7_REQUIRED_FAULT_CLASSES, _language_cue_hits, _script_fraction

UNSAFE_CLASSES = tuple(sorted(V7_REQUIRED_FAULT_CLASSES - {"clean"}))

AUTHORING_INSTRUCTIONS = {
    "clean": (
        "Create a natural translation in the requested language that preserves every operational relation, "
        "modality, audience, area, condition, quantity, exception, time constraint, and action. Do not add facts."
    ),
    "action_area": (
        "Create a fluent translation but introduce exactly one action-to-area binding error: keep all named actions "
        "and areas present while assigning an action to the wrong area. Preserve everything else."
    ),
    "action_audience": (
        "Create a fluent translation but introduce exactly one action-to-audience binding error: keep all actions "
        "and audiences present while assigning an action to the wrong audience. Preserve everything else."
    ),
    "quantity_exception_binding": (
        "Create a fluent translation but introduce exactly one quantity/exception binding error: keep the same "
        "values/exceptions present while attaching one to the wrong directive. Preserve everything else."
    ),
    "modality": (
        "Create a fluent translation but change exactly one obligation strength or deontic meaning (for example "
        "MAY↔MUST or NOT_REQUIRED↔REQUIRED). Preserve the action and all other scope."
    ),
    "temporal": (
        "Create a fluent translation but change exactly one temporal relation (for example BEFORE↔AFTER or "
        "UNTIL↔AFTER) while preserving the same clock/deadline value and other meaning."
    ),
    "logic_sequence": (
        "Create a fluent translation but change exactly one logical/ordering relation (for example OR↔AND or "
        "reverse an explicitly ordered action sequence). Preserve the actions themselves."
    ),
}


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise HoldoutError(f"{path}: line {line_no}: invalid JSON") from exc
    if not rows:
        raise HoldoutError(f"{path}: no rows")
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n" for row in rows), encoding="utf-8")


def _reference(row: dict) -> str:
    return str(row.get("source_reference") or row.get("source_url") or row.get("source_note") or row.get("case_id") or "").strip()


def prepare_authoring_packet(official_seed_path: Path, challenge_seed_path: Path) -> list[dict]:
    """Create a deterministic 24-case authoring plan without generating candidate text.

    Six clean cases per language come from fresh official-source seeds. One unsafe case
    per required fault class per language comes from a distinct independently-authored
    challenge source. Candidate text remains blank by design; a human author must fill it.
    """
    official = _read_jsonl(official_seed_path)
    challenge = _read_jsonl(challenge_seed_path)
    if len(official) < 6:
        raise HoldoutError("V7 authoring packet needs at least 6 fresh official clean source seeds")

    by_fault: dict[str, list[dict]] = {fault: [] for fault in UNSAFE_CLASSES}
    for row in challenge:
        cid = str(row.get("case_id", ""))
        inferred = None
        for fault in UNSAFE_CLASSES:
            if fault.replace("_", "-") in cid:
                inferred = fault
                break
        if inferred is None:
            # Explicit field wins when a case-id is intentionally more readable.
            candidate = str(row.get("fault_class", "")).strip().casefold()
            if candidate in by_fault:
                inferred = candidate
        if inferred is None:
            # Known bundled naming conventions.
            if "quantity-exception" in cid:
                inferred = "quantity_exception_binding"
            elif "logic-sequence" in cid:
                inferred = "logic_sequence"
        if inferred:
            by_fault[inferred].append(row)
    for fault, rows in by_fault.items():
        if len(rows) < 2:
            raise HoldoutError(f"V7 challenge seeds need at least two distinct sources for {fault}")

    tasks: list[dict] = []
    clean_seeds = official[:6]
    for lang in ("hi", "te"):
        for idx, seed in enumerate(clean_seeds, start=1):
            tasks.append({
                "task_id": f"{lang}-clean-{idx:02d}-{seed['case_id']}",
                "source_seed_id": seed["case_id"],
                "source_text": seed["text"],
                "source_language": seed.get("language", "en"),
                "source_reference": _reference(seed),
                "candidate_language": lang,
                "target_decision": "PASS",
                "fault_class": "clean",
                "authoring_instruction": AUTHORING_INSTRUCTIONS["clean"],
                "candidate_text": "",
                "author_id": "",
                "source_contract": None,
                "authority_reviewer_id": "",
                "authority_reviewed_at": "",
                "authority_notes": "",
            })

        # Use a different source variant per language so the unsafe half is not padded by translation clones.
        variant = 0 if lang == "hi" else 1
        for fault in UNSAFE_CLASSES:
            seed = by_fault[fault][variant]
            tasks.append({
                "task_id": f"{lang}-{fault}-{seed['case_id']}",
                "source_seed_id": seed["case_id"],
                "source_text": seed["text"],
                "source_language": seed.get("language", "en"),
                "source_reference": _reference(seed),
                "candidate_language": lang,
                "target_decision": "BLOCK",
                "fault_class": fault,
                "authoring_instruction": AUTHORING_INSTRUCTIONS[fault],
                "candidate_text": "",
                "author_id": "",
                "source_contract": None,
                "authority_reviewer_id": "",
                "authority_reviewed_at": "",
                "authority_notes": "",
            })
    validate_authoring_packet(tasks, require_completed=False)
    return tasks


def validate_authoring_packet(rows: list[dict], *, require_completed: bool) -> dict:
    if len(rows) != 24:
        raise HoldoutError(f"V7 authoring packet must contain exactly 24 planned cases, got {len(rows)}")
    ids = [str(r.get("task_id", "")) for r in rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise HoldoutError("V7 authoring task_id values must be nonblank and unique")

    by_lang: dict[str, list[dict]] = {"hi": [], "te": []}
    fault_counts = Counter()
    for i, row in enumerate(rows, start=1):
        lang = str(row.get("candidate_language", "")).split("-")[0].casefold()
        if lang not in by_lang:
            raise HoldoutError(f"row {i}: candidate_language must be hi or te")
        source_lang = str(row.get("source_language", "")).split("-")[0].casefold()
        if source_lang != "en":
            raise HoldoutError(f"row {i}: V7 authoritative source_language must be English ('en')")
        fault = str(row.get("fault_class", "")).strip().casefold()
        target = str(row.get("target_decision", "")).upper()
        if fault not in V7_REQUIRED_FAULT_CLASSES:
            raise HoldoutError(f"row {i}: unsupported V7 fault_class {fault!r}")
        if (fault == "clean") != (target == "PASS"):
            raise HoldoutError(f"row {i}: clean rows must target PASS and unsafe rows must target BLOCK")
        by_lang[lang].append(row)
        fault_counts[fault] += 1

        if require_completed:
            candidate = str(row.get("candidate_text", "")).strip()
            author = str(row.get("author_id", "")).strip()
            if not candidate or not author:
                raise HoldoutError(f"row {i}: completed packet requires candidate_text and author_id")
            script_chars, letters, fraction = _script_fraction(candidate, lang)
            if script_chars < 3 or fraction < 0.50:
                raise HoldoutError(
                    f"row {i}: candidate does not independently validate as {lang} script ({script_chars}/{letters})"
                )
            if _language_cue_hits(candidate, lang) < 1:
                raise HoldoutError(f"row {i}: candidate has {lang} script but lacks an independent {lang} language cue")
            reviewer = str(row.get("authority_reviewer_id", "")).strip()
            reviewed_at = str(row.get("authority_reviewed_at", "")).strip()
            if not reviewer or not reviewed_at:
                raise HoldoutError(f"row {i}: source authority contract requires reviewer identity and timestamp")
            try:
                t = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    raise ValueError
            except ValueError as exc:
                raise HoldoutError(f"row {i}: authority_reviewed_at must include timezone") from exc
            if _identity_key(reviewer) == _identity_key(author):
                raise HoldoutError(f"row {i}: candidate author cannot review the source authority contract")
            if not isinstance(row.get("source_contract"), dict):
                raise HoldoutError(f"row {i}: completed packet requires a reviewed source_contract object")
            try:
                contract = SafetyContract.model_validate(row["source_contract"])
            except Exception as exc:
                raise HoldoutError(f"row {i}: invalid reviewed source_contract: {exc}") from exc
            if contract.language.split("-")[0].casefold() != str(row.get("source_language", "en")).split("-")[0].casefold():
                raise HoldoutError(f"row {i}: source_contract language mismatch")
            errors = validate_provenance(str(row["source_text"]), contract, require_p0=True)
            if errors:
                raise HoldoutError(f"row {i}: reviewed source_contract provenance invalid: {'; '.join(errors)}")

    for lang, lang_rows in by_lang.items():
        if len(lang_rows) != 12:
            raise HoldoutError(f"V7 {lang}: authoring packet must contain 12 cases")
        if sum(r["target_decision"] == "PASS" for r in lang_rows) != 6:
            raise HoldoutError(f"V7 {lang}: authoring packet must contain exactly 6 clean PASS targets")
        unsafe = [r for r in lang_rows if r["target_decision"] == "BLOCK"]
        if len(unsafe) != 6:
            raise HoldoutError(f"V7 {lang}: authoring packet must contain exactly 6 unsafe BLOCK targets")
        observed = {str(r["fault_class"]) for r in unsafe}
        if observed != set(UNSAFE_CLASSES):
            raise HoldoutError(f"V7 {lang}: unsafe tasks must cover each critical fault exactly once")
    return {
        "total": len(rows),
        "by_language": {lang: len(v) for lang, v in by_lang.items()},
        "fault_class_counts": dict(sorted(fault_counts.items())),
        "completed": require_completed,
    }


def _identity_key(value: object) -> str:
    """Canonicalize human-role labels, including invisible Unicode format aliases."""
    import unicodedata
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")
    return " ".join(normalized.split()).casefold()


def _json_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _authored_packet_sha256(rows: list[dict]) -> str:
    return _json_sha256(rows)


BLIND_CONTENT_FIELDS = ("source_text", "source_language", "candidate_text", "candidate_language")
BLIND_REVIEW_FIELDS = {
    "review_id", *BLIND_CONTENT_FIELDS, "reviewer_id", "reviewed_at", "verdict", "notes"
}
BLIND_FORBIDDEN_FIELDS = {
    "task_id", "case_id", "target_decision", "expected_decision", "fault_class",
    "authoring_instruction", "author_id", "source_reference", "source_seed_id",
    "authority_reviewer_id", "authority_reviewed_at", "authority_notes",
}


def _review_content_sha256(row: dict) -> str:
    return _json_sha256({field: row.get(field) for field in BLIND_CONTENT_FIELDS})


def _review_task_binding_sha256(row: dict) -> str:
    return _json_sha256({
        "task_id": str(row.get("task_id", "")),
        "content_sha256": _review_content_sha256(row),
        "authored_row_sha256": _json_sha256(row),
    })


def _mapping_sha256(mapping: dict) -> str:
    payload = dict(mapping)
    payload.pop("mapping_sha256", None)
    return _json_sha256(payload)


def _new_review_id(prefix: str, used: set[str]) -> str:
    while True:
        value = f"{prefix}-{secrets.token_urlsafe(12)}"
        if value not in used:
            used.add(value)
            return value


def _shuffle_away_from_original(items: list[dict], original_task_order: list[str], role_map: dict[str, dict]) -> None:
    random.SystemRandom().shuffle(items)
    resolved = [role_map[item["review_id"]]["task_id"] for item in items]
    if resolved == original_task_order and len(items) > 1:
        items.append(items.pop(0))


def make_blind_review_templates(authored_rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Create role-specific blinded review sheets plus a private integrity mapping.

    The reviewer sheets intentionally contain neither descriptive task IDs nor source references.
    Each role receives unrelated opaque IDs and independently shuffled ordering.  The private map
    binds every review ID to both the authored task and an exact hash of the semantic content shown
    to the reviewer, so finalization can reject label leakage or edited review text.
    """
    validate_authoring_packet(authored_rows, require_completed=True)
    primary: list[dict] = []
    secondary: list[dict] = []
    mapping: dict = {
        "version": "3.0",
        "authored_sha256": _authored_packet_sha256(authored_rows),
        "primary": {},
        "secondary": {},
    }
    used: set[str] = set()
    original_task_order = [str(row["task_id"]) for row in authored_rows]
    for row in authored_rows:
        content = {
            "source_text": row["source_text"],
            "source_language": row["source_language"],
            "candidate_text": row["candidate_text"],
            "candidate_language": row["candidate_language"],
        }
        for role, target, prefix in (("primary", primary, "P"), ("secondary", secondary, "S")):
            review_id = _new_review_id(prefix, used)
            item = {
                "review_id": review_id,
                **content,
                "reviewer_id": "",
                "reviewed_at": "",
                "verdict": "UNREVIEWED",
                "notes": "",
            }
            mapping[role][review_id] = {
                "task_id": row["task_id"],
                "content_sha256": _review_content_sha256(item),
                "task_binding_sha256": _review_task_binding_sha256(row),
            }
            target.append(item)

    _shuffle_away_from_original(primary, original_task_order, mapping["primary"])
    _shuffle_away_from_original(secondary, original_task_order, mapping["secondary"])
    primary_order = [mapping["primary"][r["review_id"]]["task_id"] for r in primary]
    secondary_order = [mapping["secondary"][r["review_id"]]["task_id"] for r in secondary]
    if secondary_order == primary_order and len(secondary) > 1:
        secondary.append(secondary.pop(0))
    mapping["primary_order_sha256"] = _json_sha256([r["review_id"] for r in primary])
    mapping["secondary_order_sha256"] = _json_sha256([r["review_id"] for r in secondary])
    mapping["mapping_sha256"] = _mapping_sha256(mapping)
    return primary, secondary, mapping


def _load_review_mapping(path: Path, authored_rows: list[dict]) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HoldoutError(f"{path}: invalid blind-review mapping: {exc}") from exc
    if payload.get("version") != "3.0":
        raise HoldoutError(f"{path}: unsupported blind-review mapping version")
    if payload.get("mapping_sha256") != _mapping_sha256(payload):
        raise HoldoutError(f"{path}: blind-review mapping integrity hash mismatch")
    if payload.get("authored_sha256") != _authored_packet_sha256(authored_rows):
        raise HoldoutError(f"{path}: blind-review mapping does not match the exact authored packet")
    authored_by_id = {str(r["task_id"]): r for r in authored_rows}
    authored_ids = set(authored_by_id)
    for role in ("primary", "secondary"):
        section = payload.get(role)
        if not isinstance(section, dict) or len(section) != len(authored_rows):
            raise HoldoutError(f"{path}: {role} mapping coverage is incomplete")
        task_ids = {str(v.get("task_id", "")) for v in section.values() if isinstance(v, dict)}
        if task_ids != authored_ids:
            missing = sorted(authored_ids - task_ids); extra = sorted(task_ids - authored_ids)
            raise HoldoutError(f"{path}: {role} mapping task coverage mismatch; missing={missing}, extra={extra}")
        for review_id, mapped in section.items():
            if not isinstance(mapped, dict):
                raise HoldoutError(f"{path}: {role} mapping entry {review_id!r} is malformed")
            task_id = str(mapped.get("task_id", ""))
            authored_row = authored_by_id.get(task_id)
            if authored_row is None:
                raise HoldoutError(f"{path}: {role} mapping entry resolves to unknown task")
            expected_content = _review_content_sha256(authored_row)
            if mapped.get("content_sha256") != expected_content:
                raise HoldoutError(
                    f"{path}: {role} mapping entry {review_id!r} content is not bound to authored task {task_id!r}"
                )
            expected_binding = _review_task_binding_sha256(authored_row)
            if mapped.get("task_binding_sha256") != expected_binding:
                raise HoldoutError(
                    f"{path}: {role} mapping entry {review_id!r} task binding mismatch"
                )
    return payload


def _index_reviews(path: Path, *, role: str, role_map: dict[str, dict]) -> dict[str, dict]:
    rows = _read_jsonl(path)
    out: dict[str, dict] = {}
    seen_review_ids: set[str] = set()
    for i, row in enumerate(rows, start=1):
        hidden = BLIND_FORBIDDEN_FIELDS & set(row)
        if hidden:
            raise HoldoutError(f"{path}: row {i}: blinded review contains hidden fields {sorted(hidden)}")
        extra = set(row) - BLIND_REVIEW_FIELDS
        if extra:
            raise HoldoutError(f"{path}: row {i}: unexpected review fields {sorted(extra)}")
        review_id = str(row.get("review_id", "")).strip()
        if not review_id or review_id in seen_review_ids:
            raise HoldoutError(f"{path}: row {i}: review_id must be unique and nonblank")
        seen_review_ids.add(review_id)
        mapped = role_map.get(review_id)
        if not isinstance(mapped, dict):
            raise HoldoutError(f"{path}: row {i}: unknown {role} review_id")
        if _review_content_sha256(row) != mapped.get("content_sha256"):
            raise HoldoutError(f"{path}: row {i}: reviewed source/candidate content changed after blinding")
        reviewer = str(row.get("reviewer_id", "")).strip()
        reviewed_at = str(row.get("reviewed_at", "")).strip()
        verdict = str(row.get("verdict", "")).strip().upper()
        if not reviewer or not reviewed_at or verdict not in {"PASS", "REVIEW", "BLOCK"}:
            raise HoldoutError(f"{path}: row {i}: reviewer_id, reviewed_at and PASS/REVIEW/BLOCK verdict required")
        try:
            t = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if t.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise HoldoutError(f"{path}: row {i}: reviewed_at must include timezone") from exc
        task_id = str(mapped.get("task_id", "")).strip()
        if not task_id or task_id in out:
            raise HoldoutError(f"{path}: row {i}: mapping resolves to duplicate/blank task_id")
        out[task_id] = row
    if seen_review_ids != set(role_map):
        missing = sorted(set(role_map) - seen_review_ids); extra = sorted(seen_review_ids - set(role_map))
        raise HoldoutError(f"{path}: {role} review coverage mismatch; missing={missing}, extra={extra}")
    return out


def _parse_tz_time(value: str, *, label: str) -> datetime:
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if t.tzinfo is None:
            raise ValueError
        return t
    except ValueError as exc:
        raise HoldoutError(f"{label} must include timezone") from exc


def finalize_reviewed_holdout(
    authored_path: Path,
    primary_path: Path,
    secondary_path: Path,
    mapping_path: Path,
) -> list[dict]:
    authored = _read_jsonl(authored_path)
    validate_authoring_packet(authored, require_completed=True)
    mapping = _load_review_mapping(mapping_path, authored)
    primary = _index_reviews(primary_path, role="primary", role_map=mapping["primary"])
    secondary = _index_reviews(secondary_path, role="secondary", role_map=mapping["secondary"])

    final: list[dict] = []
    for row in authored:
        task_id = row["task_id"]
        p = primary[task_id]
        target = row["target_decision"]
        if p["verdict"].upper() != target:
            raise HoldoutError(f"{task_id}: blinded primary reviewer disagrees with target {target}; retire/replace this case")
        author = str(row["author_id"]).strip()
        authority_reviewer = str(row["authority_reviewer_id"]).strip()
        primary_reviewer = str(p["reviewer_id"]).strip()
        if _identity_key(primary_reviewer) == _identity_key(author):
            raise HoldoutError(f"{task_id}: primary reviewer must be independent of the candidate author")
        if _identity_key(primary_reviewer) == _identity_key(authority_reviewer):
            raise HoldoutError(f"{task_id}: primary reviewer must be independent of the authority reviewer")
        authority_time = _parse_tz_time(str(row["authority_reviewed_at"]), label=f"{task_id}: authority_reviewed_at")
        primary_time = _parse_tz_time(str(p["reviewed_at"]), label=f"{task_id}: primary reviewed_at")
        if primary_time < authority_time:
            raise HoldoutError(f"{task_id}: primary review predates authority-contract review")

        s = secondary[task_id]
        if s["verdict"].upper() != target:
            raise HoldoutError(f"{task_id}: blinded secondary reviewer disagrees with target {target}; retire/replace this case")
        second_reviewer = str(s["reviewer_id"]).strip()
        if _identity_key(second_reviewer) in {
            _identity_key(author), _identity_key(primary_reviewer), _identity_key(authority_reviewer)
        }:
            raise HoldoutError(
                f"{task_id}: secondary reviewer must be distinct from author, authority reviewer, and primary reviewer"
            )
        second_time = _parse_tz_time(str(s["reviewed_at"]), label=f"{task_id}: secondary reviewed_at")
        if second_time < authority_time:
            raise HoldoutError(f"{task_id}: secondary review predates authority-contract review")

        final.append({
            "case_id": task_id,
            "source_text": row["source_text"],
            "source_language": row["source_language"],
            "source_contract": row["source_contract"],
            "candidate_text": row["candidate_text"],
            "candidate_language": row["candidate_language"],
            "expected_decision": target,
            "human_reviewed": True,
            "reviewer_id": primary_reviewer,
            "reviewed_at": p["reviewed_at"],
            "source_reference": row["source_reference"],
            "fault_class": row["fault_class"],
            "second_reviewer_id": second_reviewer,
            "author_id": author,
            "authority_reviewer_id": authority_reviewer,
            "authority_reviewed_at": row["authority_reviewed_at"],
            "authority_notes": str(row.get("authority_notes", "")),
            "primary_review_notes": str(p.get("notes", "")),
            "second_reviewed_at": s["reviewed_at"],
            "second_review_notes": str(s.get("notes", "")),
        })
    return final


__all__ = [
    "AUTHORING_INSTRUCTIONS",
    "UNSAFE_CLASSES",
    "prepare_authoring_packet",
    "validate_authoring_packet",
    "make_blind_review_templates",
    "finalize_reviewed_holdout",
    "_write_jsonl",
    "_identity_key",
]

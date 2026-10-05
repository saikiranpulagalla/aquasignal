from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass

import httpx

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.normalization import canonical_text, normalize_time_string, quantities_equivalent
from signallock.contracts.provenance import repair_provenance_offsets, validate_provenance
from signallock.contracts.schema import Action, ActionType, Modality, Quantity, SafetyContract, TemporalOperator
from signallock.verification.engine import Relation, _canon_verb, _text_relation


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_EXTRACTION_PROVIDER_CONFIG = {"store": False}
OPENAI_V7_PROVIDER_CONFIG = {"store": True}


def extraction_provider_config() -> dict:
    """Code-owned default extraction configuration for ordinary/demo requests."""
    return dict(OPENAI_EXTRACTION_PROVIDER_CONFIG)


def v7_provider_config() -> dict:
    """Code-owned V7 qualification configuration; stored responses are mandatory."""
    return dict(OPENAI_V7_PROVIDER_CONFIG)


EXTRACTION_SYSTEM_PROMPT = (
    "You extract safety-critical operational facts from emergency alerts. "
    "Never infer an unstated action, location, audience, number, exception, time, urgency, severity, or certainty. "
    "Use null/empty lists for absent facts. Evidence spans for every required action, prohibited action, and quantity must be exact substrings of the input. "
    "Required actions are things recipients should do. Prohibited actions are things recipients must not do. "
    "Canonicalize semantic slots into language-independent English labels where possible. For every action, also bind modality, scoped_audience, scoped_areas, temporal_operator, bound_quantities, bound_exceptions, sequence_index, and logic_operator when stated; never flatten relationships into global bags. "
    "Keep evidence.quote in the original source language exactly; never translate evidence text or invent offsets. "
    "If an operational clause is ambiguous or cannot be confidently normalized, copy that exact clause into unresolved_operational_text instead of guessing."
)


def _native_negative_polarity(root: str, quote: str) -> bool:
    """Return True only for explicit negative/prohibitive morphology we support.

    Absence of a marker is not treated as positive polarity because verbs such as
    "avoid" are semantically protective without a surface negation token.
    """
    q = quote.casefold()
    if root == "hi":
        # Standalone न/ना, नहीं and मत plus common imperative-negative forms.
        if "नहीं" in q or "मत" in q:
            return True
        if re.search(r"(?:^|[\s।.!?,;:])न(?:\s|$|[।.!?,;:])", q):
            return True
        if re.search(r"(?:^|[\s।.!?,;:])ना(?:\s|$|[।.!?,;:])", q):
            return True
        return False
    if root == "te":
        # వద్దు also appears attached to verbs (e.g. వెళ్లవద్దు / తాగవద్దు).
        return any(marker in q for marker in ("వద్దు", "కూడదు", "చేయకండి"))
    return False


def _native_semantic_guard(text: str, contract: SafetyContract) -> list[str]:
    """Independent deterministic guard for the supported Hindi/Telugu demo boundary.

    The guard never treats model structure as proof of polarity.  Explicit surface
    negation is detected before action recognition and is checked against both the
    action fields and required/prohibited list membership.
    """
    root = (contract.language or "").split("-")[0].casefold()
    if root == "en":
        return []

    unresolved: list[str] = []
    indexed_actions = [
        (False, action) for action in contract.required_actions
    ] + [
        (True, action) for action in contract.prohibited_actions
    ]
    for idx, (listed_prohibited, action) in enumerate(indexed_actions):
        quote = action.evidence.quote if action.evidence else ""
        q = quote.casefold()
        recognized = False
        inferred_type = None
        inferred_verb = None
        inferred_object = None
        explicit_negative = _native_negative_polarity(root, q)
        inferred_negative = True if explicit_negative else None
        inferred_modality = None
        inferred_temporal = None

        if root == "hi":
            if any(x in q for x in ("शरण", "घर के अंदर", "अंदर रहें")):
                recognized, inferred_type, inferred_verb = True, ActionType.SHELTER, "shelter"
            if any(x in q for x in ("बाहर निकल", "खाली कर", "निकासी")):
                recognized, inferred_type, inferred_verb = True, ActionType.EVACUATE, "evacuate"
            if any(x in q for x in ("सड़क", "सड़कों")) and any(x in q for x in ("बचें", "बचना", "दूर रहें")):
                recognized, inferred_type, inferred_verb, inferred_object = True, ActionType.AVOID, "avoid", "roads"
            if "पानी" in q and any(x in q for x in ("पिए", "पिएं", "पीए", "पीना")):
                recognized, inferred_type, inferred_verb, inferred_object = True, ActionType.EXECUTE, "drink", "water"
            if "प्रवेश" in q:
                recognized, inferred_verb = True, "enter"
            if any(x in q for x in ("सकते हैं", "सकती हैं", "सकता है")):
                inferred_modality = Modality.MAY
            elif "सलाह" in q:
                inferred_modality = Modality.SHOULD
            elif recognized and "चाहिए" not in q:
                inferred_modality = Modality.MUST
            if explicit_negative:
                inferred_modality = Modality.PROHIBITED
            if "के बाद" in q:
                inferred_temporal = TemporalOperator.AFTER
            elif "से पहले" in q or "के पहले" in q:
                inferred_temporal = TemporalOperator.BEFORE
            elif "तक" in q:
                inferred_temporal = TemporalOperator.UNTIL
        elif root == "te":
            if any(x in q for x in ("ఆశ్రయం", "ఇంట్లో", "లోపల")):
                recognized, inferred_type, inferred_verb = True, ActionType.SHELTER, "shelter"
            if any(x in q for x in ("బయటకు", "ఖాళీ", "తరలించ")):
                recognized, inferred_type, inferred_verb = True, ActionType.EVACUATE, "evacuate"
            if any(x in q for x in ("రోడ్లు", "రోడ్ల")) and any(x in q for x in ("నివారించ", "దూరంగా")):
                recognized, inferred_type, inferred_verb, inferred_object = True, ActionType.AVOID, "avoid", "roads"
            if any(x in q for x in ("నీరు", "నీటిని")) and any(x in q for x in ("త్రాగ", "తాగ")):
                recognized, inferred_type, inferred_verb, inferred_object = True, ActionType.EXECUTE, "drink", "water"
            if "ప్రవేశ" in q:
                recognized, inferred_verb = True, "enter"
            if any(x in q for x in ("వచ్చు", "గలరు")):
                inferred_modality = Modality.MAY
            elif any(x in q for x in ("చేయాలి", "వలెను")):
                inferred_modality = Modality.MUST
            elif recognized:
                inferred_modality = Modality.MUST
            if explicit_negative:
                inferred_modality = Modality.PROHIBITED
            if "తర్వాత" in q:
                inferred_temporal = TemporalOperator.AFTER
            elif "ముందు" in q:
                inferred_temporal = TemporalOperator.BEFORE
            elif "వరకు" in q:
                inferred_temporal = TemporalOperator.UNTIL

        contradictions: list[str] = []
        if inferred_type is not None and action.type != inferred_type:
            contradictions.append(f"action type {action.type.value} != {inferred_type.value}")
        if inferred_verb is not None and action.verb.casefold() != inferred_verb:
            contradictions.append(f"verb {action.verb!r} != {inferred_verb!r}")
        if inferred_object is not None and (action.object or "").casefold() != inferred_object:
            contradictions.append(f"object {action.object!r} != {inferred_object!r}")
        if inferred_negative is not None and action.negated != inferred_negative:
            contradictions.append(f"negation {action.negated} != {inferred_negative}")
        if explicit_negative and not listed_prohibited:
            contradictions.append("explicitly negative evidence was placed in required_actions")
        if explicit_negative and action.modality != Modality.PROHIBITED:
            contradictions.append(f"modality {action.modality.value} != {Modality.PROHIBITED.value}")
        elif inferred_modality is not None and action.modality != inferred_modality:
            contradictions.append(f"modality {action.modality.value} != {inferred_modality.value}")
        if inferred_temporal is not None:
            observed_ops = {x.operator for x in action.temporal_constraints}
            if not observed_ops and action.temporal_operator:
                observed_ops = {action.temporal_operator}
            if inferred_temporal not in observed_ops:
                contradictions.append(f"temporal operator does not contain {inferred_temporal.value}")

        if contradictions:
            unresolved.append(f"independent semantic contradiction in P0 evidence for action[{idx}]: {quote} ({'; '.join(dict.fromkeys(contradictions))})")
        elif not recognized:
            unresolved.append(f"independent semantic validation unavailable for P0 evidence action[{idx}]: {quote}")
    return unresolved


def _coverage_text_contains(expected: str, observed: list[str]) -> bool:
    return any(
        _text_relation(expected, item, source_language="en", candidate_language="en") == Relation.MATCH
        for item in observed
    )


def _coverage_quantity_matches(expected: Quantity, observed: Quantity) -> bool:
    if not quantities_equivalent(expected.value, expected.unit, observed.value, observed.unit):
        return False
    if expected.relation.value != "Unknown" and expected.relation != observed.relation:
        return False
    if expected.meaning and _text_relation(
        expected.meaning, observed.meaning, source_language="en", candidate_language="en"
    ) != Relation.MATCH:
        return False
    return True


def _coverage_temporal_keys(action: Action) -> set[tuple[str, str]]:
    if action.temporal_constraints:
        return {
            (row.operator.value, normalize_time_string(row.time) or canonical_text(row.time))
            for row in action.temporal_constraints
        }
    if action.deadline or action.temporal_operator:
        return {
            (
                action.temporal_operator.value if action.temporal_operator else "UNKNOWN",
                normalize_time_string(action.deadline or "") or canonical_text(action.deadline or ""),
            )
        }
    return set()


def _coverage_text_sets_equivalent(left: list[str], right: list[str]) -> bool:
    return all(_coverage_text_contains(item, right) for item in left) and all(
        _coverage_text_contains(item, left) for item in right
    )


def _coverage_quantities_equivalent(left: list[Quantity], right: list[Quantity]) -> bool:
    used: set[int] = set()
    for expected in left:
        match = next(
            (idx for idx, observed in enumerate(right) if idx not in used and _coverage_quantity_matches(expected, observed)),
            None,
        )
        if match is None:
            return False
        used.add(match)
    return len(used) == len(right)


def _provider_action_covers(expected: Action, observed: Action) -> bool:
    """Deterministically reconcile one provider action with one English anchor.

    This is intentionally stricter than ordinary verification matching.  Provider
    semantics are accepted as independently supported only when the deterministic
    anchor accounts for the same safety slots.  Extra model-only semantics are not
    discarded or trusted; they are routed to unresolved REVIEW by the caller.
    """
    if expected.type != observed.type or expected.negated != observed.negated:
        return False
    if _canon_verb(expected.verb) != _canon_verb(observed.verb):
        return False
    if expected.modality != observed.modality:
        return False

    for left, right in (
        (expected.object, observed.object),
        (expected.destination, observed.destination),
        (expected.condition, observed.condition),
    ):
        if bool(left) != bool(right):
            return False
        if left and _text_relation(left, right, source_language="en", candidate_language="en") != Relation.MATCH:
            return False

    if not _coverage_text_sets_equivalent(expected.scoped_audience, observed.scoped_audience):
        return False
    if not _coverage_text_sets_equivalent(expected.scoped_areas, observed.scoped_areas):
        return False

    if _coverage_temporal_keys(expected) != _coverage_temporal_keys(observed):
        return False
    if not _coverage_quantities_equivalent(list(expected.bound_quantities), list(observed.bound_quantities)):
        return False
    if not _coverage_text_sets_equivalent(expected.bound_exceptions, observed.bound_exceptions):
        return False

    if expected.logic_operator != observed.logic_operator:
        return False
    if expected.sequence_index != observed.sequence_index:
        return False
    return True


def _english_provider_coverage_guard(text: str, contract: SafetyContract) -> list[str]:
    """Independently detect provider omissions in English operational content.

    This is deliberately a coverage guard, not a second extractor verdict.  It uses
    the deterministic development extractor only to establish safety anchors and
    residual operational cues.  It never unions heuristic semantics into the model
    contract and never chooses PASS/BLOCK.  Uncovered material is preserved as
    unresolved text so the existing verifier fails closed to REVIEW.
    """
    root = (contract.language or "").split("-")[0].casefold()
    if root != "en":
        return []

    deterministic = HeuristicExtractor().extract(text, language="en", source_id=contract.source_id)
    findings: list[str] = [
        f"provider coverage unresolved operational clause: {clause}"
        for clause in deterministic.unresolved_operational_text
    ]

    def reconcile_actions(expected: list[Action], observed: list[Action], label: str) -> None:
        used: set[int] = set()
        for action in expected:
            match = next(
                (
                    idx
                    for idx, candidate in enumerate(observed)
                    if idx not in used and _provider_action_covers(action, candidate)
                ),
                None,
            )
            if match is None:
                quote = action.evidence.quote if action.evidence else f"{action.modality.value} {action.verb}"
                findings.append(f"provider coverage missing or altered {label}: {quote}")
            else:
                used.add(match)
        for idx, action in enumerate(observed):
            if idx not in used:
                quote = action.evidence.quote if action.evidence else f"{action.modality.value} {action.verb}"
                findings.append(f"provider coverage unconfirmed {label}: {quote}")

    reconcile_actions(deterministic.required_actions, contract.required_actions, "required directive")
    reconcile_actions(deterministic.prohibited_actions, contract.prohibited_actions, "prohibited directive")

    deterministic_audiences = list(deterministic.audience) + [
        item for action in deterministic.required_actions + deterministic.prohibited_actions for item in action.scoped_audience
    ]
    deterministic_areas = list(deterministic.affected_areas) + [
        item for action in deterministic.required_actions + deterministic.prohibited_actions for item in action.scoped_areas
    ]
    provider_audiences = list(contract.audience) + [
        item for action in contract.required_actions + contract.prohibited_actions for item in action.scoped_audience
    ]
    provider_areas = list(contract.affected_areas) + [
        item for action in contract.required_actions + contract.prohibited_actions for item in action.scoped_areas
    ]
    for item in deterministic_audiences:
        if not _coverage_text_contains(item, provider_audiences):
            findings.append(f"provider coverage missing audience: {item}")
    for item in provider_audiences:
        if not _coverage_text_contains(item, deterministic_audiences):
            findings.append(f"provider coverage unconfirmed audience: {item}")
    for item in deterministic_areas:
        if not _coverage_text_contains(item, provider_areas):
            findings.append(f"provider coverage missing area: {item}")
    for item in provider_areas:
        if not _coverage_text_contains(item, deterministic_areas):
            findings.append(f"provider coverage unconfirmed area: {item}")

    if deterministic.hazard is None and contract.hazard is not None:
        findings.append(f"provider coverage unconfirmed hazard: {contract.hazard.type}")
    elif deterministic.hazard is not None:
        if contract.hazard is None or _text_relation(
            deterministic.hazard.type,
            contract.hazard.type if contract.hazard else None,
            source_language="en",
            candidate_language="en",
        ) != Relation.MATCH:
            findings.append(f"provider coverage missing or altered hazard: {deterministic.hazard.type}")

    for field in ("urgency", "severity", "certainty"):
        expected = getattr(deterministic, field)
        observed = getattr(contract, field)
        if expected != observed:
            if expected.value == "Unknown":
                findings.append(f"provider coverage unconfirmed {field}: {observed.value}")
            else:
                findings.append(f"provider coverage missing or altered {field}: {expected.value}")

    provider_quantities = list(contract.quantities) + [
        item for action in contract.required_actions + contract.prohibited_actions for item in action.bound_quantities
    ]
    deterministic_quantities = list(deterministic.quantities) + [
        item for action in deterministic.required_actions + deterministic.prohibited_actions for item in action.bound_quantities
    ]
    for quantity in deterministic_quantities:
        if not any(_coverage_quantity_matches(quantity, item) for item in provider_quantities):
            findings.append(f"provider coverage missing quantity: {quantity.value:g} {quantity.unit}")
    for quantity in provider_quantities:
        if not any(_coverage_quantity_matches(quantity, item) for item in deterministic_quantities):
            findings.append(f"provider coverage unconfirmed quantity: {quantity.value:g} {quantity.unit}")

    deterministic_exceptions = [item.text for item in deterministic.exceptions] + [
        item for action in deterministic.required_actions + deterministic.prohibited_actions for item in action.bound_exceptions
    ]
    provider_exceptions = [item.text for item in contract.exceptions] + [
        item for action in contract.required_actions + contract.prohibited_actions for item in action.bound_exceptions
    ]
    for exception in deterministic_exceptions:
        if not _coverage_text_contains(exception, provider_exceptions):
            findings.append(f"provider coverage missing exception: {exception}")
    for exception in provider_exceptions:
        if not _coverage_text_contains(exception, deterministic_exceptions):
            findings.append(f"provider coverage unconfirmed exception: {exception}")

    return list(dict.fromkeys(findings))


def _bind_model_scopes(text: str, contract: SafetyContract) -> None:
    # Safe only when the global scope is singular. Multiple global scopes are not
    # guessed onto every action; that uncertainty is surfaced instead.
    for action in contract.required_actions + contract.prohibited_actions:
        ev_start = action.evidence.start_char if action.evidence else 0
        ev_end = action.evidence.end_char if action.evidence else 0
        left = max(text.rfind(".", 0, ev_start), text.rfind("।", 0, ev_start), text.rfind("!", 0, ev_start), text.rfind("?", 0, ev_start)) + 1
        right_candidates = [x for x in (text.find(".", ev_end), text.find("।", ev_end), text.find("!", ev_end), text.find("?", ev_end)) if x >= 0]
        right = min(right_candidates) if right_candidates else len(text)
        sentence = text[left:right].casefold()
        root = (contract.language or "").split("-")[0].casefold()
        audience_cue = False
        if len(contract.audience) == 1:
            canonical = contract.audience[0].casefold()
            audience_cue = canonical in sentence
            if root == "hi" and canonical == "residents": audience_cue = audience_cue or "निवास" in sentence
            if root == "te" and canonical == "residents": audience_cue = audience_cue or "నివాస" in sentence
        if not action.scoped_audience and audience_cue:
            action.scoped_audience = list(contract.audience)
        if not action.scoped_areas and len(contract.affected_areas) == 1:
            # Area binding is accepted only when a canonical/numeric fragment occurs in
            # the same evidence sentence; otherwise it remains unresolved rather than guessed.
            area = contract.affected_areas[0].casefold()
            tokens = [t for t in area.replace("-", " ").split() if len(t) >= 3 or t.isdigit()]
            if tokens and any(t in sentence for t in tokens):
                action.scoped_areas = list(contract.affected_areas)
        if action.deadline and action.temporal_operator is None:
            root = (contract.language or "").split("-")[0].casefold()
            lower = text.casefold()
            if root == "en":
                import re
                m = re.search(r"\b(until|by|before|after)\b", lower)
                if m:
                    action.temporal_operator = TemporalOperator(m.group(1).upper())
            elif root == "hi" and "तक" in text:
                action.temporal_operator = TemporalOperator.UNTIL
            elif root == "te" and "వరకు" in text:
                action.temporal_operator = TemporalOperator.UNTIL



def contract_from_provider_output(
    output_text: str,
    source_text: str,
    *,
    language: str = "en",
    source_id: str | None = None,
) -> SafetyContract:
    """Deterministically rebuild the post-provider contract from retained output."""
    try:
        parsed = json.loads(output_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProviderError(f"Provider structured output was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("Provider structured output must be a JSON object")
    parsed["language"] = language
    if source_id:
        parsed["source_id"] = source_id
    try:
        contract = SafetyContract.model_validate(parsed)
    except Exception as exc:
        raise ProviderError(f"Provider structured output did not match SafetyContract: {exc}") from exc
    repair_provenance_offsets(source_text, contract)
    provenance_errors = validate_provenance(source_text, contract, require_p0=True)
    if provenance_errors:
        raise ProviderError("Invalid extraction provenance: " + "; ".join(provenance_errors))
    _bind_model_scopes(source_text, contract)
    guard_findings = _native_semantic_guard(source_text, contract)
    if (contract.language or "").split("-")[0].casefold() == "en":
        try:
            guard_findings.extend(_english_provider_coverage_guard(source_text, contract))
        except Exception as exc:
            # Completeness-check failure must never make provider extraction easier to
            # approve. Preserve machine-readable uncertainty for the verifier.
            guard_findings.append(f"provider coverage guard failure: {type(exc).__name__}")
    if guard_findings:
        contract.unresolved_operational_text = list(dict.fromkeys(contract.unresolved_operational_text + guard_findings))
    return contract


class ProviderError(RuntimeError):
    pass


def _strict_schema(schema: dict) -> dict:
    """Convert Pydantic JSON Schema to the conservative Structured Outputs subset.

    OpenAI strict schemas require object properties to be explicit and benefit from
    every property being listed as required; nullable fields remain nullable via anyOf.
    """
    remove_keys = {"default", "title", "minLength", "maxLength", "minimum", "exclusiveMinimum", "format"}
    def walk(node):
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items() if k not in remove_keys}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node
    return walk(schema)


@dataclass(slots=True)
class OpenAIResponsesProvider:
    api_key: str | None = None
    model: str | None = None
    timeout_seconds: float = 45.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        self.model = self.model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")

    async def _request(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(OPENAI_RESPONSES_URL, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

    @staticmethod
    def _output_text(response: dict) -> str:
        # Responses API returns message items containing output_text content.
        chunks: list[str] = []
        for item in response.get("output", []):
            for content in item.get("content", []) if isinstance(item, dict) else []:
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        if not chunks and response.get("output_text"):
            chunks.append(str(response["output_text"]))
        if not chunks:
            raise ProviderError("Provider response did not contain output text")
        return "\n".join(chunks)

    async def extract_contract_with_evidence(
        self,
        text: str,
        *,
        language: str = "en",
        source_id: str | None = None,
        require_provider_identity: bool = True,
        audit_metadata: dict[str, str] | None = None,
        store: bool | None = None,
    ) -> tuple[SafetyContract, dict]:
        schema = _strict_schema(SafetyContract.model_json_schema())
        provider_config = extraction_provider_config()
        if store is not None:
            provider_config["store"] = bool(store)
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": EXTRACTION_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"Language: {language}\nSource ID: {source_id or ''}\n\nALERT:\n{text}",
                },
            ],
            **provider_config,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "safety_contract",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if audit_metadata:
            payload["metadata"] = {str(k): str(v) for k, v in audit_metadata.items()}
        raw = await self._request(payload)
        output_text = self._output_text(raw)
        response_id = str(raw.get("id", "")).strip()
        response_model = str(raw.get("model", "")).strip()
        if require_provider_identity and not response_id:
            raise ProviderError("Provider response did not report a response id")
        if require_provider_identity and not response_model:
            raise ProviderError("Provider response did not report model identity")
        contract = contract_from_provider_output(
            output_text, text, language=language, source_id=source_id
        )
        receipt = {
            "response_id": response_id or None,
            "response_model": response_model or None,
            "response_created_at": raw.get("created_at"),
            "response_completed_at": raw.get("completed_at"),
            "response_status": raw.get("status"),
            "stored": raw.get("store") is True,
            "response_metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
            "usage": raw.get("usage") if isinstance(raw.get("usage"), dict) else None,
            "raw_output_text": output_text,
            "output_text_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
        }
        return contract, receipt

    async def extract_contract(self, text: str, *, language: str = "en", source_id: str | None = None) -> SafetyContract:
        contract, _ = await self.extract_contract_with_evidence(
            text, language=language, source_id=source_id, require_provider_identity=False
        )
        return contract

    async def transform(self, text: str, *, mode: str, language: str | None = None, max_chars: int | None = None) -> str:
        constraints = (
            "Preserve every protective action, prohibition/negation, location, number/unit, deadline/time, audience, exception, "
            "urgency, severity, and certainty. Do not add new operational facts."
        )
        if mode == "simplify":
            instruction = f"Rewrite in plain, easy-to-read language. {constraints}"
        elif mode == "sms":
            limit = max_chars or 360
            instruction = f"Compress to at most {limit} characters while preserving safety-critical meaning. {constraints}"
        elif mode == "translate":
            if not language:
                raise ValueError("language is required for translate mode")
            instruction = f"Translate/localize the alert into {language}. {constraints}"
        else:
            raise ValueError(f"Unsupported transform mode: {mode}")

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": instruction + " Output only the transformed alert."},
                {"role": "user", "content": text},
            ],
        }
        raw = await self._request(payload)
        output = self._output_text(raw).strip()
        if not output:
            raise ProviderError("Provider returned an empty transformation")
        if mode == "sms" and len(output) > (max_chars or 360):
            raise ProviderError(f"SMS transformation exceeded character limit: {len(output)} > {max_chars or 360}")
        return output

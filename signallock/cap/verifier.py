from __future__ import annotations

from datetime import timezone

from signallock.cap.mapper import cap_info_seed_contract
from signallock.cap.parser import CAPAlert, CAPInfo
from signallock.contracts.schema import Decision, VerificationResult, VerificationSignal
from signallock.verification.engine import VerificationEngine


def _dt_key(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).isoformat()


def _signal(field: str, expected, observed, *, criticality: str = "P0", detector: str = "cap_envelope") -> VerificationSignal:
    ok = expected == observed
    return VerificationSignal(
        field=field,
        status="PASS" if ok else "FAIL",
        criticality=criticality,
        expected=str(expected),
        observed=str(observed),
        reason=f"CAP {field} preserved." if ok else f"CAP {field} materially changed.",
        detector=detector,
    )


def _norm_text(value: str | None) -> str:
    return " ".join((value or "").split())


def _canonical_polygon(value: str) -> tuple[str, ...]:
    pts = tuple(" ".join(p.split()) for p in value.split() if p.strip())
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return ()
    rotations = []
    for seq in (pts, tuple(reversed(pts))):
        rotations.extend(seq[i:] + seq[:i] for i in range(len(seq)))
    return min(rotations)


def _info_structure_key(info: CAPInfo) -> tuple:
    return (
        info.language.casefold(),
        _norm_text(info.event).casefold(),
        tuple(sorted(x.casefold() for x in info.category)),
        tuple(sorted(x.casefold() for x in info.response_types)),
        tuple(sorted(_norm_text(x).casefold() for x in info.areas)),
        tuple(sorted(_canonical_polygon(x) for x in info.polygons)),
        tuple(sorted(_norm_text(x).casefold() for x in info.circles)),
        tuple(sorted((a.casefold(), b.casefold()) for a, b in info.geocodes)),
    )


def _pair_signals(source_alert: CAPAlert, candidate_alert: CAPAlert, s_info: CAPInfo, c_info: CAPInfo, label: str) -> list[VerificationSignal]:
    signals: list[VerificationSignal] = []
    for field, expected, observed in [
        ("language", s_info.language.casefold(), c_info.language.casefold()),
        ("category", tuple(sorted(x.casefold() for x in s_info.category)), tuple(sorted(x.casefold() for x in c_info.category))),
        ("event", _norm_text(s_info.event).casefold(), _norm_text(c_info.event).casefold()),
        ("response_types", tuple(sorted(x.casefold() for x in s_info.response_types)), tuple(sorted(x.casefold() for x in c_info.response_types))),
        ("onset", _dt_key(s_info.onset) if s_info.onset else "", _dt_key(c_info.onset) if c_info.onset else ""),
        ("headline", _norm_text(s_info.headline), _norm_text(c_info.headline)),
        ("description", _norm_text(s_info.description), _norm_text(c_info.description)),
        ("polygons", tuple(sorted(_canonical_polygon(x) for x in s_info.polygons)), tuple(sorted(_canonical_polygon(x) for x in c_info.polygons))),
        ("circles", tuple(sorted(_norm_text(x) for x in s_info.circles)), tuple(sorted(_norm_text(x) for x in c_info.circles))),
        ("geocodes", tuple(sorted(s_info.geocodes)), tuple(sorted(c_info.geocodes))),
    ]:
        signals.append(_signal(f"{label}.{field}", expected, observed, detector="cap_info_structure"))

    s_contract = cap_info_seed_contract(source_alert, s_info)
    c_contract = cap_info_seed_contract(candidate_alert, c_info)
    nested = VerificationEngine().verify(s_contract, c_contract)
    for sig in nested.signals:
        signals.append(sig.model_copy(update={"field": f"{label}.{sig.field}"}))
    return signals


def _pair_score(signals: list[VerificationSignal]) -> tuple[int, int]:
    fails = sum(s.status == "FAIL" and s.criticality in {"P0", "P1"} for s in signals)
    unknowns = sum(s.status in {"WARN", "UNKNOWN"} for s in signals)
    return fails, unknowns


def verify_cap_alerts(source: CAPAlert, candidate: CAPAlert, *, source_info_index: int = 0, candidate_info_index: int = 0) -> VerificationResult:
    signals: list[VerificationSignal] = []

    for field, expected, observed in [
        ("identifier", source.identifier, candidate.identifier),
        ("sender", source.sender, candidate.sender),
        ("status", source.status, candidate.status),
        ("msg_type", source.msg_type, candidate.msg_type),
        ("scope", source.scope, candidate.scope),
        ("sent", _dt_key(source.sent), _dt_key(candidate.sent)),
        ("references", source.references or "", candidate.references or ""),
        ("restriction", source.restriction or "", candidate.restriction or ""),
        ("addresses", tuple(sorted(source.addresses)), tuple(sorted(candidate.addresses))),
    ]:
        signals.append(_signal(f"cap.{field}", expected, observed))

    if len(source.infos) != len(candidate.infos):
        signals.append(VerificationSignal(
            field="cap.info_count", status="FAIL", criticality="P0",
            expected=str(len(source.infos)), observed=str(len(candidate.infos)),
            reason="Candidate CAP added or removed an info block.", detector="cap_whole_message",
        ))

    # Match info blocks semantically instead of by position. Structure keys narrow the
    # candidates first; if necessary we choose the lowest-risk unmatched pairing.
    unused = set(range(len(candidate.infos)))
    for s_idx, s_info in enumerate(source.infos):
        candidates = [j for j in unused if _info_structure_key(candidate.infos[j]) == _info_structure_key(s_info)]
        if not candidates:
            candidates = list(unused)
        if not candidates:
            break
        scored = []
        for j in candidates:
            pair = _pair_signals(source, candidate, s_info, candidate.infos[j], f"cap.info[{s_idx}->{j}]")
            scored.append((_pair_score(pair), j, pair))
        _, chosen, pair = min(scored, key=lambda row: row[0])
        unused.remove(chosen)
        signals.extend(pair)

    if unused:
        for j in sorted(unused):
            signals.append(VerificationSignal(
                field=f"cap.candidate_only_info[{j}]", status="FAIL", criticality="P0",
                expected="<no additional info block>", observed=repr(_info_structure_key(candidate.infos[j])),
                reason="Candidate CAP introduced an unmatched info block.", detector="cap_whole_message",
            ))

    try:
        source_contract = cap_info_seed_contract(source, source.infos[source_info_index])
        candidate_contract = cap_info_seed_contract(candidate, candidate.infos[candidate_info_index])
    except IndexError as exc:
        raise ValueError("CAP info index out of range") from exc

    failures = [s.field for s in signals if s.status == "FAIL" and s.criticality in {"P0", "P1"}]
    uncertain = [s.field for s in signals if s.status in {"WARN", "UNKNOWN"}]
    if failures:
        decision = Decision.BLOCK
        summary = "CAP envelope, geography, info-block, or protective-action mismatch detected."
    elif uncertain:
        decision = Decision.REVIEW
        summary = "CAP structure is intact, but one or more semantic relations remain unresolved."
    else:
        decision = Decision.PASS
        summary = "Whole CAP message and scoped protective directives are preserved."

    return VerificationResult(
        decision=decision,
        signals=signals,
        critical_failures=list(dict.fromkeys(failures)),
        warnings=list(dict.fromkeys(uncertain)),
        summary=summary,
        source_contract=source_contract,
        candidate_contract=candidate_contract,
    )

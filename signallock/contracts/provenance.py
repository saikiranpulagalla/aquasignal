from __future__ import annotations

from signallock.contracts.schema import SafetyContract


class ProvenanceError(ValueError):
    pass


def validate_provenance(text: str, contract: SafetyContract, *, require_p0: bool = False) -> list[str]:
    errors: list[str] = []
    evidence_items: list[tuple[str, object | None]] = []
    if contract.hazard:
        evidence_items.append(("hazard", contract.hazard.evidence))
    for idx, row in enumerate(contract.required_actions):
        evidence_items.append((f"required_actions[{idx}]", row.evidence))
    for idx, row in enumerate(contract.prohibited_actions):
        evidence_items.append((f"prohibited_actions[{idx}]", row.evidence))
    for idx, row in enumerate(contract.quantities):
        evidence_items.append((f"quantities[{idx}]", row.evidence))
    for idx, row in enumerate(contract.exceptions):
        evidence_items.append((f"exceptions[{idx}]", row.evidence))

    p0_prefixes = ("required_actions[", "prohibited_actions[", "quantities[")
    for name, ev in evidence_items:
        if ev is None:
            if require_p0 and name.startswith(p0_prefixes):
                errors.append(f"{name}: missing required P0 evidence")
            continue
        if ev.end_char > len(text):
            errors.append(f"{name}: evidence end_char exceeds source length")
            continue
        if text[ev.start_char:ev.end_char] != ev.quote:
            errors.append(f"{name}: evidence span does not match source text")
    return errors


def assert_valid_provenance(text: str, contract: SafetyContract, *, require_p0: bool = False) -> None:
    errors = validate_provenance(text, contract, require_p0=require_p0)
    if errors:
        raise ProvenanceError("; ".join(errors))

def repair_provenance_offsets(text: str, contract: SafetyContract) -> SafetyContract:
    """Repair offsets only when the model supplied an exact, uniquely occurring quote.

    This improves robustness without weakening provenance: we never fuzzy-search or
    rewrite the quote, and ambiguous duplicate occurrences remain invalid.
    """
    evidence_items = []
    if contract.hazard and contract.hazard.evidence:
        evidence_items.append(contract.hazard.evidence)
    for row in contract.required_actions + contract.prohibited_actions + contract.quantities + contract.exceptions:
        if row.evidence:
            evidence_items.append(row.evidence)
    for ev in evidence_items:
        if ev.end_char <= len(text) and text[ev.start_char:ev.end_char] == ev.quote:
            continue
        starts = []
        pos = text.find(ev.quote)
        while pos != -1:
            starts.append(pos)
            pos = text.find(ev.quote, pos + 1)
        if len(starts) == 1:
            ev.start_char = starts[0]
            ev.end_char = starts[0] + len(ev.quote)
    return contract

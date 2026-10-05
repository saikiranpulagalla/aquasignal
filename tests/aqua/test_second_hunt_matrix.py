from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
from aquasignal.integrity.verifier import AquaVerificationEngine


ext = FreshwaterExtractor()
verifier = AquaVerificationEngine()


def _decision(source: str, candidate: str) -> str:
    source_contract = ext.extract(source, source_id="matrix:source")
    candidate_contract = ext.extract(candidate, source_id="matrix:candidate")
    if not assess_source_readiness(source_contract).ready:
        return "SOURCE_REVIEW"
    return verifier.verify(source_contract, candidate_contract).decision.value


def test_generated_unsafe_mutation_matrix_has_zero_passes():
    cases: list[tuple[str, str]] = []

    for verb in ("swim", "wade", "fish", "enter"):
        source = f"Do not {verb} in Stream A until 18:00."
        for modal in ("may", "can", "must", "should"):
            cases.append((source, f"Visitors {modal} {verb} in Stream A until 18:00."))

    source = "Do not drink water from Stream A until 18:00."
    for modal in ("may", "can", "must", "should"):
        cases.append((source, f"Visitors {modal} drink water from Stream A until 18:00."))

    source = "Visitors must avoid contact with Stream A until 18:00."
    cases.extend(
        (
            source,
            candidate,
        )
        for candidate in (
            "Visitors may touch the water in Stream A until 18:00.",
            "Visitors can contact the water in Stream A until 18:00.",
            "Visitors should touch the water in Stream A until 18:00.",
            "Visitors must not avoid contact with Stream A until 18:00.",
            "Visitors must avoid contact with Stream A before 18:00.",
            "Visitors must avoid contact with Stream A after 18:00.",
            "Visitors must avoid contact with Stream A until 19:00.",
            "Visitors must avoid contact with Stream A tonight.",
            "Visitors must avoid contact with Stream A.",
        )
    )

    source = "Do not swim in Stream A until 18:00."
    for suffix in ("Wear gloves.", "Call 911.", "Stay home.", "Boil water.", "Then call staff."):
        cases.append((source, source + " " + suffix))
    for candidate in (
        "Do not swim in Stream A and wear gloves until 18:00.",
        "Do not swim in Stream A then wear gloves until 18:00.",
        "Do not swim in Stream A plus call 911 until 18:00.",
        "Do not swim in Stream A because contamination was reported until 18:00.",
    ):
        cases.append((source, candidate))

    results = [(source, candidate, _decision(source, candidate)) for source, candidate in cases]
    unsafe_passes = [row for row in results if row[2] == "PASS"]
    assert not unsafe_passes, unsafe_passes


def test_generated_clean_equivalence_matrix_passes():
    cases = [
        ("Do not swim in Stream A until 18:00.", "Don’t swim in stream a until 6 PM."),
        ("Avoid direct contact with River North until 18:00.", "Do not touch water in river north until 6pm."),
        ("Avoid direct contact downstream of Bridge North until 18:00.", "Avoid contact downstream of Bridge North until 6 PM."),
        ("Boil the water for at least 1 hour before drinking.", "Boil the water for at least 60 minutes before drinking."),
        ("Boil the water for at least 3 minutes before drinking.", "Boil the water for at least 180 seconds before drinking."),
        ("Keep children and pets away from Stream A until 18:00.", "Keep pets and children away from stream a until 6 PM."),
    ]
    results = [(source, candidate, _decision(source, candidate)) for source, candidate in cases]
    non_pass = [row for row in results if row[2] != "PASS"]
    assert not non_pass, non_pass

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AquaCase:
    case_id: str
    family: str
    source: str
    candidate: str
    safe_equivalent: bool
    expected_decision: str | None = None


DEV_CASES = [
    AquaCase("U01", "time_reversal", "Visitors must avoid contact with Stream A after 18:00.", "Visitors must avoid contact with Stream A before 18:00.", False, "BLOCK"),
    AquaCase("U02", "time_reversal", "Visitors must avoid contact with Stream A before 18:00.", "Visitors must avoid contact with Stream A after 18:00.", False, "BLOCK"),
    AquaCase("U03", "location_reversal", "Avoid direct contact with stream water downstream of Bridge A until 18:00.", "Avoid direct contact with stream water upstream of Bridge A until 18:00.", False, "BLOCK"),
    AquaCase("U04", "location_reversal", "Avoid direct contact with stream water upstream of Bridge A until 18:00.", "Avoid direct contact with stream water downstream of Bridge A until 18:00.", False, "BLOCK"),
    AquaCase("U05", "location_weakening", "Avoid direct contact with stream water downstream of Bridge A until 18:00.", "Avoid direct contact with stream water near Bridge A until 18:00.", False, "BLOCK"),
    AquaCase("U06", "audience_omission", "Keep children and pets away from Stream A until 18:00.", "Keep children away from Stream A until 18:00.", False, "BLOCK"),
    AquaCase("U07", "audience_omission", "Keep children and pets away from Stream A until 18:00.", "Keep pets away from Stream A until 18:00.", False, "BLOCK"),
    AquaCase("U08", "action_omission", "Do not swim or fish in Stream A until 18:00.", "Do not swim in Stream A until 18:00.", False, "BLOCK"),
    AquaCase("U09", "action_omission", "Do not swim or fish in Stream A until 18:00.", "Do not fish in Stream A until 18:00.", False, "BLOCK"),
    AquaCase("U10", "prohibition_loss", "Do not swim in Stream A until 18:00.", "Swim in Stream A until 18:00.", False, "BLOCK"),
    AquaCase("U11", "time_omission", "Avoid direct contact with Stream A until 18:00.", "Avoid direct contact with Stream A.", False, "BLOCK"),
    AquaCase("U12", "unauthorized_addition", "Avoid direct contact with Stream A until 18:00.", "Avoid direct contact with Stream A until 18:00. Boil the water for at least 1 minute before drinking.", False, "BLOCK"),
    AquaCase("U13", "exclusivity_loss", "Only trained personnel may collect samples from Site A.", "Trained personnel may collect samples from Site A.", False, "BLOCK"),
    AquaCase("U14", "relative_time", "Avoid direct contact with Stream A until 18:00.", "Avoid direct contact with Stream A this afternoon.", False, "BLOCK"),
    AquaCase("C01", "clock_equivalence", "Visitors must avoid contact with Stream A until 6 PM.", "Visitors must avoid contact with Stream A until 18:00.", True, "PASS"),
    AquaCase("C02", "contact_paraphrase", "Avoid direct contact with Stream A until 18:00.", "Do not touch water in Stream A until 18:00.", True, "PASS"),
    AquaCase("C03", "identity", "Keep children and pets away from Stream A until 18:00.", "Keep children and pets away from Stream A until 18:00.", True, "PASS"),
    AquaCase("C04", "identity", "Do not swim or fish in Stream A until 18:00.", "Do not swim or fish in Stream A until 18:00.", True, "PASS"),
    AquaCase("C05", "identity", "Avoid direct contact with stream water downstream of Bridge A until 18:00.", "Avoid direct contact with stream water downstream of Bridge A until 18:00.", True, "PASS"),
    AquaCase("C06", "identity", "Do not wade in Stream A until 18:00.", "Do not wade in Stream A until 18:00.", True, "PASS"),
    AquaCase("C07", "identity", "Do not drink water from Stream A until 18:00.", "Do not drink water from Stream A until 18:00.", True, "PASS"),
    AquaCase("C08", "boil_duration", "Boil the water for at least 1 minute before drinking.", "Boil the water for at least 1 minute before drinking.", True, "PASS"),
    AquaCase("C09", "sample_restriction", "Only trained personnel may collect samples from Site A.", "Only trained personnel may collect samples from Site A.", True, "PASS"),
    AquaCase("C10", "clock_equivalence", "Avoid direct contact with Stream A until 7 PM.", "Do not touch water in Stream A until 19:00.", True, "PASS"),
]

import json
from pathlib import Path

import pytest

from signallock.contracts.schema import Action, ActionType, EvidenceSpan, SafetyContract
from signallock.evaluation.holdout import HoldoutError, validate_v7_quality
from signallock.evaluation.review_workflow import (
    BLIND_FORBIDDEN_FIELDS,
    finalize_reviewed_holdout,
    make_blind_review_templates,
    prepare_authoring_packet,
    validate_authoring_packet,
)

ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _contract_for(text: str):
    quote = text.split()[0]
    start = text.index(quote)
    return SafetyContract(
        language="en",
        required_actions=[Action(type=ActionType.OTHER, verb="reviewed", evidence=EvidenceSpan(
            quote=quote, start_char=start, end_char=start + len(quote)
        ))],
    ).model_dump(mode="json")


def _complete_packet(rows):
    out=[]
    for i,row in enumerate(rows):
        r=dict(row)
        r["source_contract"]=_contract_for(r["source_text"])
        if r["candidate_language"]=="hi":
            r["candidate_text"]=f"निवासी सुरक्षित रहें और निर्देश मानें केस {i}।"
            r["author_id"]="candidate-author-a" if i % 2 == 0 else "candidate-author-c"
        else:
            r["candidate_text"]=f"నివాసితులు సురక్షితంగా ఉండండి మరియు సూచనలు పాటించండి కేసు {i}."
            r["author_id"]="candidate-author-b" if i % 2 == 0 else "candidate-author-d"
        r["authority_reviewer_id"]="authority-reviewer"
        r["authority_reviewed_at"]="2026-09-12T14:00:00+05:30"
        out.append(r)
    return out


def _make_reviews(rows):
    primary, secondary, mapping = make_blind_review_templates(rows)
    targets={r["task_id"]:r["target_decision"] for r in rows}
    for item in primary:
        task_id=mapping["primary"][item["review_id"]]["task_id"]
        item["reviewer_id"]="reviewer-a"
        item["reviewed_at"]="2026-09-12T15:00:00+05:30"
        item["verdict"]=targets[task_id]
        item["notes"]="blind primary review"
    for item in secondary:
        task_id=mapping["secondary"][item["review_id"]]["task_id"]
        item["reviewer_id"]="reviewer-b"
        item["reviewed_at"]="2026-09-12T15:30:00+05:30"
        item["verdict"]=targets[task_id]
        item["notes"]="independent blind confirmation"
    return primary, secondary, mapping


def _final_like(rows):
    final=[]
    for i,row in enumerate(rows):
        item={
            "case_id":row["task_id"],"source_text":row["source_text"],"source_language":"en",
            "source_contract":row["source_contract"],"candidate_text":row["candidate_text"],
            "candidate_language":row["candidate_language"],"expected_decision":row["target_decision"],
            "human_reviewed":True,"reviewer_id":"reviewer-a","reviewed_at":"2026-09-12T15:00:00+05:30",
            "source_reference":row["source_reference"],"fault_class":row["fault_class"],
            "second_reviewer_id":"reviewer-b" if row["target_decision"]=="BLOCK" else None,
            "second_reviewed_at":"2026-09-12T15:30:00+05:30" if row["target_decision"]=="BLOCK" else None,
            "author_id":row["author_id"],"authority_reviewer_id":"authority-reviewer",
            "authority_reviewed_at":"2026-09-12T14:00:00+05:30",
        }
        final.append(item)
    return final


def _packet():
    return prepare_authoring_packet(
        ROOT/"data/multilingual/v7_source_seeds.jsonl",
        ROOT/"data/multilingual/v7_challenge_source_seeds_v05.jsonl",
    )


def test_v7_qualification_packet_has_exact_balanced_plan():
    rows=_packet()
    report=validate_authoring_packet(rows, require_completed=False)
    assert report["total"]==24
    assert report["by_language"]=={"hi":12,"te":12}
    assert report["fault_class_counts"]["clean"]==12
    assert all(report["fault_class_counts"][f]==2 for f in (
        "action_area","action_audience","quantity_exception_binding","modality","temporal","logic_sequence"
    ))
    assert all(not r["candidate_text"] for r in rows)
    assert all(not r["author_id"] for r in rows)


def test_blind_review_templates_remove_label_side_channels_and_use_opaque_ids():
    rows=_complete_packet(_packet())
    primary,secondary,mapping=make_blind_review_templates(rows)
    assert len(primary)==24 and len(secondary)==24
    assert mapping["version"]=="3.0"
    assert set(mapping["primary"]) == {r["review_id"] for r in primary}
    assert set(mapping["secondary"]) == {r["review_id"] for r in secondary}
    assert set(mapping["primary"]).isdisjoint(mapping["secondary"])
    for row in primary+secondary:
        assert BLIND_FORBIDDEN_FIELDS.isdisjoint(row)
        assert row["review_id"].startswith(("P-","S-"))
        assert "source_reference" not in row and "task_id" not in row
    original=[r["task_id"] for r in rows]
    p_order=[mapping["primary"][r["review_id"]]["task_id"] for r in primary]
    s_order=[mapping["secondary"][r["review_id"]]["task_id"] for r in secondary]
    assert p_order != original
    assert s_order != original
    assert p_order != s_order


def test_finalize_requires_blind_consensus_and_produces_strict_quality(tmp_path):
    rows=_complete_packet(_packet())
    authored=tmp_path/"authored.jsonl"; _write(authored,rows)
    primary,secondary,mapping=_make_reviews(rows)
    pp=tmp_path/"p.jsonl"; sp=tmp_path/"s.jsonl"; mp=tmp_path/"map.json"
    _write(pp,primary); _write(sp,secondary); _write_json(mp,mapping)
    final=finalize_reviewed_holdout(authored,pp,sp,mp)
    quality=validate_v7_quality(final)
    assert quality["total"]==24
    assert quality["reviewer_count"]>=2
    assert quality["fault_class_counts"]["clean"]==12


def test_finalize_refuses_primary_disagreement(tmp_path):
    rows=_complete_packet(_packet())
    authored=tmp_path/"authored.jsonl"; _write(authored,rows)
    primary,secondary,mapping=_make_reviews(rows)
    primary[0]["verdict"]="BLOCK" if primary[0]["verdict"]=="PASS" else "PASS"
    pp=tmp_path/"p.jsonl"; sp=tmp_path/"s.jsonl"; mp=tmp_path/"map.json"
    _write(pp,primary); _write(sp,secondary); _write_json(mp,mapping)
    with pytest.raises(HoldoutError, match="primary reviewer disagrees"):
        finalize_reviewed_holdout(authored,pp,sp,mp)


def test_finalize_refuses_review_content_tampering(tmp_path):
    rows=_complete_packet(_packet())
    authored=tmp_path/"authored.jsonl"; _write(authored,rows)
    primary,secondary,mapping=_make_reviews(rows)
    primary[0]["candidate_text"] += " बदला हुआ"
    pp=tmp_path/"p.jsonl"; sp=tmp_path/"s.jsonl"; mp=tmp_path/"map.json"
    _write(pp,primary); _write(sp,secondary); _write_json(mp,mapping)
    with pytest.raises(HoldoutError, match="content changed after blinding"):
        finalize_reviewed_holdout(authored,pp,sp,mp)


def test_finalize_refuses_hidden_label_in_review_sheet(tmp_path):
    rows=_complete_packet(_packet())
    authored=tmp_path/"authored.jsonl"; _write(authored,rows)
    primary,secondary,mapping=_make_reviews(rows)
    primary[0]["fault_class"]="clean"
    pp=tmp_path/"p.jsonl"; sp=tmp_path/"s.jsonl"; mp=tmp_path/"map.json"
    _write(pp,primary); _write(sp,secondary); _write_json(mp,mapping)
    with pytest.raises(HoldoutError, match="contains hidden fields"):
        finalize_reviewed_holdout(authored,pp,sp,mp)


def test_finalize_refuses_mapping_from_different_authored_packet(tmp_path):
    rows=_complete_packet(_packet())
    authored=tmp_path/"authored.jsonl"; _write(authored,rows)
    primary,secondary,mapping=_make_reviews(rows)
    rows[0]["candidate_text"] += " अतिरिक्त"
    _write(authored,rows)
    pp=tmp_path/"p.jsonl"; sp=tmp_path/"s.jsonl"; mp=tmp_path/"map.json"
    _write(pp,primary); _write(sp,secondary); _write_json(mp,mapping)
    with pytest.raises(HoldoutError, match="does not match the exact authored packet"):
        finalize_reviewed_holdout(authored,pp,sp,mp)


def test_strict_v7_rejects_empty_authority_contract_even_with_review_metadata():
    rows=_complete_packet(_packet())
    final=_final_like(rows)
    final[0]["source_contract"]=SafetyContract(language="en").model_dump(mode="json")
    with pytest.raises(HoldoutError, match="no operational directive"):
        validate_v7_quality(final)


def test_strict_v7_requires_language_cue_not_only_script():
    rows=_complete_packet(_packet())
    rows[0]["candidate_text"]="संस्कृतभाषा श्लोकः पठतु।"
    final=_final_like(rows)
    with pytest.raises(HoldoutError, match="language cue"):
        validate_v7_quality(final)


def test_strict_v7_rejects_case_and_whitespace_identity_aliases():
    rows=_complete_packet(_packet())
    final=_final_like(rows)
    final[0]["author_id"]=" Reviewer A "
    final[0]["reviewer_id"]="reviewer   a"
    with pytest.raises(HoldoutError, match="primary reviewer must be independent"):
        validate_v7_quality(final)


def test_strict_v7_rejects_reviews_before_authority_review():
    rows=_complete_packet(_packet())
    final=_final_like(rows)
    final[0]["reviewed_at"]="2026-09-12T13:59:00+05:30"
    with pytest.raises(HoldoutError, match="predates authority-contract review"):
        validate_v7_quality(final)


@pytest.fixture
def quality_rows():
    """In-memory validator fixture only; never persisted as human evidence."""
    rows = _final_like(_complete_packet(_packet()))
    assert validate_v7_quality(rows)["total"] == 24
    return rows


def test_quality_accepts_complete_fixture(quality_rows):
    quality = validate_v7_quality(quality_rows)
    assert quality["author_count"] >= 2
    assert quality["reviewer_count"] >= 2
    assert all(quality["authors_by_fault"][name] >= 2 for name in (
        "action_area", "action_audience", "quantity_exception_binding", "modality", "temporal", "logic_sequence"
    ))


def test_quality_rejects_single_author(quality_rows):
    for row in quality_rows:
        row["author_id"] = "unit-test-only-author"
    with pytest.raises(HoldoutError, match="at least 2 independent candidate authors"):
        validate_v7_quality(quality_rows)


def test_quality_rejects_single_author_for_one_fault(quality_rows):
    for row in quality_rows:
        if row["fault_class"] == "modality":
            row["author_id"] = "unit-test-only-author"
    with pytest.raises(HoldoutError, match="requires at least 2 distinct candidate authors"):
        validate_v7_quality(quality_rows)


@pytest.mark.parametrize("alias", ["reviewer-a", " REVIEWER-A ", "reviewer-\u200ba", "ｒｅｖｉｅｗｅｒ-ａ"])
def test_quality_rejects_author_primary_identity_collision(quality_rows, alias):
    quality_rows[0]["author_id"] = alias
    with pytest.raises(HoldoutError, match="primary reviewer must be independent"):
        validate_v7_quality(quality_rows)


@pytest.mark.parametrize("role", ["author_id", "reviewer_id", "authority_reviewer_id", None])
def test_quality_requires_independent_second_reviewer(quality_rows, role):
    row = next(row for row in quality_rows if row["expected_decision"] == "BLOCK")
    row["second_reviewer_id"] = row[role] if role else ""
    with pytest.raises(HoldoutError, match="second reviewer distinct"):
        validate_v7_quality(quality_rows)


def test_quality_rejects_collapsed_review_roles(quality_rows):
    for row in quality_rows:
        row["reviewer_id"] = row["authority_reviewer_id"]
    with pytest.raises(HoldoutError, match="independent of authority reviewer"):
        validate_v7_quality(quality_rows)


def test_quality_rejects_missing_fault_family(quality_rows):
    for row in quality_rows:
        if row["fault_class"] == "modality":
            row["fault_class"] = "temporal"
    with pytest.raises(HoldoutError, match="missing required fault classes"):
        validate_v7_quality(quality_rows)


def test_quality_rejects_duplicate_padding(quality_rows):
    quality_rows.append(dict(quality_rows[0]))
    with pytest.raises(HoldoutError, match="duplicate source/candidate"):
        validate_v7_quality(quality_rows)

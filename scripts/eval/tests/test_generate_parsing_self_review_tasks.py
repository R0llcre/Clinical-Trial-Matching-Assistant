from __future__ import annotations

from generate_parsing_self_review_tasks import build_self_review_tasks


def _adjudicated_row(
    nct_id: str,
    *,
    ambiguous: bool = False,
) -> dict[str, object]:
    return {
        "nct_id": nct_id,
        "eligibility_text": f"text for {nct_id}",
        "labeled_rules": [],
        "ambiguous": ambiguous,
    }


def _dis_row(nct_id: str, *, jaccard: float, a_only: int, b_only: int) -> dict[str, object]:
    return {
        "nct_id": nct_id,
        "jaccard": jaccard,
        "a_only_rule_count": a_only,
        "b_only_rule_count": b_only,
    }


def test_build_self_review_tasks_prioritizes_ambiguous_then_backfill() -> None:
    adjudicated = [
        _adjudicated_row("N1", ambiguous=True),
        _adjudicated_row("N2", ambiguous=False),
        _adjudicated_row("N3", ambiguous=False),
    ]
    disagreements = [
        _dis_row("N2", jaccard=0.1, a_only=8, b_only=8),
        _dis_row("N1", jaccard=0.2, a_only=3, b_only=2),
        _dis_row("N3", jaccard=0.4, a_only=2, b_only=2),
    ]

    tasks, manifest = build_self_review_tasks(
        adjudicated_rows=adjudicated,
        disagreement_rows=disagreements,
        target_trials=2,
        task_id_prefix="parsing-relabel-r2-self",
        guideline_version="m5-v1",
        target_annotator="annotator_c",
    )

    assert len(tasks) == 2
    assert tasks[0]["nct_id"] == "N1"
    assert tasks[0]["priority_reason"] == "ambiguous_from_round1"
    assert tasks[1]["nct_id"] == "N2"
    assert tasks[1]["priority_reason"] == "high_disagreement_backfill"
    assert manifest["selected_ambiguous_trials"] == 1
    assert manifest["selected_backfill_trials"] == 1


def test_build_self_review_tasks_falls_back_when_disagreement_missing() -> None:
    adjudicated = [
        _adjudicated_row("N1", ambiguous=False),
        _adjudicated_row("N2", ambiguous=False),
    ]
    disagreements = [
        _dis_row("N1", jaccard=0.1, a_only=3, b_only=3),
    ]

    tasks, manifest = build_self_review_tasks(
        adjudicated_rows=adjudicated,
        disagreement_rows=disagreements,
        target_trials=2,
        task_id_prefix="parsing-relabel-r2-self",
        guideline_version="m5-v1",
        target_annotator="annotator_c",
    )

    assert len(tasks) == 2
    assert {tasks[0]["nct_id"], tasks[1]["nct_id"]} == {"N1", "N2"}
    assert manifest["shortfall"] == 0

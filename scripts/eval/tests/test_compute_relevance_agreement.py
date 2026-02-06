from __future__ import annotations

import json
from pathlib import Path

import pytest

from compute_relevance_agreement import cohen_kappa, load_labels


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def test_load_labels_ok(tmp_path: Path) -> None:
    file_path = tmp_path / "a.jsonl"
    _write(
        file_path,
        [
            {"query_id": "Q1", "nct_id": "NCT1", "relevance_label": 2},
            {"query_id": "Q2", "nct_id": "NCT2", "relevance_label": 1},
        ],
    )

    labels = load_labels(file_path)
    assert labels[("Q1", "NCT1")] == 2
    assert labels[("Q2", "NCT2")] == 1


def test_load_labels_rejects_invalid_label(tmp_path: Path) -> None:
    file_path = tmp_path / "bad.jsonl"
    _write(file_path, [{"query_id": "Q1", "nct_id": "NCT1", "relevance_label": 3}])

    with pytest.raises(ValueError, match="relevance_label"):
        load_labels(file_path)


def test_cohen_kappa_perfect_agreement() -> None:
    assert cohen_kappa([0, 1, 2, 2], [0, 1, 2, 2]) == pytest.approx(1.0)


def test_cohen_kappa_partial_agreement() -> None:
    score = cohen_kappa([0, 1, 2, 0], [0, 2, 2, 1])
    assert score < 1.0
    assert score > -1.0

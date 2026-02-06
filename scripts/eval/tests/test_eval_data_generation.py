from __future__ import annotations

from pathlib import Path

from generate_eval_data import generate
from validate_eval_data import validate_data_dir


def test_generate_eval_data_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "eval_data"
    generate(output_dir)

    assert (output_dir / "queries.jsonl").exists()
    assert (output_dir / "trials_sample.jsonl").exists()
    assert (output_dir / "patients.jsonl").exists()

    counts, errors = validate_data_dir(output_dir)
    assert counts["queries"] > 0
    assert counts["trials_sample"] > 0
    assert counts["patients"] > 0
    assert errors == []


def test_repository_eval_data_is_valid() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    counts, errors = validate_data_dir(repo_root / "eval" / "data")
    assert counts["queries"] > 0
    assert counts["trials_sample"] > 0
    assert counts["patients"] > 0
    assert errors == []


def test_validate_data_dir_reports_missing_files(tmp_path: Path) -> None:
    counts, errors = validate_data_dir(tmp_path)
    assert counts["queries"] == 0
    assert counts["trials_sample"] == 0
    assert counts["patients"] == 0
    assert len(errors) == 3

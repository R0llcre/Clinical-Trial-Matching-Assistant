from __future__ import annotations

from run_llm_ablation import default_configs, render_markdown


def test_default_configs_contains_required_dimensions() -> None:
    configs = default_configs()
    names = {cfg.name for cfg in configs}
    assert "strict_guarded" in names
    assert "no_contract_postprocess" in names
    assert "no_hallucination_gate" in names
    assert "no_critical_backfill" in names
    assert "precision_prompt" in names
    assert "recall_prompt" in names


def test_render_markdown_outputs_summary_table() -> None:
    report = {
        "generated_at_utc": "2026-02-07T00:00:00Z",
        "model": "gpt-4.1",
        "trial_count": 10,
        "results": [
            {
                "name": "strict_guarded",
                "description": "baseline",
                "env": {"OPENAI_PROMPT_STYLE": "strict_v1"},
                "elapsed_sec": 1.2,
                "metrics": {
                    "parsing": {"f1": 0.3, "precision": 0.25, "recall": 0.4},
                    "hallucination": {"hallucination_rate": 0.0},
                },
                "runtime": {
                    "fallback_rate": 0.5,
                    "token_usage": {"total_tokens": 1234},
                    "source_counts": {"llm_v1": 5, "rule_v1": 5, "other": 0},
                },
            }
        ],
    }
    markdown = render_markdown(report)
    assert "# LLM Ablation Report" in markdown
    assert "| Config | F1 | Precision | Recall | Hallucination | Fallback Rate | Tokens |" in markdown
    assert "strict_guarded" in markdown

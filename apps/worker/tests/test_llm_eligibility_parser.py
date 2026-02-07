import json

import pytest

from services import llm_eligibility_parser as parser


def test_parse_criteria_llm_v1_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_PARSER_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(parser.LLMParserError, match="llm parser disabled"):
        parser.parse_criteria_llm_v1("Adults only")


def test_parse_criteria_llm_v1_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PARSER_ENABLED", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(parser.LLMParserError, match="OPENAI_API_KEY not set"):
        parser.parse_criteria_llm_v1("Adults only")


def test_parse_criteria_llm_v1_accepts_valid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PARSER_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rules": [
                                {
                                    "id": "rule-1",
                                    "type": "INCLUSION",
                                    "field": "age",
                                    "operator": ">=",
                                    "value": 18,
                                    "unit": "years",
                                    "time_window": None,
                                    "certainty": "high",
                                    "evidence_text": "Adults 18 years or older",
                                    "source_span": {"start": 0, "end": 24},
                                }
                            ]
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }
    monkeypatch.setattr(parser, "_post_chat_completion", lambda **kwargs: payload)

    rules, usage = parser.parse_criteria_llm_v1("Adults only")

    assert len(rules) == 1
    assert rules[0]["field"] == "age"
    assert rules[0]["operator"] == ">="
    assert usage["total_tokens"] == 14


def test_parse_criteria_llm_v1_normalizes_operator_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PARSER_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rules": [
                                {
                                    "id": "rule-1",
                                    "type": "INCLUSION",
                                    "field": "age",
                                    "operator": ">",
                                    "value": 18,
                                    "unit": "years",
                                    "time_window": None,
                                    "certainty": "high",
                                    "evidence_text": "Adults 18 years or older",
                                    "source_span": {"start": 0, "end": 24},
                                }
                            ]
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }
    monkeypatch.setattr(parser, "_post_chat_completion", lambda **kwargs: payload)

    rules, _ = parser.parse_criteria_llm_v1("Adults only")
    assert rules[0]["operator"] == ">="


def test_build_response_format_uses_json_schema() -> None:
    response_format = parser._build_response_format()
    assert response_format["type"] == "json_schema"
    schema = response_format["json_schema"]["schema"]
    assert schema["type"] == "object"
    assert "rules" in schema["properties"]


def test_parse_criteria_llm_v1_rejects_invalid_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PARSER_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rules": [
                                {
                                    "id": "rule-1",
                                    "type": "INCLUSION",
                                    "field": "sex",
                                    "operator": "=",
                                    "value": "unknown",
                                    "unit": None,
                                    "time_window": None,
                                    "certainty": "high",
                                    "evidence_text": "Sex unknown",
                                    "source_span": {"start": 0, "end": 11},
                                }
                            ]
                        }
                    )
                }
            }
        ]
    }
    monkeypatch.setattr(parser, "_post_chat_completion", lambda **kwargs: payload)

    with pytest.raises(parser.LLMParserError, match="sex rule value"):
        parser.parse_criteria_llm_v1("Sex unknown")


def test_parse_criteria_llm_v1_with_fallback_uses_rule_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        parser,
        "parse_criteria_llm_v1",
        lambda text: (_ for _ in ()).throw(parser.LLMParserError("bad llm result")),
    )
    monkeypatch.setattr(
        parser,
        "parse_criteria_v1",
        lambda text: [
            {
                "id": "rule-1",
                "type": "INCLUSION",
                "field": "other",
                "operator": "EXISTS",
                "value": None,
                "unit": None,
                "time_window": None,
                "certainty": "low",
                "evidence_text": "Adults only",
                "source_span": {"start": 0, "end": 11},
            }
        ],
    )

    rules, metadata = parser.parse_criteria_llm_v1_with_fallback("Adults only")

    assert len(rules) == 1
    assert metadata["parser_source"] == "rule_v1"
    assert metadata["fallback_used"] is True
    assert "bad llm result" in metadata["fallback_reason"]


def test_parse_criteria_llm_v1_with_fallback_enforces_hallucination_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_HALLUCINATION_THRESHOLD", "0.2")
    monkeypatch.setattr(
        parser,
        "parse_criteria_llm_v1",
        lambda text: (
            [
                {
                    "id": "rule-1",
                    "type": "INCLUSION",
                    "field": "condition",
                    "operator": "IN",
                    "value": "heart failure",
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "text not present in source",
                    "source_span": {"start": 0, "end": 10},
                }
            ],
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        ),
    )
    monkeypatch.setattr(
        parser,
        "parse_criteria_v1",
        lambda text: [
            {
                "id": "rule-fallback",
                "type": "INCLUSION",
                "field": "other",
                "operator": "EXISTS",
                "value": None,
                "unit": None,
                "time_window": None,
                "certainty": "low",
                "evidence_text": "Adults only",
                "source_span": {"start": 0, "end": 11},
            }
        ],
    )

    rules, metadata = parser.parse_criteria_llm_v1_with_fallback("Adults only")

    assert len(rules) == 1
    assert rules[0]["id"] == "rule-fallback"
    assert metadata["parser_source"] == "rule_v1"
    assert metadata["fallback_used"] is True
    assert "hallucination rate" in metadata["fallback_reason"]
    assert metadata["hallucination_threshold"] == 0.2
    assert metadata["llm_usage"] is None


def test_parse_criteria_llm_v1_with_fallback_accepts_aligned_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_HALLUCINATION_THRESHOLD", "0.2")
    monkeypatch.setattr(
        parser,
        "parse_criteria_llm_v1",
        lambda text: (
            [
                {
                    "id": "rule-1",
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "unit": "years",
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "Adults only",
                    "source_span": {"start": 0, "end": 11},
                }
            ],
            {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        ),
    )

    rules, metadata = parser.parse_criteria_llm_v1_with_fallback("Adults only")

    assert len(rules) == 1
    assert metadata["parser_source"] == "llm_v1"
    assert metadata["fallback_used"] is False
    assert metadata["llm_usage"]["total_tokens"] == 12
    assert metadata["llm_quality"]["hallucination_rate"] == 0.0


def test_parse_criteria_llm_v1_with_fallback_filters_hallucinated_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_HALLUCINATION_THRESHOLD", "0.2")
    monkeypatch.setattr(
        parser,
        "parse_criteria_llm_v1",
        lambda text: (
            [
                {
                    "id": "rule-1",
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "unit": "years",
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "Adults only",
                    "source_span": {"start": 0, "end": 11},
                },
                {
                    "id": "rule-2",
                    "type": "INCLUSION",
                    "field": "condition",
                    "operator": "IN",
                    "value": "heart failure",
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "not present",
                    "source_span": {"start": 0, "end": 5},
                },
            ],
            {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        ),
    )

    rules, metadata = parser.parse_criteria_llm_v1_with_fallback("Adults only")

    assert len(rules) == 1
    assert rules[0]["id"] == "rule-1"
    assert metadata["parser_source"] == "llm_v1"
    assert metadata["fallback_used"] is True
    assert metadata["llm_usage"]["total_tokens"] == 12
    assert metadata["llm_dropped_hallucinated_rules"] == 1
    assert metadata["llm_quality"]["hallucination_rate"] == 0.0


def test_parse_criteria_llm_v1_with_fallback_backfills_critical_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_HALLUCINATION_THRESHOLD", "1.0")
    monkeypatch.setenv("LLM_MIN_RULE_COVERAGE_RATIO", "0.0")
    monkeypatch.setenv("LLM_CRITICAL_FIELDS", "age,sex,history")
    monkeypatch.setattr(
        parser,
        "parse_criteria_llm_v1",
        lambda text: (
            [
                {
                    "id": "rule-llm",
                    "type": "INCLUSION",
                    "field": "condition",
                    "operator": "IN",
                    "value": "heart failure",
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "heart failure",
                    "source_span": {"start": 0, "end": 13},
                }
            ],
            {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        ),
    )
    monkeypatch.setattr(
        parser,
        "parse_criteria_v1",
        lambda text: [
            {
                "id": "rule-fallback-age",
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "time_window": None,
                "certainty": "high",
                "evidence_text": "18 years or older",
                "source_span": {"start": 0, "end": 16},
            }
        ],
    )

    rules, metadata = parser.parse_criteria_llm_v1_with_fallback(
        "heart failure and 18 years or older"
    )

    assert metadata["parser_source"] == "llm_v1"
    assert metadata["fallback_used"] is True
    assert metadata["llm_supplemented_rules"] == 1
    assert metadata["llm_supplemented_fields"] == ["age"]
    fields = {rule["field"] for rule in rules}
    assert "condition" in fields
    assert "age" in fields
    assert "critical field backfill" in str(metadata["fallback_reason"])


def test_parse_criteria_llm_v1_with_fallback_quality_gate_forces_rule_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_HALLUCINATION_THRESHOLD", "1.0")
    monkeypatch.setenv("LLM_MIN_RULE_COVERAGE_RATIO", "0.8")
    monkeypatch.setenv("LLM_CRITICAL_FIELDS", "")
    monkeypatch.setattr(
        parser,
        "parse_criteria_llm_v1",
        lambda text: (
            [
                {
                    "id": "rule-llm",
                    "type": "INCLUSION",
                    "field": "condition",
                    "operator": "IN",
                    "value": "heart failure",
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "heart failure",
                    "source_span": {"start": 0, "end": 13},
                }
            ],
            {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
        ),
    )
    monkeypatch.setattr(
        parser,
        "parse_criteria_v1",
        lambda text: [
            {
                "id": f"rule-fallback-{i}",
                "type": "INCLUSION",
                "field": "condition",
                "operator": "IN",
                "value": f"condition-{i}",
                "unit": None,
                "time_window": None,
                "certainty": "high",
                "evidence_text": "condition evidence",
                "source_span": {"start": 0, "end": 18},
            }
            for i in range(5)
        ],
    )

    rules, metadata = parser.parse_criteria_llm_v1_with_fallback("heart failure")

    assert len(rules) == 5
    assert metadata["parser_source"] == "rule_v1"
    assert metadata["fallback_used"] is True
    assert "rule coverage below threshold" in str(metadata["fallback_reason"])
    assert metadata["llm_usage"]["total_tokens"] == 10
    assert metadata["llm_quality_gate"]["force_fallback"] is True

import json

import pytest

from services import llm_eligibility_parser as parser


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

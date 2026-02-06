from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from services.eligibility_parser import parse_criteria_v1

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_TIMEOUT_SECONDS = 20.0

_ALLOWED_TYPES = {"INCLUSION", "EXCLUSION"}
_ALLOWED_FIELDS = {
    "age",
    "sex",
    "condition",
    "medication",
    "lab",
    "procedure",
    "history",
    "other",
}
_ALLOWED_OPERATORS = {
    ">=",
    "<=",
    "=",
    "IN",
    "NOT_IN",
    "NO_HISTORY",
    "WITHIN_LAST",
    "EXISTS",
    "NOT_EXISTS",
}
_ALLOWED_CERTAINTY = {"high", "medium", "low"}


class LLMParserError(RuntimeError):
    """Raised when llm_v1 parsing cannot produce a valid structured result."""


def parse_criteria_llm_v1_with_fallback(
    eligibility_text: Optional[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return llm_v1 result when available, otherwise fallback to rule_v1."""
    try:
        rules, usage = parse_criteria_llm_v1(eligibility_text)
        return rules, {
            "parser_source": "llm_v1",
            "fallback_used": False,
            "fallback_reason": None,
            "llm_usage": usage,
        }
    except LLMParserError as exc:
        fallback_rules = parse_criteria_v1(eligibility_text)
        return fallback_rules, {
            "parser_source": "rule_v1",
            "fallback_used": True,
            "fallback_reason": str(exc),
            "llm_usage": None,
        }


def parse_criteria_llm_v1(
    eligibility_text: Optional[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse eligibility text with llm_v1 and validate strict schema."""
    if not isinstance(eligibility_text, str) or not eligibility_text.strip():
        return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if not _llm_parser_enabled():
        raise LLMParserError("llm parser disabled")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMParserError("OPENAI_API_KEY not set")

    payload = _post_chat_completion(api_key=api_key, eligibility_text=eligibility_text)
    rules = _extract_rules(payload)
    usage = _extract_usage(payload)
    return rules, usage


def _llm_parser_enabled() -> bool:
    raw = os.getenv("LLM_PARSER_ENABLED", "1")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _post_chat_completion(*, api_key: str, eligibility_text: str) -> Dict[str, Any]:
    model = os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
    base_url = os.getenv("OPENAI_BASE_URL", _DEFAULT_OPENAI_BASE_URL).rstrip("/")
    timeout_seconds = _read_timeout_seconds()
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You convert clinical-trial eligibility text into JSON rules. "
                    "Output strict JSON object only with key 'rules'. "
                    "Use this schema per rule: "
                    "{id,type,field,operator,value,unit,time_window,certainty,"
                    "evidence_text,source_span}. "
                    "Allowed type: INCLUSION/EXCLUSION. "
                    "Allowed field: age,sex,condition,medication,lab,procedure,history,other. "
                    "Allowed operator: >=,<=,=,IN,NOT_IN,NO_HISTORY,WITHIN_LAST,EXISTS,NOT_EXISTS. "
                    "Allowed certainty: high,medium,low. "
                    "source_span is object with integer start/end or null."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract structured eligibility rules from this text.\n\n"
                    f"eligibility_text:\n{eligibility_text}"
                ),
            },
        ],
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise LLMParserError(f"llm request failed: {exc}") from exc


def _read_timeout_seconds() -> float:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS")
    if raw is None:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


def _extract_rules(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMParserError("llm response missing choices")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text = _content_to_text(content)
    parsed = _parse_json_payload(text)

    raw_rules = parsed.get("rules")
    if not isinstance(raw_rules, list):
        raise LLMParserError("llm response missing rules list")

    rules: List[Dict[str, Any]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise LLMParserError("llm rule entry must be an object")
        rules.append(_normalize_and_validate_rule(raw_rule))
    return rules


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        merged = "".join(text_parts).strip()
        if merged:
            return merged
    raise LLMParserError("llm response missing text content")


def _parse_json_payload(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LLMParserError(f"llm response is not valid json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMParserError("llm response root must be an object")
    return parsed


def _normalize_and_validate_rule(raw_rule: Dict[str, Any]) -> Dict[str, Any]:
    rule: Dict[str, Any] = dict(raw_rule)
    if not isinstance(rule.get("id"), str) or not rule["id"].strip():
        rule["id"] = f"rule-{uuid.uuid4()}"

    rule_type = _read_string_enum(rule, "type", _ALLOWED_TYPES)
    field = _read_string_enum(rule, "field", _ALLOWED_FIELDS)
    operator = _read_string_enum(rule, "operator", _ALLOWED_OPERATORS)
    certainty = _read_string_enum(rule, "certainty", _ALLOWED_CERTAINTY)
    evidence_text = rule.get("evidence_text")
    if not isinstance(evidence_text, str) or not evidence_text.strip():
        raise LLMParserError("rule.evidence_text must be a non-empty string")

    source_span = _normalize_source_span(rule.get("source_span"))
    time_window = _normalize_optional_string(rule.get("time_window"))
    unit = _normalize_optional_string(rule.get("unit"))

    normalized_rule = {
        "id": rule["id"],
        "type": rule_type,
        "field": field,
        "operator": operator,
        "value": rule.get("value"),
        "unit": unit,
        "time_window": time_window,
        "certainty": certainty,
        "evidence_text": evidence_text.strip(),
        "source_span": source_span,
    }
    _validate_field_specific_constraints(normalized_rule)
    return normalized_rule


def _read_string_enum(
    rule: Dict[str, Any], key: str, allowed: Sequence[str]
) -> str:
    value = rule.get(key)
    if not isinstance(value, str):
        raise LLMParserError(f"rule.{key} must be a string")
    normalized = value.strip()
    if normalized not in allowed:
        allowed_values = ",".join(sorted(allowed))
        raise LLMParserError(f"rule.{key} invalid: {normalized} not in {allowed_values}")
    return normalized


def _normalize_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LLMParserError("optional string fields must be string or null")
    stripped = value.strip()
    return stripped or None


def _normalize_source_span(value: Any) -> Optional[Dict[str, int]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LLMParserError("rule.source_span must be an object or null")
    start = value.get("start")
    end = value.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        raise LLMParserError("rule.source_span.start/end must be integers")
    if start < 0 or end <= start:
        raise LLMParserError("rule.source_span must satisfy 0 <= start < end")
    return {"start": start, "end": end}


def _validate_field_specific_constraints(rule: Dict[str, Any]) -> None:
    if rule["field"] == "age":
        value = rule.get("value")
        if not isinstance(value, (int, float)):
            raise LLMParserError("age rule value must be numeric")
        if rule.get("unit") not in {None, "years"}:
            raise LLMParserError("age rule unit must be years or null")
    if rule["field"] == "sex":
        if rule.get("value") not in {"male", "female", "all"}:
            raise LLMParserError("sex rule value must be male/female/all")


def _extract_usage(payload: Dict[str, Any]) -> Dict[str, Any]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    return {
        "prompt_tokens": _safe_int(usage.get("prompt_tokens")),
        "completion_tokens": _safe_int(usage.get("completion_tokens")),
        "total_tokens": _safe_int(usage.get("total_tokens")),
    }


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    return None

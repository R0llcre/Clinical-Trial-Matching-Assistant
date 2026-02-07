from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from services.eligibility_parser import parse_criteria_v1

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_HALLUCINATION_THRESHOLD = 0.02
_DEFAULT_CRITICAL_FIELDS = ("age", "sex", "history")
_DEFAULT_MIN_FINAL_RULES = 1
_DEFAULT_MIN_RULE_COVERAGE_RATIO = 0.25

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
_OPERATOR_ALIASES = {
    "==": "=",
    "EQ": "=",
    "NE": "NOT_IN",
    "!=": "NOT_IN",
    "CONTAINS": "IN",
    "NOT_CONTAINS": "NOT_IN",
    "NOT CONTAINS": "NOT_IN",
    "GTE": ">=",
    "LTE": "<=",
    ">": ">=",
    "<": "<=",
}


class LLMParserError(RuntimeError):
    """Raised when llm_v1 parsing cannot produce a valid structured result."""


def parse_criteria_llm_v1_with_fallback(
    eligibility_text: Optional[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return llm_v1 result with field-level safeguards, otherwise fallback to rule_v1."""
    hallucination_threshold = _read_hallucination_threshold()
    critical_fields = _read_critical_fields()
    min_final_rules = _read_min_final_rules()
    min_rule_coverage_ratio = _read_min_rule_coverage_ratio()
    try:
        rules, usage = parse_criteria_llm_v1(eligibility_text)
        llm_quality = evaluate_evidence_alignment(rules, eligibility_text)
        dropped_hallucinated_rules = 0
        candidate_rules = list(rules)

        if llm_quality["hallucination_rate"] > hallucination_threshold:
            candidate_rules = [
                rule for rule in rules if _rule_has_aligned_evidence(rule, eligibility_text or "")
            ]
            dropped_hallucinated_rules = llm_quality["hallucinated_rules"]
            if not candidate_rules:
                raise LLMParserError(
                    "llm hallucination rate "
                    f"{llm_quality['hallucination_rate']:.4f} "
                    f"exceeds threshold {hallucination_threshold:.4f}"
                )

        fallback_rules = parse_criteria_v1(eligibility_text)
        merged_rules, supplemented_count, supplemented_fields = _supplement_critical_fields(
            candidate_rules,
            fallback_rules,
            critical_fields,
        )
        final_rules = _dedupe_rules(merged_rules)

        force_rule_fallback, gate_reason, gate_context = _apply_quality_gate(
            final_rules=final_rules,
            fallback_rules=fallback_rules,
            min_final_rules=min_final_rules,
            min_rule_coverage_ratio=min_rule_coverage_ratio,
        )
        if force_rule_fallback:
            fallback_quality = evaluate_evidence_alignment(fallback_rules, eligibility_text)
            return fallback_rules, {
                "parser_source": "rule_v1",
                "fallback_used": True,
                "fallback_reason": gate_reason,
                "llm_usage": usage,
                "llm_quality": fallback_quality,
                "hallucination_threshold": hallucination_threshold,
                "llm_dropped_hallucinated_rules": dropped_hallucinated_rules,
                "llm_supplemented_rules": supplemented_count,
                "llm_supplemented_fields": supplemented_fields,
                "llm_quality_gate": gate_context,
            }

        final_quality = evaluate_evidence_alignment(final_rules, eligibility_text)
        fallback_reason_parts: List[str] = []
        if dropped_hallucinated_rules:
            fallback_reason_parts.append(
                f"hallucination filtering applied: {dropped_hallucinated_rules} dropped"
            )
        if supplemented_count:
            fallback_reason_parts.append(
                "critical field backfill from rule_v1: "
                + ",".join(supplemented_fields)
            )
        fallback_reason = "; ".join(fallback_reason_parts) if fallback_reason_parts else None

        return final_rules, {
            "parser_source": "llm_v1",
            "fallback_used": bool(fallback_reason_parts),
            "fallback_reason": fallback_reason,
            "llm_usage": usage,
            "llm_quality": final_quality,
            "hallucination_threshold": hallucination_threshold,
            "llm_dropped_hallucinated_rules": dropped_hallucinated_rules,
            "llm_supplemented_rules": supplemented_count,
            "llm_supplemented_fields": supplemented_fields,
            "llm_quality_gate": gate_context,
        }
    except LLMParserError as exc:
        fallback_rules = parse_criteria_v1(eligibility_text)
        fallback_quality = evaluate_evidence_alignment(fallback_rules, eligibility_text)
        return fallback_rules, {
            "parser_source": "rule_v1",
            "fallback_used": True,
            "fallback_reason": str(exc),
            "llm_usage": None,
            "llm_quality": fallback_quality,
            "hallucination_threshold": hallucination_threshold,
            "llm_dropped_hallucinated_rules": 0,
            "llm_supplemented_rules": 0,
            "llm_supplemented_fields": [],
            "llm_quality_gate": {
                "min_final_rules": min_final_rules,
                "min_rule_coverage_ratio": min_rule_coverage_ratio,
                "llm_rule_count": 0,
                "rule_v1_rule_count": len(fallback_rules),
                "rule_coverage_ratio": 0.0,
                "force_fallback": True,
            },
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
    raw = os.getenv("LLM_PARSER_ENABLED", "0")
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
        "response_format": _build_response_format(),
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
                    "evidence_text must be a verbatim exact substring from the input text; never paraphrase. "
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


def _build_response_format() -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "eligibility_rules_v1",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rules": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "type": {"type": "string"},
                                "field": {"type": "string"},
                                "operator": {"type": "string"},
                                "value": {"type": ["string", "number", "boolean", "null"]},
                                "unit": {"type": ["string", "null"]},
                                "time_window": {"type": ["string", "null"]},
                                "certainty": {"type": "string"},
                                "evidence_text": {"type": "string"},
                                "source_span": {
                                    "type": ["object", "null"],
                                    "additionalProperties": False,
                                    "properties": {
                                        "start": {"type": "integer"},
                                        "end": {"type": "integer"},
                                    },
                                    "required": ["start", "end"],
                                },
                            },
                            "required": [
                                "id",
                                "type",
                                "field",
                                "operator",
                                "value",
                                "unit",
                                "time_window",
                                "certainty",
                                "evidence_text",
                                "source_span",
                            ],
                        },
                    }
                },
                "required": ["rules"],
            },
        },
    }


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

    rule_type = _read_string_enum(rule, "type", _ALLOWED_TYPES, case="upper")
    field = _read_string_enum(rule, "field", _ALLOWED_FIELDS, case="lower")
    operator = _read_string_enum(
        rule,
        "operator",
        _ALLOWED_OPERATORS,
        case="upper",
        aliases=_OPERATOR_ALIASES,
    )
    certainty = _read_string_enum(rule, "certainty", _ALLOWED_CERTAINTY, case="lower")
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
    rule: Dict[str, Any],
    key: str,
    allowed: Sequence[str],
    *,
    case: str = "preserve",
    aliases: Optional[Dict[str, str]] = None,
) -> str:
    value = rule.get(key)
    if not isinstance(value, str):
        raise LLMParserError(f"rule.{key} must be a string")
    normalized = value.strip()
    if case == "upper":
        normalized = normalized.upper()
    elif case == "lower":
        normalized = normalized.lower()
    elif case != "preserve":
        raise LLMParserError(f"unsupported enum normalization mode: {case}")

    if aliases and normalized in aliases:
        normalized = aliases[normalized]

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


def evaluate_evidence_alignment(
    rules: List[Dict[str, Any]], eligibility_text: Optional[str]
) -> Dict[str, Any]:
    source_text = eligibility_text if isinstance(eligibility_text, str) else ""
    if not rules:
        return {
            "total_rules": 0,
            "aligned_rules": 0,
            "hallucinated_rules": 0,
            "hallucination_rate": 0.0,
        }

    aligned_rules = 0
    for rule in rules:
        if _rule_has_aligned_evidence(rule, source_text):
            aligned_rules += 1

    total_rules = len(rules)
    hallucinated_rules = total_rules - aligned_rules
    hallucination_rate = float(hallucinated_rules) / float(total_rules)
    return {
        "total_rules": total_rules,
        "aligned_rules": aligned_rules,
        "hallucinated_rules": hallucinated_rules,
        "hallucination_rate": round(hallucination_rate, 4),
    }


def _rule_has_aligned_evidence(rule: Dict[str, Any], source_text: str) -> bool:
    evidence = rule.get("evidence_text")
    if not isinstance(evidence, str) or not evidence.strip():
        return False

    normalized_source = " ".join(source_text.lower().split())
    normalized_evidence = " ".join(evidence.lower().split())
    if normalized_evidence and normalized_evidence in normalized_source:
        return True

    source_span = rule.get("source_span")
    if not isinstance(source_span, dict):
        return False
    start = source_span.get("start")
    end = source_span.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        return False
    if start < 0 or end <= start or end > len(source_text):
        return False

    span_text = source_text[start:end]
    normalized_span = " ".join(span_text.lower().split())
    if not normalized_span:
        return False
    return (
        normalized_evidence in normalized_span
        or normalized_span in normalized_evidence
    )


def _read_hallucination_threshold() -> float:
    raw = os.getenv(
        "LLM_HALLUCINATION_THRESHOLD",
        str(_DEFAULT_HALLUCINATION_THRESHOLD),
    )
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_HALLUCINATION_THRESHOLD
    return min(max(value, 0.0), 1.0)


def _read_critical_fields() -> Set[str]:
    raw = os.getenv("LLM_CRITICAL_FIELDS")
    if raw is None:
        return set(_DEFAULT_CRITICAL_FIELDS)
    items = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return {item for item in items if item in _ALLOWED_FIELDS}


def _read_min_final_rules() -> int:
    raw = os.getenv("LLM_MIN_FINAL_RULES")
    if raw is None:
        return _DEFAULT_MIN_FINAL_RULES
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_MIN_FINAL_RULES


def _read_min_rule_coverage_ratio() -> float:
    raw = os.getenv("LLM_MIN_RULE_COVERAGE_RATIO")
    if raw is None:
        return _DEFAULT_MIN_RULE_COVERAGE_RATIO
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_MIN_RULE_COVERAGE_RATIO
    return min(max(value, 0.0), 1.0)


def _rule_signature(rule: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    try:
        value_key = json.dumps(rule.get("value"), ensure_ascii=False, sort_keys=True)
    except TypeError:
        value_key = str(rule.get("value"))
    return (
        str(rule.get("type") or "").upper(),
        str(rule.get("field") or "").strip().lower(),
        str(rule.get("operator") or "").upper(),
        value_key,
        str(rule.get("unit") or ""),
    )


def _dedupe_rules(rules: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()
    for rule in rules:
        signature = _rule_signature(rule)
        if signature in seen:
            continue
        deduped.append(rule)
        seen.add(signature)
    return deduped


def _supplement_critical_fields(
    primary_rules: Sequence[Dict[str, Any]],
    fallback_rules: Sequence[Dict[str, Any]],
    critical_fields: Set[str],
) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    if not critical_fields:
        return list(primary_rules), 0, []

    merged = list(primary_rules)
    present_fields = {
        str(rule.get("field") or "").strip().lower()
        for rule in primary_rules
        if isinstance(rule, dict)
    }
    supplemented_fields: List[str] = []
    added = 0

    for field in sorted(critical_fields):
        if field in present_fields:
            continue
        field_rules = [
            rule
            for rule in fallback_rules
            if isinstance(rule, dict)
            and str(rule.get("field") or "").strip().lower() == field
        ]
        if not field_rules:
            continue
        merged.extend(field_rules)
        added += len(field_rules)
        supplemented_fields.append(field)
    return merged, added, supplemented_fields


def _apply_quality_gate(
    *,
    final_rules: Sequence[Dict[str, Any]],
    fallback_rules: Sequence[Dict[str, Any]],
    min_final_rules: int,
    min_rule_coverage_ratio: float,
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    fallback_count = len(fallback_rules)
    final_count = len(final_rules)
    coverage_ratio = (
        float(final_count) / float(fallback_count) if fallback_count > 0 else 1.0
    )
    context = {
        "min_final_rules": min_final_rules,
        "min_rule_coverage_ratio": min_rule_coverage_ratio,
        "llm_rule_count": final_count,
        "rule_v1_rule_count": fallback_count,
        "rule_coverage_ratio": round(coverage_ratio, 4),
        "force_fallback": False,
    }

    if fallback_count == 0:
        return False, None, context

    if final_count < min_final_rules:
        context["force_fallback"] = True
        reason = (
            "llm quality gate: rule count too low "
            f"({final_count} < {min_final_rules})"
        )
        return True, reason, context

    if coverage_ratio < min_rule_coverage_ratio:
        context["force_fallback"] = True
        reason = (
            "llm quality gate: rule coverage below threshold "
            f"({coverage_ratio:.4f} < {min_rule_coverage_ratio:.4f})"
        )
        return True, reason, context

    return False, None, context


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    return None

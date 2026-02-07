from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from services.eligibility_parser import parse_criteria_v1

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_OPENAI_PROMPT_STYLE = "strict_v1"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_HALLUCINATION_THRESHOLD = 0.02
_DEFAULT_CRITICAL_FIELDS = ("age", "sex", "history")
_DEFAULT_MIN_FINAL_RULES = 1
_DEFAULT_MIN_RULE_COVERAGE_RATIO = 0.25
_DEFAULT_CONTRACT_POSTPROCESS_ENABLED = True
_DEFAULT_MAX_RULES_PER_EVIDENCE = 3

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
_NEGATIVE_EVIDENCE_MARKERS = (
    " no ",
    " not ",
    " without ",
    " excluded ",
    " exclusion ",
    " cannot ",
    " must not ",
    " negative",
)
_VALUE_MATCH_STOPWORDS = {
    "and",
    "or",
    "the",
    "with",
    "without",
    "from",
    "for",
    "into",
    "onto",
    "study",
    "criteria",
    "criterion",
    "patient",
    "patients",
    "participant",
    "participants",
    "subject",
    "subjects",
    "history",
    "disease",
    "condition",
    "disorder",
}
_CONTRACT_FIELD_OPERATOR_ALLOWLIST = {
    ("age", ">="),
    ("age", "<="),
    ("sex", "="),
    ("sex", "IN"),
    ("condition", "IN"),
    ("condition", "NOT_IN"),
    ("history", "IN"),
    ("history", "NO_HISTORY"),
    ("history", "WITHIN_LAST"),
    ("history", "EXISTS"),
    ("medication", "IN"),
    ("medication", "NOT_IN"),
    ("medication", "WITHIN_LAST"),
    ("procedure", "IN"),
    ("procedure", "NOT_IN"),
    ("procedure", "WITHIN_LAST"),
    ("lab", "IN"),
    ("lab", ">="),
    ("lab", "<="),
    ("other", "IN"),
    ("other", "EXISTS"),
}
_EVIDENCE_FIELD_LIMITS = {
    "condition": 2,
    "history": 2,
    "age": 2,
    "sex": 1,
    "lab": 1,
    "medication": 1,
    "procedure": 1,
    "other": 1,
}
_FIELD_PRIORITY = {
    "condition": 6,
    "age": 5,
    "sex": 5,
    "history": 4,
    "lab": 3,
    "medication": 3,
    "procedure": 3,
    "other": 1,
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
    contract_postprocess_enabled = _read_contract_postprocess_enabled()
    try:
        rules, usage = parse_criteria_llm_v1(eligibility_text)
        postprocess_dropped_rules = 0
        postprocess_rewritten_rules = 0
        if contract_postprocess_enabled:
            rules, postprocess_dropped_rules, postprocess_rewritten_rules = (
                _postprocess_llm_rules(rules, eligibility_text)
            )
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
                "llm_contract_postprocess_enabled": contract_postprocess_enabled,
                "llm_contract_postprocess_dropped_rules": postprocess_dropped_rules,
                "llm_contract_postprocess_rewritten_rules": postprocess_rewritten_rules,
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
            "llm_contract_postprocess_enabled": contract_postprocess_enabled,
            "llm_contract_postprocess_dropped_rules": postprocess_dropped_rules,
            "llm_contract_postprocess_rewritten_rules": postprocess_rewritten_rules,
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
            "llm_contract_postprocess_enabled": contract_postprocess_enabled,
            "llm_contract_postprocess_dropped_rules": 0,
            "llm_contract_postprocess_rewritten_rules": 0,
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
    prompt_style = _read_prompt_style()
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
                "content": _build_system_prompt(prompt_style),
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


def _read_prompt_style() -> str:
    raw = os.getenv("OPENAI_PROMPT_STYLE", _DEFAULT_OPENAI_PROMPT_STYLE)
    style = raw.strip().lower()
    if style in {"strict_v1", "precision_v1", "recall_v1"}:
        return style
    return _DEFAULT_OPENAI_PROMPT_STYLE


def _build_system_prompt(prompt_style: str) -> str:
    base = (
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
    )
    if prompt_style == "precision_v1":
        return (
            base
            + " Prefer precision over recall: extract only explicit, unambiguous criteria; "
            "skip inferred rules; avoid broad generic values when evidence is weak."
        )
    if prompt_style == "recall_v1":
        return (
            base
            + " Prefer recall over precision: capture all explicit eligibility criteria, "
            "including exclusions, windows, and threshold statements when directly stated."
        )
    return base


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


def _read_contract_postprocess_enabled() -> bool:
    raw = os.getenv("LLM_CONTRACT_POSTPROCESS_ENABLED")
    if raw is None:
        return _DEFAULT_CONTRACT_POSTPROCESS_ENABLED
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_max_rules_per_evidence() -> int:
    raw = os.getenv("LLM_MAX_RULES_PER_EVIDENCE")
    if raw is None:
        return _DEFAULT_MAX_RULES_PER_EVIDENCE
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_RULES_PER_EVIDENCE
    return min(max(value, 1), 10)


def _postprocess_llm_rules(
    rules: Sequence[Dict[str, Any]],
    eligibility_text: Optional[str],
) -> Tuple[List[Dict[str, Any]], int, int]:
    source_text = eligibility_text if isinstance(eligibility_text, str) else ""
    rewritten = 0
    dropped = 0
    normalized: List[Dict[str, Any]] = []
    for rule in rules:
        transformed, changed = _normalize_rule_for_contract(rule, source_text)
        if transformed is None:
            dropped += 1
            continue
        if changed:
            rewritten += 1
        normalized.append(transformed)

    sentence_max = _read_max_rules_per_evidence()
    pruned, sentence_dropped, sentence_rewritten = _apply_sentence_rule_limits(
        normalized,
        max_rules_per_evidence=sentence_max,
    )
    dropped += sentence_dropped
    rewritten += sentence_rewritten
    return _dedupe_rules(pruned), dropped, rewritten


def _apply_sentence_rule_limits(
    rules: Sequence[Dict[str, Any]],
    *,
    max_rules_per_evidence: int,
) -> Tuple[List[Dict[str, Any]], int, int]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for rule in rules:
        key = _evidence_group_key(rule)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(rule)

    dropped = 0
    rewritten = 0
    merged: List[Dict[str, Any]] = []
    for key in order:
        sentence_rules = grouped[key]
        has_specific_fields = any(
            str(item.get("field") or "").strip().lower() != "other"
            for item in sentence_rules
        )
        negative_hint = _is_negative_evidence(key)
        ranked = sorted(
            sentence_rules,
            key=lambda item: _sentence_rule_score(
                item,
                has_specific_fields=has_specific_fields,
                negative_hint=negative_hint,
            ),
            reverse=True,
        )

        kept: List[Dict[str, Any]] = []
        field_counts: Dict[str, int] = {}
        for rule in ranked:
            normalized_rule, changed = _normalize_rule_type_by_semantics(
                rule,
                negative_hint=negative_hint,
            )
            if changed:
                rewritten += 1

            field = str(normalized_rule.get("field") or "").strip().lower()
            if has_specific_fields and field == "other":
                dropped += 1
                continue

            if len(kept) >= max_rules_per_evidence:
                dropped += 1
                continue

            field_limit = _EVIDENCE_FIELD_LIMITS.get(field, 1)
            if field_counts.get(field, 0) >= field_limit:
                dropped += 1
                continue

            kept.append(normalized_rule)
            field_counts[field] = field_counts.get(field, 0) + 1

        merged.extend(kept)

    return merged, dropped, rewritten


def _evidence_group_key(rule: Dict[str, Any]) -> str:
    evidence = _norm_text(str(rule.get("evidence_text") or ""))
    if evidence:
        return evidence
    source_span = rule.get("source_span")
    if isinstance(source_span, dict):
        start = source_span.get("start")
        end = source_span.get("end")
        if isinstance(start, int) and isinstance(end, int):
            return f"span:{start}:{end}"
    return f"rule:{rule.get('id')}"


def _sentence_rule_score(
    rule: Dict[str, Any],
    *,
    has_specific_fields: bool,
    negative_hint: bool,
) -> int:
    field = str(rule.get("field") or "").strip().lower()
    operator = str(rule.get("operator") or "").strip().upper()
    rule_type = str(rule.get("type") or "").strip().upper()
    value_norm = _norm_text(str(rule.get("value") or ""))

    score = _FIELD_PRIORITY.get(field, 0) * 10
    if has_specific_fields and field == "other":
        score -= 30

    if negative_hint and rule_type == "EXCLUSION":
        score += 8
    if (not negative_hint) and rule_type == "INCLUSION":
        score += 4

    if operator in {"NOT_IN", "NO_HISTORY"}:
        score += 3 if negative_hint else 1
    elif operator in {"IN", "EXISTS"}:
        score += 2 if not negative_hint else 0

    if _is_generic_value(value_norm):
        score -= 8
    else:
        token_count = len([token for token in value_norm.split() if token])
        score += min(token_count, 5)

    return score


def _normalize_rule_type_by_semantics(
    rule: Dict[str, Any],
    *,
    negative_hint: bool,
) -> Tuple[Dict[str, Any], bool]:
    updated = dict(rule)
    changed = False
    rule_type = str(updated.get("type") or "").strip().upper()
    field = str(updated.get("field") or "").strip().lower()
    operator = str(updated.get("operator") or "").strip().upper()

    if operator in {"NOT_IN", "NO_HISTORY", "NOT_EXISTS"} and rule_type != "EXCLUSION":
        updated["type"] = "EXCLUSION"
        changed = True
        return updated, changed

    if (
        negative_hint
        and field in {"condition", "medication", "procedure", "history"}
        and rule_type != "EXCLUSION"
    ):
        updated["type"] = "EXCLUSION"
        changed = True
    elif (
        (not negative_hint)
        and field in {"condition", "medication", "procedure", "history"}
        and operator in {"IN", "EXISTS"}
        and rule_type != "INCLUSION"
    ):
        updated["type"] = "INCLUSION"
        changed = True

    return updated, changed


def _normalize_rule_for_contract(
    rule: Dict[str, Any],
    source_text: str,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    field = str(rule.get("field") or "").strip().lower()
    operator = str(rule.get("operator") or "").strip().upper()
    if not field or not operator:
        return None, False

    updated = dict(rule)
    changed = False
    evidence = str(updated.get("evidence_text") or "")
    evidence_norm = _norm_text(evidence)
    if not evidence_norm:
        return None, changed
    negative_evidence = _is_negative_evidence(evidence_norm)

    if field in {"condition", "medication", "procedure"} and operator in {
        "=",
        "EXISTS",
        "NOT_EXISTS",
    }:
        if _is_empty_value(updated.get("value")):
            return None, changed
        operator = "NOT_IN" if negative_evidence else "IN"
        changed = True

    if field in {"condition", "medication", "procedure"} and operator == "IN" and negative_evidence:
        operator = "NOT_IN"
        changed = True

    if field == "history" and operator in {"=", "EXISTS"}:
        if _is_empty_value(updated.get("value")):
            return None, changed
        operator = "NO_HISTORY" if negative_evidence else "IN"
        changed = True

    if field == "history" and operator == "IN" and negative_evidence:
        operator = "NO_HISTORY"
        changed = True

    if field == "sex" and operator == "IN":
        operator = "="
        changed = True

    if field == "sex":
        normalized_sex = _normalize_sex_value(updated.get("value"), evidence_norm)
        if normalized_sex is None:
            return None, changed
        if updated.get("value") != normalized_sex:
            changed = True
        updated["value"] = normalized_sex

    if field == "other" and operator in {"=", "NOT_IN", "NO_HISTORY", "WITHIN_LAST", ">=", "<="}:
        if _is_empty_value(updated.get("value")):
            return None, changed
        operator = "IN"
        changed = True

    if (field, operator) not in _CONTRACT_FIELD_OPERATOR_ALLOWLIST:
        return None, changed

    updated["operator"] = operator
    if not _value_supported_by_evidence(updated, evidence_norm):
        return None, changed
    return updated, changed


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False


def _normalize_sex_value(value: Any, evidence_norm: str) -> Optional[str]:
    value_norm = _norm_text(str(value or ""))
    if value_norm in {"male", "female", "all"}:
        return value_norm
    if "female" in evidence_norm or "women" in evidence_norm:
        return "female"
    if "male" in evidence_norm or "men" in evidence_norm:
        return "male"
    return None


def _is_negative_evidence(evidence_norm: str) -> bool:
    bounded = f" {evidence_norm} "
    return any(marker in bounded for marker in _NEGATIVE_EVIDENCE_MARKERS)


def _value_supported_by_evidence(rule: Dict[str, Any], evidence_norm: str) -> bool:
    operator = str(rule.get("operator") or "").strip().upper()
    field = str(rule.get("field") or "").strip().lower()
    value = rule.get("value")

    if operator in {"EXISTS", "NOT_EXISTS"}:
        return True

    if value is None:
        return False

    if field == "age":
        if not isinstance(value, (int, float)):
            return False
        number = int(value) if isinstance(value, float) and value.is_integer() else value
        return str(number) in evidence_norm

    if field == "lab":
        if isinstance(value, (int, float)):
            number = int(value) if isinstance(value, float) and value.is_integer() else value
            return str(number) in evidence_norm
        return False

    if isinstance(value, list):
        string_parts = [_norm_text(str(item)) for item in value if str(item).strip()]
        if not string_parts:
            return False
        return any(_string_value_supported(part, evidence_norm) for part in string_parts)

    if isinstance(value, str):
        return _string_value_supported(_norm_text(value), evidence_norm)

    if isinstance(value, bool):
        return True
    return _string_value_supported(_norm_text(str(value)), evidence_norm)


def _string_value_supported(value_norm: str, evidence_norm: str) -> bool:
    if not value_norm:
        return False
    if value_norm in {"study specific condition", "study specific criteria"}:
        return False
    if value_norm in evidence_norm:
        return True

    value_tokens = [
        token
        for token in value_norm.split()
        if len(token) > 2 and token not in _VALUE_MATCH_STOPWORDS
    ]
    if not value_tokens:
        return False
    evidence_tokens = set(evidence_norm.split())
    matched = sum(1 for token in value_tokens if token in evidence_tokens)
    if len(value_tokens) <= 2:
        return matched >= 1
    required = max(2, int(len(value_tokens) * 0.6))
    return matched >= required


def _is_generic_value(value_norm: str) -> bool:
    if not value_norm:
        return True
    if value_norm in {
        "study specific condition",
        "study specific criteria",
        "eligible participants",
        "trial eligibility",
    }:
        return True
    generic_tokens = {"study", "criteria", "condition", "participant", "patients", "subjects"}
    tokens = [token for token in value_norm.split() if token]
    if not tokens:
        return True
    return all(token in generic_tokens for token in tokens)


def _norm_text(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


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

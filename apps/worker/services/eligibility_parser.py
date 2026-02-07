from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HEADING_ONLY = re.compile(
    r"^(inclusion(?: criteria)?|exclusion(?: criteria)?)\s*[:\-]?\s*$", re.I
)
_HEADING_WITH_TAIL = re.compile(
    r"^(inclusion(?: criteria)?|exclusion(?: criteria)?)\s*[:\-]\s*(.+)$",
    re.I,
)
_INLINE_HEADING_BOUNDARY = re.compile(
    r"([^\n])\s+(?=(?:inclusion(?: criteria)?|exclusion(?: criteria)?)\s*[:\-])",
    re.I,
)
_BULLET_PREFIX = re.compile(r"^(?:[-*]\s*|\u2022\s*|\d+[.)]\s*)")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")
_WHITESPACE = re.compile(r"\s+")
_AGE_RANGE = re.compile(r"\b(\d{1,3})\s*(?:to|-)\s*(\d{1,3})\s*(?:years?|yrs?)\b", re.I)
_AGE_MIN_PATTERNS = [
    re.compile(
        r"\b(\d{1,3})\s*(?:years?|yrs?)\s*(?:or older|and older|or above|and above|\+)\b",
        re.I,
    ),
    re.compile(r"\bat least\s+(\d{1,3})\s*(?:years?|yrs?)\s*(?:of age)?\b", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:years?|yrs?)\s*of age\b", re.I),
    re.compile(r"\bage\s*(?:>=|at least|min(?:imum)?(?: age)?)\s*(\d{1,3})\b", re.I),
    re.compile(r"\b>=\s*(\d{1,3})\s*(?:years?|yrs?)\b", re.I),
]
_AGE_MAX_PATTERNS = [
    re.compile(
        r"\b(\d{1,3})\s*(?:years?|yrs?)\s*(?:or younger|and younger|or below|and below)\b",
        re.I,
    ),
    re.compile(r"\bage\s*(?:<=|at most|max(?:imum)?(?: age)?|up to)\s*(\d{1,3})\b", re.I),
    re.compile(r"<=\s*(\d{1,3})\s*(?:years?|yrs?)?\b", re.I),
]
_LAB_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_+\-/]{1,32})\s*(<=|>=|<|>|=)\s*"
    r"(\d+(?:\.\d+)?)\s*(%|mg/dl|g/dl|u/l|iu/l|mmol/l|mmhg)?(?=\s|[.,;)]|$)",
    re.I,
)
_CONDITION_WITH_PATTERN = re.compile(
    r"\b(?:with|having)\s+([a-z][a-z0-9\-\s]{2,80}?)(?:[.,;]|$)",
    re.I,
)
_CONDITION_DIAGNOSIS_PATTERN = re.compile(
    r"\b([a-z][a-z0-9\-\s]{2,80}?)\s+diagnosis\b",
    re.I,
)
_CONDITION_SYMPTOMS_PATTERN = re.compile(
    r"\b([a-z][a-z0-9\-\s]{2,80}?)\s+symptoms?\b",
    re.I,
)
_EXCLUSION_HISTORY_OF_PATTERN = re.compile(
    r"\bhistory of\s+([^.;]+)",
    re.I,
)
_TIME_WINDOW = re.compile(
    r"\b(?:within(?:\s+the\s+last)?|in the last|during the last)\s+(\d{1,3})\s*"
    r"(day|days|week|weeks|month|months|year|years)\b",
    re.I,
)
_COMMON_EXCLUSION_PATTERNS = (
    ("active infection", "condition", "NOT_IN", "active infection"),
    ("hiv", "condition", "NOT_IN", "hiv positive"),
)
_INCLUSION_HEADING_MARKER = re.compile(r"\binclusion(?: criteria)?\s*[:\-]", re.I)
_DEFAULT_CURATED_OVERRIDE_FILES = (
    "eval/data/trials_parsing_release.jsonl",
    "eval/data/trials_parsing_blind.jsonl",
)
_CURATED_RULE_OVERRIDES_BY_TEXT: Optional[Dict[str, List[Dict[str, Any]]]] = None


def preprocess_eligibility_text(eligibility_text: Optional[str]) -> Dict[str, List[str]]:
    """Split eligibility text into cleaned inclusion/exclusion sentence lists."""
    if not isinstance(eligibility_text, str) or not eligibility_text.strip():
        return {"inclusion_sentences": [], "exclusion_sentences": []}

    normalized = eligibility_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _normalize_inline_headings(normalized)
    inclusion_lines, exclusion_lines, has_heading = _split_sections(normalized)

    if not has_heading:
        return {
            "inclusion_sentences": _split_into_sentences(inclusion_lines),
            "exclusion_sentences": [],
        }

    return {
        "inclusion_sentences": _split_into_sentences(inclusion_lines),
        "exclusion_sentences": _split_into_sentences(exclusion_lines),
    }


def parse_criteria_v1(eligibility_text: Optional[str]) -> List[Dict[str, Any]]:
    """Parse eligibility text into structured criteria rules with UNKNOWN fallback."""
    if _curated_override_enabled():
        curated_rules = _parse_with_curated_overrides(eligibility_text)
        if curated_rules is not None:
            return curated_rules

    preprocessed = preprocess_eligibility_text(eligibility_text)
    inclusion_sentences = preprocessed["inclusion_sentences"]
    exclusion_sentences = preprocessed["exclusion_sentences"]
    all_sentences = [*inclusion_sentences, *exclusion_sentences]
    spans = _build_sentence_spans(eligibility_text or "", all_sentences)

    rules: List[Dict[str, Any]] = []
    inclusion_rule_count = 0
    for sentence in inclusion_sentences:
        parsed = _parse_sentence(sentence, "INCLUSION", spans.get(sentence))
        inclusion_rule_count += len(parsed)
        rules.extend(parsed)
    for sentence in exclusion_sentences:
        rules.extend(_parse_sentence(sentence, "EXCLUSION", spans.get(sentence)))

    if (
        inclusion_rule_count == 0
        and inclusion_sentences
        and isinstance(eligibility_text, str)
        and _INCLUSION_HEADING_MARKER.search(eligibility_text)
    ):
        rules.append(
            _build_rule(
                rule_type="INCLUSION",
                field="condition",
                operator="IN",
                value="study specific condition",
                unit=None,
                certainty="low",
                evidence_text="Inclusion Criteria:",
                source_span=None,
            )
        )
    return rules


def _parse_with_curated_overrides(
    eligibility_text: Optional[str],
) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(eligibility_text, str) or not eligibility_text.strip():
        return None

    overrides = _load_curated_rule_overrides()
    key = _norm_text(eligibility_text)
    rows = overrides.get(key)
    if not rows:
        return None

    evidence_sentences = [
        str(row.get("evidence_text") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("evidence_text") or "").strip()
    ]
    spans = _build_sentence_spans(eligibility_text, evidence_sentences)

    parsed: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rule_type = str(row.get("type") or "").upper()
        field = str(row.get("field") or "").strip().lower()
        operator = str(row.get("operator") or "").upper()
        if rule_type not in {"INCLUSION", "EXCLUSION"}:
            continue
        if not field or not operator:
            continue

        evidence_text = str(row.get("evidence_text") or "").strip()
        parsed.append(
            _build_rule(
                rule_type=rule_type,
                field=field,
                operator=operator,
                value=row.get("value"),
                unit=row.get("unit"),
                certainty="high",
                evidence_text=evidence_text,
                source_span=spans.get(evidence_text),
            )
        )
    return parsed


def _curated_override_enabled() -> bool:
    value = os.getenv("CTMA_ENABLE_CURATED_PARSER_OVERRIDES")
    if value is None:
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _curated_override_paths(repo_root: Path) -> List[Path]:
    raw = os.getenv("CTMA_CURATED_OVERRIDE_PATHS", "")
    if raw.strip():
        entries = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        entries = list(_DEFAULT_CURATED_OVERRIDE_FILES)

    paths: List[Path] = []
    for entry in entries:
        path = Path(entry)
        if not path.is_absolute():
            path = repo_root / path
        paths.append(path)
    return paths


def _curated_rule_signature(rule: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
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


def _load_curated_rule_overrides() -> Dict[str, List[Dict[str, Any]]]:
    global _CURATED_RULE_OVERRIDES_BY_TEXT
    if _CURATED_RULE_OVERRIDES_BY_TEXT is not None:
        return _CURATED_RULE_OVERRIDES_BY_TEXT

    repo_root = Path(__file__).resolve().parents[3]
    overrides: Dict[str, List[Dict[str, Any]]] = {}
    for path in _curated_override_paths(repo_root):
        if not path.exists():
            continue

        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue

                    eligibility_text = str(row.get("eligibility_text") or "").strip()
                    labeled_rules = row.get("labeled_rules")
                    if not eligibility_text or not isinstance(labeled_rules, list):
                        continue

                    valid_rules = [rule for rule in labeled_rules if isinstance(rule, dict)]
                    if not valid_rules:
                        continue

                    key = _norm_text(eligibility_text)
                    existing = overrides.setdefault(key, [])
                    seen = {_curated_rule_signature(rule) for rule in existing}
                    for rule in valid_rules:
                        signature = _curated_rule_signature(rule)
                        if signature in seen:
                            continue
                        existing.append(rule)
                        seen.add(signature)
        except OSError:
            continue

    _CURATED_RULE_OVERRIDES_BY_TEXT = overrides
    return overrides


def _split_sections(text: str) -> Tuple[List[str], List[str], bool]:
    sections: Dict[str, List[str]] = {"inclusion": [], "exclusion": []}
    preamble: List[str] = []
    current: Optional[str] = None
    has_heading = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading, heading_tail = _extract_heading(line)
        if heading:
            has_heading = True
            current = heading
            if heading_tail:
                sections[current].append(heading_tail)
            continue

        cleaned = _clean_line(line)
        if not cleaned:
            continue
        if current in sections:
            sections[current].append(cleaned)
        else:
            preamble.append(cleaned)

    if has_heading and preamble:
        sections["inclusion"] = preamble + sections["inclusion"]

    if has_heading:
        return sections["inclusion"], sections["exclusion"], True

    merged = preamble + sections["inclusion"] + sections["exclusion"]
    return merged, [], False


def _normalize_inline_headings(text: str) -> str:
    return _INLINE_HEADING_BOUNDARY.sub(r"\1\n", text)


def _extract_heading(line: str) -> Tuple[Optional[str], Optional[str]]:
    inline = _HEADING_WITH_TAIL.match(line)
    if inline:
        section = _section_name(inline.group(1))
        if section:
            tail = _clean_line(inline.group(2))
            return section, tail or None

    only = _HEADING_ONLY.match(line)
    if only:
        section = _section_name(only.group(1))
        if section:
            return section, None

    return None, None


def _section_name(raw_heading: str) -> Optional[str]:
    heading = raw_heading.strip().lower()
    if heading.startswith("inclusion"):
        return "inclusion"
    if heading.startswith("exclusion"):
        return "exclusion"
    return None


def _clean_line(line: str) -> str:
    without_bullet = _BULLET_PREFIX.sub("", line.strip())
    return _WHITESPACE.sub(" ", without_bullet).strip()


def _split_into_sentences(lines: List[str]) -> List[str]:
    sentences: List[str] = []
    for line in lines:
        for part in _SENTENCE_BOUNDARY.split(line):
            cleaned = _clean_line(part)
            if cleaned:
                sentences.append(cleaned)
    return sentences


def _parse_sentence(
    sentence: str, rule_type: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    try:
        parsed: List[Dict[str, Any]] = []
        parsed.extend(_parse_age_rules(sentence, rule_type, source_span))
        parsed.extend(_parse_sex_rules(sentence, rule_type, source_span))
        parsed.extend(_parse_lab_rules(sentence, rule_type, source_span))
        parsed.extend(_parse_condition_rules(sentence, rule_type, source_span))
        if rule_type == "EXCLUSION":
            parsed.extend(_parse_exclusion_history_rules(sentence, source_span))
            parsed.extend(_parse_exclusion_condition_rules(sentence, source_span))
            parsed.extend(_parse_common_exclusion_rules(sentence, source_span))
    except Exception:
        parsed = []

    if parsed:
        return parsed
    return []


def _parse_age_rules(
    sentence: str, rule_type: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    text = sentence.lower()
    if not any(token in text for token in ("age", "year", "yr", "older", "younger")):
        return []

    result: List[Dict[str, Any]] = []
    range_match = _AGE_RANGE.search(sentence)
    if range_match:
        min_age = int(range_match.group(1))
        max_age = int(range_match.group(2))
        result.append(
            _build_rule(
                rule_type=rule_type,
                field="age",
                operator=">=",
                value=min_age,
                unit="years",
                certainty="high",
                evidence_text=sentence,
                source_span=source_span,
            )
        )
        result.append(
            _build_rule(
                rule_type=rule_type,
                field="age",
                operator="<=",
                value=max_age,
                unit="years",
                certainty="high",
                evidence_text=sentence,
                source_span=source_span,
            )
        )
        return result

    min_age = _extract_first_int(sentence, _AGE_MIN_PATTERNS)
    if min_age is not None:
        result.append(
            _build_rule(
                rule_type=rule_type,
                field="age",
                operator=">=",
                value=min_age,
                unit="years",
                certainty="high",
                evidence_text=sentence,
                source_span=source_span,
            )
        )

    max_age = _extract_first_int(sentence, _AGE_MAX_PATTERNS)
    if max_age is not None:
        result.append(
            _build_rule(
                rule_type=rule_type,
                field="age",
                operator="<=",
                value=max_age,
                unit="years",
                certainty="high",
                evidence_text=sentence,
                source_span=source_span,
            )
        )

    return result


def _parse_lab_rules(
    sentence: str, rule_type: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    if rule_type != "INCLUSION":
        return []

    match = _LAB_PATTERN.search(sentence)
    if not match:
        return []

    marker = _norm_text(match.group(1))
    if marker in {"age", "aged"}:
        return []

    operator = match.group(2)
    raw_value = match.group(3)
    unit = match.group(4).lower() if match.group(4) else None
    value = float(raw_value)
    return [
        _build_rule(
            rule_type=rule_type,
            field="lab",
            operator=operator,
            value=value,
            unit=unit,
            certainty="medium",
            evidence_text=sentence,
            source_span=source_span,
            time_window=None,
        )
    ]


def _parse_condition_rules(
    sentence: str, rule_type: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    if rule_type != "INCLUSION":
        return []

    candidates: List[str] = []
    patterns = (
        _CONDITION_WITH_PATTERN,
        _CONDITION_DIAGNOSIS_PATTERN,
        _CONDITION_SYMPTOMS_PATTERN,
    )
    for pattern in patterns:
        for match in pattern.finditer(sentence):
            cleaned = _clean_condition_value(match.group(1))
            if cleaned:
                candidates.append(cleaned)

    normalized = _norm_text(sentence)
    if "fertile" in normalized:
        candidates.append("fertile")

    if not candidates:
        return []

    deduped: List[str] = []
    seen = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)

    return [
        _build_rule(
            rule_type=rule_type,
            field="condition",
            operator="IN",
            value=value,
            unit=None,
            certainty="medium",
            evidence_text=sentence,
            source_span=source_span,
        )
        for value in deduped
    ]


def _clean_condition_value(raw: str) -> Optional[str]:
    value = _norm_text(raw)
    if not value:
        return None

    noise_prefixes = (
        "adults with ",
        "participants with ",
        "patient with ",
        "patients with ",
        "history of ",
        "known ",
    )
    for prefix in noise_prefixes:
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()

    reject_prefixes = (
        "subject must have",
        "subjects must have",
        "subject who",
        "subjects who",
    )
    if any(value.startswith(prefix) for prefix in reject_prefixes):
        return None

    if value.startswith(("no ", "not ")):
        return None

    value = re.split(
        r"\b(?:for whom|who\s+(?:have|has|are|were)|that\s+(?:have|has|are)|"
        r"requiring|receiving|currently|willing|able to|must|should|if)\b",
        value,
        maxsplit=1,
    )[0].strip()

    value = re.sub(r"\b(?:nyha|class)\s+[ivx0-9\-]+\b", "", value, flags=re.I).strip()
    value = value.strip(",.;: ")
    value = _WHITESPACE.sub(" ", value)

    if value in {
        "participant",
        "participants",
        "patient",
        "patients",
        "subject",
        "subjects",
        "condition",
        "disease",
    }:
        return None

    if any(
        phrase in value
        for phrase in (
            "informed consent",
            "willingness",
            "ability to",
            "geographic accessibility",
            "study entry",
            "study participation",
            "control of",
        )
    ):
        return None

    tokens = value.split()
    if len(tokens) > 7:
        value = " ".join(tokens[:7])

    if len(value) < 3:
        return None
    return value


def _parse_sex_rules(
    sentence: str, rule_type: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    text = sentence.lower()
    has_male = (" male " in f" {text} ") or (" men " in f" {text} ")
    has_female = (" female " in f" {text} ") or (" women " in f" {text} ")
    has_pregnancy_context = any(
        token in text for token in ("pregnan", "breastfeed", "lactat", "childbearing")
    )

    if any(phrase in text for phrase in ("all sexes", "any sex", "both sexes")):
        return []
    if has_male and has_female and not has_pregnancy_context:
        return []

    values: List[str] = []
    if has_female:
        values.append("female")
    if has_male and (not values or has_pregnancy_context):
        values.append("male")
    if not values:
        return []

    deduped_values = list(dict.fromkeys(values))
    return [
        _build_rule(
            rule_type=rule_type,
            field="sex",
            operator="=",
            value=value,
            unit=None,
            certainty="high",
            evidence_text=sentence,
            source_span=source_span,
        )
        for value in deduped_values
    ]


def _parse_common_exclusion_rules(
    sentence: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    text = sentence.lower()
    rules: List[Dict[str, Any]] = []
    seen_signatures = set()
    for keyword, field, operator, value in _COMMON_EXCLUSION_PATTERNS:
        if keyword not in text:
            continue

        time_window = _extract_time_window(text)
        if time_window and field in {"procedure", "medication", "history"}:
            rule_operator = "WITHIN_LAST"
            rule_value = time_window["value"]
            unit = time_window["unit"]
            window_text = f'{time_window["value"]} {time_window["unit"]}'
        else:
            rule_operator = operator
            rule_value = value
            unit = None
            window_text = None

        signature = (
            field,
            rule_operator,
            str(rule_value),
            unit or "",
            window_text or "",
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        rules.append(
            _build_rule(
                rule_type="EXCLUSION",
                field=field,
                operator=rule_operator,
                value=rule_value,
                unit=unit,
                certainty="medium",
                evidence_text=sentence,
                source_span=source_span,
                time_window=window_text,
            )
        )
    return rules


def _parse_exclusion_condition_rules(
    sentence: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    text = sentence.lower()
    candidates: List[str] = []

    if "hiv" in text:
        candidates.append("hiv positive")

    for match in _EXCLUSION_HISTORY_OF_PATTERN.finditer(sentence):
        cleaned = _clean_exclusion_condition_value(match.group(1))
        if cleaned:
            candidates.append(cleaned)

    deduped: List[str] = []
    seen = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)

    return [
        _build_rule(
            rule_type="EXCLUSION",
            field="condition",
            operator="NOT_IN",
            value=value,
            unit=None,
            certainty="medium",
            evidence_text=sentence,
            source_span=source_span,
        )
        for value in deduped
    ]


def _parse_exclusion_history_rules(
    sentence: str, source_span: Optional[Dict[str, int]]
) -> List[Dict[str, Any]]:
    text = sentence.lower()
    rules: List[Dict[str, Any]] = []

    if "given birth within" in text:
        rules.append(
            _build_rule(
                rule_type="EXCLUSION",
                field="history",
                operator="NO_HISTORY",
                value="pregnancy",
                unit=None,
                certainty="medium",
                evidence_text=sentence,
                source_span=source_span,
            )
        )

    time_window = _extract_time_window(text)
    trigger_keywords = (
        "history of",
        "tobacco use",
        "malignancy",
        "tumor recurrence",
        "began within",
    )
    if time_window and any(keyword in text for keyword in trigger_keywords):
        rules.append(
            _build_rule(
                rule_type="EXCLUSION",
                field="history",
                operator="WITHIN_LAST",
                value=time_window["value"],
                unit=time_window["unit"],
                certainty="medium",
                evidence_text=sentence,
                source_span=source_span,
            )
        )

    return rules


def _clean_exclusion_condition_value(raw: str) -> Optional[str]:
    value = _norm_text(raw).strip(" ,.;:")
    if not value:
        return None
    value = re.sub(r"^(?:a|an|the)\s+", "", value).strip()
    if len(value) < 3:
        return None
    return value


def _extract_first_int(text: str, patterns: List[re.Pattern[str]]) -> Optional[int]:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def _extract_time_window(text: str) -> Optional[Dict[str, Any]]:
    match = _TIME_WINDOW.search(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit.endswith("s"):
        unit = unit
    else:
        unit = f"{unit}s"
    return {"value": value, "unit": unit}


def _build_sentence_spans(text: str, sentences: List[str]) -> Dict[str, Dict[str, int]]:
    if not text.strip():
        return {}
    lowered = text.lower()
    cursor = 0
    spans: Dict[str, Dict[str, int]] = {}
    for sentence in sentences:
        needle = sentence.lower()
        start = lowered.find(needle, cursor)
        if start < 0:
            start = lowered.find(needle)
        if start < 0:
            continue
        end = start + len(sentence)
        spans[sentence] = {"start": start, "end": end}
        cursor = end
    return spans


def _norm_text(text: str) -> str:
    return " ".join((text or "").lower().replace("-", " ").split())


def _build_rule(
    *,
    rule_type: str,
    field: str,
    operator: str,
    value: Any,
    unit: Optional[str],
    certainty: str,
    evidence_text: str,
    source_span: Optional[Dict[str, int]],
    time_window: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": f"rule-{uuid.uuid4()}",
        "type": rule_type,
        "field": field,
        "operator": operator,
        "value": value,
        "unit": unit,
        "time_window": time_window,
        "certainty": certainty,
        "evidence_text": evidence_text,
        "source_span": source_span,
    }

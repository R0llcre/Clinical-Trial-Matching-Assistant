from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

PASS_SCORE = 1.0
UNKNOWN_SCORE = 0.3
FAIL_SCORE = -2.0

_AGE_PATTERN = re.compile(
    r"^\s*(\d+)\s*(year|years|month|months|week|weeks|day|days)\s*$",
    re.I,
)


def _extract_eligibility(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    eligibility = (
        raw_json.get("protocolSection", {})
        .get("eligibilityModule", {})
    )
    return {
        "minimum_age": _parse_age_to_years(eligibility.get("minimumAge")),
        "maximum_age": _parse_age_to_years(eligibility.get("maximumAge")),
        "sex": (eligibility.get("sex") or "ALL"),
    }


def _parse_age_to_years(value: Optional[str]) -> Optional[float]:
    if not value or not isinstance(value, str):
        return None
    match = _AGE_PATTERN.match(value)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("year"):
        return amount
    if unit.startswith("month"):
        return amount / 12.0
    if unit.startswith("week"):
        return amount / 52.0
    return amount / 365.0


def _rule(verdict: str, rule_id: str, evidence: str) -> Dict[str, str]:
    return {"rule_id": rule_id, "verdict": verdict, "evidence": evidence}


def _summarize_match(
    inclusion: List[Dict[str, str]],
    exclusion: List[Dict[str, str]],
    missing_info: List[str],
) -> Dict[str, Any]:
    all_rules = inclusion + exclusion
    pass_count = sum(1 for rule in all_rules if rule.get("verdict") == "PASS")
    fail_count = sum(1 for rule in all_rules if rule.get("verdict") == "FAIL")
    unknown_count = sum(
        1 for rule in all_rules if rule.get("verdict") not in {"PASS", "FAIL"}
    )
    missing_count = len(set(missing_info))

    if fail_count > 0:
        tier = "INELIGIBLE"
    elif unknown_count > 0 or missing_count > 0:
        tier = "POTENTIAL"
    else:
        tier = "ELIGIBLE"

    return {
        "tier": tier,
        "pass": pass_count,
        "fail": fail_count,
        "unknown": unknown_count,
        "missing": missing_count,
    }


def _score_from_rules(rules: List[Dict[str, str]]) -> float:
    score = 0.0
    for rule in rules:
        verdict = rule["verdict"]
        if verdict == "PASS":
            score += PASS_SCORE
        elif verdict == "UNKNOWN":
            score += UNKNOWN_SCORE
        else:
            score += FAIL_SCORE
    return score


def _norm_text_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    for value in values:
        if isinstance(value, str) and value.strip():
            normalized.append(value.strip().lower())
    return normalized


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _evaluate_condition_overlap_rule(
    patient_profile: Dict[str, Any], trial: Dict[str, Any]
) -> Tuple[Dict[str, str], Optional[str]]:
    patient_conditions = _norm_text_list(patient_profile.get("conditions"))
    trial_conditions = _norm_text_list(trial.get("conditions"))

    if not patient_conditions:
        return (
            _rule("UNKNOWN", "condition_match", "patient conditions are missing"),
            "conditions",
        )
    if not trial_conditions:
        return _rule("UNKNOWN", "condition_match", "trial conditions are missing"), None

    condition_pass = any(
        (pc in tc) or (tc in pc) or bool(_tokenize(pc) & _tokenize(tc))
        for pc in patient_conditions
        for tc in trial_conditions
    )
    verdict = "PASS" if condition_pass else "FAIL"
    return _rule(verdict, "condition_match", "condition overlap check"), None


def evaluate_trial(
    patient_profile: Dict[str, Any], trial: Dict[str, Any]
) -> Dict[str, Any]:
    parsed_rules = trial.get("criteria_json")
    if isinstance(parsed_rules, list) and parsed_rules:
        return _evaluate_trial_with_parsed_rules(patient_profile, trial, parsed_rules)
    return _evaluate_trial_legacy(patient_profile, trial)


def _evaluate_trial_with_parsed_rules(
    patient_profile: Dict[str, Any],
    trial: Dict[str, Any],
    parsed_rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    inclusion: List[Dict[str, str]] = []
    exclusion: List[Dict[str, str]] = []
    missing_info: List[str] = []
    has_parsed_condition = any(
        str(rule.get("type")).upper() == "INCLUSION"
        and str(rule.get("field")).lower() == "condition"
        for rule in parsed_rules
    )

    if not has_parsed_condition:
        condition_rule, missing_field = _evaluate_condition_overlap_rule(
            patient_profile, trial
        )
        inclusion.append(condition_rule)
        if missing_field:
            missing_info.append(missing_field)

    for parsed_rule in parsed_rules:
        verdict, missing_field = _evaluate_parsed_rule(parsed_rule, patient_profile)
        fallback_id = f"rule-{len(inclusion) + len(exclusion)}"
        rule_id = str(parsed_rule.get("id") or fallback_id)
        evidence = str(parsed_rule.get("evidence_text") or "criteria rule")
        checklist_rule = _rule(verdict, rule_id, evidence)
        if missing_field:
            missing_info.append(missing_field)
        if str(parsed_rule.get("type")).upper() == "EXCLUSION":
            exclusion.append(checklist_rule)
        else:
            inclusion.append(checklist_rule)

    all_rules = inclusion + exclusion
    pass_count = sum(1 for rule in all_rules if rule["verdict"] == "PASS")
    certainty = pass_count / len(all_rules) if all_rules else 0.0

    score = _score_from_rules(all_rules)
    hard_fail_ids = {
        str(rule.get("id"))
        for rule in parsed_rules
        if str(rule.get("type")).upper() == "EXCLUSION"
        and str(rule.get("field")).lower() in {"age", "sex"}
    }
    hard_fail = any(
        rule["rule_id"] in hard_fail_ids and rule["verdict"] == "FAIL"
        for rule in exclusion
    )
    if hard_fail:
        score -= 100.0

    fetched_at = _parse_fetched_at(trial.get("fetched_at"))
    return {
        "nct_id": trial.get("nct_id"),
        "title": trial.get("title"),
        "status": trial.get("status"),
        "phase": trial.get("phase"),
        "score": round(score, 4),
        "certainty": round(certainty, 4),
        "match_summary": _summarize_match(inclusion, exclusion, missing_info),
        "checklist": {
            "inclusion": inclusion,
            "exclusion": exclusion,
            "missing_info": sorted(set(missing_info)),
        },
        "_sort_fetched_at": fetched_at,
    }


def _evaluate_parsed_rule(
    rule: Dict[str, Any], patient_profile: Dict[str, Any]
) -> Tuple[str, Optional[str]]:
    field = str(rule.get("field") or "").lower()
    operator = str(rule.get("operator") or "").upper()
    value = rule.get("value")

    demographics = patient_profile.get("demographics")
    if not isinstance(demographics, dict):
        demographics = {}

    if field == "age":
        patient_age = demographics.get("age")
        if isinstance(patient_age, bool) or not isinstance(patient_age, (int, float)):
            return "UNKNOWN", "demographics.age"
        target = _to_number(value)
        if target is None:
            return "UNKNOWN", None
        if operator == ">=":
            return ("PASS", None) if float(patient_age) >= target else ("FAIL", None)
        if operator == "<=":
            return ("PASS", None) if float(patient_age) <= target else ("FAIL", None)
        if operator == "=":
            return ("PASS", None) if float(patient_age) == target else ("FAIL", None)
        return "UNKNOWN", None

    if field == "sex":
        patient_sex = demographics.get("sex")
        if not isinstance(patient_sex, str) or not patient_sex.strip():
            return "UNKNOWN", "demographics.sex"
        patient_sex_norm = patient_sex.strip().lower()
        target = str(value or "").strip().lower()
        if target in {"all", "any", ""}:
            return "PASS", None
        return ("PASS", None) if patient_sex_norm == target else ("FAIL", None)

    if field == "condition":
        patient_conditions = _norm_text_list(patient_profile.get("conditions"))
        if not patient_conditions:
            return "UNKNOWN", "conditions"
        if isinstance(value, list):
            terms = _norm_text_list(value)
        else:
            terms = [str(value or "").lower()]
        terms = [term for term in terms if term]
        if not terms:
            return "UNKNOWN", None
        hit = any(
            any(
                (term in condition)
                or (condition in term)
                or bool(_tokenize(term) & _tokenize(condition))
                for term in terms
            )
            for condition in patient_conditions
        )
        if operator in {"IN", "="}:
            return ("PASS", None) if hit else ("FAIL", None)
        if operator == "NOT_IN":
            return ("FAIL", None) if hit else ("PASS", None)
        return "UNKNOWN", None

    if field in {"history", "procedure", "medication"}:
        profile_key = {
            "history": "history",
            "procedure": "procedures",
            "medication": "medications",
        }[field]
        values = _norm_text_list(patient_profile.get(profile_key))
        if not values:
            return "UNKNOWN", profile_key
        value_text = str(value or "").lower()
        found = any(
            value_text and (value_text in item or item in value_text)
            for item in values
        )
        if operator in {"NO_HISTORY", "NOT_EXISTS"}:
            return ("FAIL", None) if found else ("PASS", None)
        if operator == "EXISTS":
            return ("PASS", None) if found else ("FAIL", None)
        if operator == "WITHIN_LAST":
            # Time granularity is unavailable in MVP patient profile fields.
            return "UNKNOWN", profile_key
        return "UNKNOWN", None

    return "UNKNOWN", None


def _to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_fetched_at(value: Any) -> dt.datetime:
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError:
            return dt.datetime.min
    if isinstance(value, dt.datetime):
        return value
    return dt.datetime.min


def _evaluate_trial_legacy(
    patient_profile: Dict[str, Any], trial: Dict[str, Any]
) -> Dict[str, Any]:
    demographics = patient_profile.get("demographics")
    if not isinstance(demographics, dict):
        demographics = {}

    patient_age = demographics.get("age")
    if isinstance(patient_age, bool) or not isinstance(patient_age, (int, float)):
        patient_age = None
    patient_sex = demographics.get("sex")
    if isinstance(patient_sex, str):
        patient_sex = patient_sex.strip().lower()
    else:
        patient_sex = None

    missing_info: List[str] = []
    inclusion: List[Dict[str, str]] = []
    exclusion: List[Dict[str, str]] = []

    condition_rule, missing_condition = _evaluate_condition_overlap_rule(
        patient_profile, trial
    )
    inclusion.append(condition_rule)
    if missing_condition:
        missing_info.append(missing_condition)

    eligibility = _extract_eligibility(trial.get("raw_json") or {})
    minimum_age = eligibility["minimum_age"]
    maximum_age = eligibility["maximum_age"]

    if patient_age is None:
        missing_info.append("demographics.age")
        exclusion.append(_rule("UNKNOWN", "age", "patient age is missing"))
    else:
        age_fail = (
            (minimum_age is not None and patient_age < minimum_age)
            or (maximum_age is not None and patient_age > maximum_age)
        )
        age_verdict = "FAIL" if age_fail else "PASS"
        exclusion.append(
            _rule(
                age_verdict,
                "age",
                f"patient age {patient_age}, trial range {minimum_age} - {maximum_age}",
            )
        )

    trial_sex = str(eligibility["sex"]).strip().lower()
    if not patient_sex:
        missing_info.append("demographics.sex")
        exclusion.append(_rule("UNKNOWN", "sex", "patient sex is missing"))
    elif trial_sex in {"all", "none", ""}:
        exclusion.append(_rule("PASS", "sex", "trial accepts all sexes"))
    elif patient_sex == trial_sex:
        exclusion.append(_rule("PASS", "sex", "patient sex matches trial requirement"))
    else:
        exclusion.append(
            _rule(
                "FAIL",
                "sex",
                f"patient sex {patient_sex} does not match trial sex {trial_sex}",
            )
        )

    all_rules = inclusion + exclusion
    pass_count = sum(1 for rule in all_rules if rule["verdict"] == "PASS")
    certainty = pass_count / len(all_rules) if all_rules else 0.0

    score = _score_from_rules(all_rules)
    hard_fail = any(
        rule["rule_id"] in {"age", "sex"} and rule["verdict"] == "FAIL"
        for rule in exclusion
    )
    if hard_fail:
        score -= 100.0

    fetched_at = _parse_fetched_at(trial.get("fetched_at"))

    return {
        "nct_id": trial.get("nct_id"),
        "title": trial.get("title"),
        "status": trial.get("status"),
        "phase": trial.get("phase"),
        "score": round(score, 4),
        "certainty": round(certainty, 4),
        "match_summary": _summarize_match(inclusion, exclusion, missing_info),
        "checklist": {
            "inclusion": inclusion,
            "exclusion": exclusion,
            "missing_info": sorted(set(missing_info)),
        },
        "_sort_fetched_at": fetched_at,
    }


def _contains_term(term: str, trial: Dict[str, Any]) -> bool:
    term_lower = term.strip().lower()
    if not term_lower:
        return True
    title = str(trial.get("title") or "").lower()
    if term_lower in title:
        return True
    conditions = _norm_text_list(trial.get("conditions"))
    return any(term_lower in condition for condition in conditions)


def _load_trial_candidates(
    engine: Engine, recall_limit: int = 500
) -> List[Dict[str, Any]]:
    stmt = text(
        """
        SELECT
          t.nct_id,
          t.title,
          t.status,
          t.phase,
          t.conditions,
          t.raw_json,
          t.fetched_at,
          tc.criteria_json
        FROM trials AS t
        LEFT JOIN LATERAL (
          SELECT criteria_json
          FROM trial_criteria
          WHERE trial_id = t.id
          ORDER BY created_at DESC
          LIMIT 1
        ) AS tc ON TRUE
        ORDER BY t.fetched_at DESC
        LIMIT :limit
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt, {"limit": recall_limit}).mappings().all()
    return [dict(row) for row in rows]


def match_trials(
    engine: Engine,
    patient_profile: Dict[str, Any],
    *,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    filters = filters or {}
    condition_filter = str(filters.get("condition") or "").strip()
    status_filter = str(filters.get("status") or "").strip()
    phase_filter = str(filters.get("phase") or "").strip()

    candidates = _load_trial_candidates(engine)
    filtered: List[Dict[str, Any]] = []
    for trial in candidates:
        if condition_filter and not _contains_term(condition_filter, trial):
            continue
        if status_filter and str(trial.get("status") or "") != status_filter:
            continue
        if phase_filter and str(trial.get("phase") or "") != phase_filter:
            continue
        filtered.append(trial)

    results = [evaluate_trial(patient_profile, trial) for trial in filtered]
    results.sort(
        key=lambda item: (
            item["score"],
            item["certainty"],
            item["_sort_fetched_at"],
        ),
        reverse=True,
    )

    clipped = results[:top_k]
    for item in clipped:
        item.pop("_sort_fetched_at", None)
    return clipped

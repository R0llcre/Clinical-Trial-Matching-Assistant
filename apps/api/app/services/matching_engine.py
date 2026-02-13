from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

PASS_SCORE = 1.0
UNKNOWN_SCORE = 0.3
FAIL_SCORE = -2.0
_MIN_RULES_FOR_STRONG_TIER = 8
_MIN_NON_DEMOGRAPHIC_RULES_FOR_STRONG_TIER = 4
_STRONG_EVIDENCE_FIELDS = {"history", "procedure", "medication", "lab"}

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


def _rule(
    verdict: str,
    rule_id: str,
    evidence: str,
    *,
    rule_meta: Optional[Dict[str, Any]] = None,
    evaluation_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rule: Dict[str, Any] = {
        "rule_id": rule_id,
        "verdict": verdict,
        "evidence": evidence,
    }
    if rule_meta is not None:
        rule["rule_meta"] = rule_meta
    if evaluation_meta is not None:
        rule["evaluation_meta"] = evaluation_meta
    return rule


def _parsed_rule_meta(parsed_rule: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": str(parsed_rule.get("type") or "").upper() or None,
        "field": str(parsed_rule.get("field") or "").lower() or None,
        "operator": str(parsed_rule.get("operator") or "").upper() or None,
        "value": parsed_rule.get("value"),
        "unit": parsed_rule.get("unit"),
        "time_window": parsed_rule.get("time_window"),
        "certainty": parsed_rule.get("certainty"),
    }


def _evaluation_meta(
    *,
    missing_field: Optional[str] = None,
    reason: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not missing_field and not reason:
        return None
    return {"missing_field": missing_field, "reason": reason}


def _summarize_match(
    inclusion: List[Dict[str, Any]],
    exclusion: List[Dict[str, Any]],
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


def _score_from_rules(rules: List[Dict[str, Any]]) -> float:
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
) -> Tuple[Dict[str, Any], Optional[str]]:
    patient_conditions = _norm_text_list(patient_profile.get("conditions"))
    trial_conditions = _norm_text_list(trial.get("conditions"))
    condition_meta = {
        "type": "INCLUSION",
        "field": "condition",
        "operator": "IN",
        "value": trial.get("conditions"),
        "unit": None,
        "time_window": None,
        "certainty": "medium",
    }

    if not patient_conditions:
        return (
            _rule(
                "UNKNOWN",
                "condition_match",
                "patient conditions are missing",
                rule_meta=condition_meta,
                evaluation_meta=_evaluation_meta(
                    missing_field="conditions",
                    reason="patient conditions are missing",
                ),
            ),
            "conditions",
        )
    if not trial_conditions:
        return (
            _rule(
                "UNKNOWN",
                "condition_match",
                "trial conditions are missing",
                rule_meta=condition_meta,
                evaluation_meta=_evaluation_meta(reason="trial conditions are missing"),
            ),
            None,
        )

    condition_pass = any(
        (pc in tc) or (tc in pc) or bool(_tokenize(pc) & _tokenize(tc))
        for pc in patient_conditions
        for tc in trial_conditions
    )
    verdict = "PASS" if condition_pass else "FAIL"
    return (
        _rule(
            verdict,
            "condition_match",
            "condition overlap check",
            rule_meta=condition_meta,
        ),
        None,
    )


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
    inclusion: List[Dict[str, Any]] = []
    exclusion: List[Dict[str, Any]] = []
    missing_info: List[str] = []
    condition_overlap_verdict: Optional[str] = None
    parsed_condition_inclusion_pass = False
    non_demographic_pass_count = 0
    non_demographic_pass_fields: set[str] = set()
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
        condition_overlap_verdict = condition_rule.get("verdict")
        if missing_field:
            missing_info.append(missing_field)

    for parsed_rule in parsed_rules:
        rule_type = str(parsed_rule.get("type") or "").upper()
        rule_field = str(parsed_rule.get("field") or "").lower()
        verdict, missing_field = _evaluate_parsed_rule(parsed_rule, patient_profile)
        if verdict == "PASS":
            if rule_type == "INCLUSION" and rule_field == "condition":
                parsed_condition_inclusion_pass = True
            if rule_field and rule_field not in {"age", "sex"}:
                non_demographic_pass_count += 1
                non_demographic_pass_fields.add(rule_field)
        fallback_id = f"rule-{len(inclusion) + len(exclusion)}"
        rule_id = str(parsed_rule.get("id") or fallback_id)
        evidence = str(parsed_rule.get("evidence_text") or "criteria rule")
        checklist_rule = _rule(
            verdict,
            rule_id,
            evidence,
            rule_meta=_parsed_rule_meta(parsed_rule),
            evaluation_meta=_evaluation_meta(
                missing_field=missing_field,
                reason=(
                    "missing required patient field" if missing_field else None
                ),
            ),
        )
        if missing_field:
            missing_info.append(missing_field)
        if rule_type == "EXCLUSION":
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
    match_summary = _summarize_match(inclusion, exclusion, missing_info)
    # Even if everything "passes", a tiny evaluated rule set is not enough
    # evidence to claim a definitive strong match.
    if (
        match_summary.get("tier") == "ELIGIBLE"
        and len(all_rules) < _MIN_RULES_FOR_STRONG_TIER
    ):
        match_summary["tier"] = "POTENTIAL"
    # Additionally, only label a match as "ELIGIBLE" when we have non-demographic
    # evidence beyond just demographics/condition overlap.
    if match_summary.get("tier") == "ELIGIBLE":
        condition_ok = (
            parsed_condition_inclusion_pass
            if has_parsed_condition
            else condition_overlap_verdict == "PASS"
        )
        if not condition_ok:
            match_summary["tier"] = "POTENTIAL"
        elif non_demographic_pass_count < _MIN_NON_DEMOGRAPHIC_RULES_FOR_STRONG_TIER:
            match_summary["tier"] = "POTENTIAL"
        elif not (non_demographic_pass_fields & _STRONG_EVIDENCE_FIELDS):
            match_summary["tier"] = "POTENTIAL"
    return {
        "nct_id": trial.get("nct_id"),
        "title": trial.get("title"),
        "status": trial.get("status"),
        "phase": trial.get("phase"),
        "score": round(score, 4),
        "certainty": round(certainty, 4),
        "match_summary": match_summary,
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
    inclusion: List[Dict[str, Any]] = []
    exclusion: List[Dict[str, Any]] = []

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
        exclusion.append(
            _rule(
                "UNKNOWN",
                "age",
                "patient age is missing",
                rule_meta={
                    "type": "EXCLUSION",
                    "field": "age",
                    "operator": "RANGE",
                    "value": {"min": minimum_age, "max": maximum_age},
                    "unit": "years",
                    "time_window": None,
                    "certainty": "low",
                },
                evaluation_meta=_evaluation_meta(
                    missing_field="demographics.age",
                    reason="patient age is missing",
                ),
            )
        )
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
                rule_meta={
                    "type": "EXCLUSION",
                    "field": "age",
                    "operator": "RANGE",
                    "value": {"min": minimum_age, "max": maximum_age},
                    "unit": "years",
                    "time_window": None,
                    "certainty": "high",
                },
            )
        )

    trial_sex = str(eligibility["sex"]).strip().lower()
    if not patient_sex:
        missing_info.append("demographics.sex")
        exclusion.append(
            _rule(
                "UNKNOWN",
                "sex",
                "patient sex is missing",
                rule_meta={
                    "type": "EXCLUSION",
                    "field": "sex",
                    "operator": "=",
                    "value": trial_sex,
                    "unit": None,
                    "time_window": None,
                    "certainty": "low",
                },
                evaluation_meta=_evaluation_meta(
                    missing_field="demographics.sex",
                    reason="patient sex is missing",
                ),
            )
        )
    elif trial_sex in {"all", "none", ""}:
        exclusion.append(
            _rule(
                "PASS",
                "sex",
                "trial accepts all sexes",
                rule_meta={
                    "type": "EXCLUSION",
                    "field": "sex",
                    "operator": "=",
                    "value": "all",
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                },
            )
        )
    elif patient_sex == trial_sex:
        exclusion.append(
            _rule(
                "PASS",
                "sex",
                "patient sex matches trial requirement",
                rule_meta={
                    "type": "EXCLUSION",
                    "field": "sex",
                    "operator": "=",
                    "value": trial_sex,
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                },
            )
        )
    else:
        exclusion.append(
            _rule(
                "FAIL",
                "sex",
                f"patient sex {patient_sex} does not match trial sex {trial_sex}",
                rule_meta={
                    "type": "EXCLUSION",
                    "field": "sex",
                    "operator": "=",
                    "value": trial_sex,
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                },
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

    match_summary = _summarize_match(inclusion, exclusion, missing_info)
    # Legacy matching only evaluates condition overlap + structured age/sex fields.
    # Even when those pass, we still lack most eligibility criteria coverage, so
    # we surface it as "POTENTIAL" rather than a definitive "ELIGIBLE".
    if match_summary.get("tier") == "ELIGIBLE":
        match_summary["tier"] = "POTENTIAL"

    return {
        "nct_id": trial.get("nct_id"),
        "title": trial.get("title"),
        "status": trial.get("status"),
        "phase": trial.get("phase"),
        "score": round(score, 4),
        "certainty": round(certainty, 4),
        "match_summary": match_summary,
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
    engine: Engine,
    *,
    condition_filter: str = "",
    status_filter: str = "",
    phase_filter: str = "",
    recall_limit: int = 500,
) -> List[Dict[str, Any]]:
    filters = []
    params: Dict[str, Any] = {"limit": recall_limit}

    if condition_filter:
        like = f"%{condition_filter}%"
        params["condition_like"] = like
        # Match /api/trials search semantics so Browse/Match don't diverge.
        filters.append(
            "("
            "t.title ILIKE :condition_like OR "
            "array_to_string(t.conditions, ',') ILIKE :condition_like"
            ")"
        )
    if status_filter:
        params["status"] = status_filter
        filters.append("t.status = :status")
    if phase_filter:
        params["phase"] = phase_filter
        filters.append("t.phase = :phase")

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    stmt = text(
        f"""
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
        {where_clause}
        ORDER BY t.fetched_at DESC
        LIMIT :limit
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt, params).mappings().all()
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

    candidates = _load_trial_candidates(
        engine,
        condition_filter=condition_filter,
        status_filter=status_filter,
        phase_filter=phase_filter,
    )
    results = [evaluate_trial(patient_profile, trial) for trial in candidates]
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

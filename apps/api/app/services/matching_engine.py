from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional

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


def evaluate_trial(
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

    patient_conditions = _norm_text_list(patient_profile.get("conditions"))
    trial_conditions = _norm_text_list(trial.get("conditions"))

    missing_info: List[str] = []
    inclusion: List[Dict[str, str]] = []
    exclusion: List[Dict[str, str]] = []

    if not patient_conditions:
        missing_info.append("conditions")
        inclusion.append(
            _rule("UNKNOWN", "condition_match", "patient conditions are missing")
        )
    elif not trial_conditions:
        inclusion.append(
            _rule("UNKNOWN", "condition_match", "trial conditions are missing")
        )
    else:
        condition_pass = any(
            (pc in tc) or (tc in pc)
            or bool(_tokenize(pc) & _tokenize(tc))
            for pc in patient_conditions
            for tc in trial_conditions
        )
        verdict = "PASS" if condition_pass else "FAIL"
        inclusion.append(_rule(verdict, "condition_match", "condition overlap check"))

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

    fetched_at = trial.get("fetched_at")
    if isinstance(fetched_at, str):
        try:
            fetched_at = dt.datetime.fromisoformat(fetched_at)
        except ValueError:
            fetched_at = dt.datetime.min
    elif not isinstance(fetched_at, dt.datetime):
        fetched_at = dt.datetime.min

    return {
        "nct_id": trial.get("nct_id"),
        "title": trial.get("title"),
        "status": trial.get("status"),
        "phase": trial.get("phase"),
        "score": round(score, 4),
        "certainty": round(certainty, 4),
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
        SELECT nct_id, title, status, phase, conditions, raw_json, fetched_at
        FROM trials
        ORDER BY fetched_at DESC
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

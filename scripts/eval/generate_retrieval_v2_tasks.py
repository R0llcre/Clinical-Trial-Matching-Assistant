#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

DEFAULT_BASE_URL = "https://clinicaltrials.gov/api/v2"
DEFAULT_EXCLUDE_FILES = [
    "eval/annotations/relevance.annotator_a.jsonl",
    "eval/annotations/relevance.annotator_b.jsonl",
    "eval/annotations/relevance.batch1.annotator_b.jsonl",
    "eval/annotations/relevance.batch2.annotator_b.jsonl",
    "eval/annotations/relevance.batch3.annotator_b.jsonl",
    "eval/annotations/relevance.batch4.annotator_b.jsonl",
]
QUERY_SYNONYMS = {
    "type 2 diabetes": [
        "diabetes mellitus type 2",
        "type ii diabetes",
        "t2d",
    ],
    "metastatic breast cancer": [
        "advanced breast cancer",
        "stage iv breast cancer",
    ],
    "heart failure": [
        "congestive heart failure",
        "cardiac failure",
    ],
    "asthma": [
        "pediatric asthma",
        "childhood asthma",
    ],
    "rheumatoid arthritis": [
        "ra disease",
        "arthritis rheumatoid",
    ],
    "melanoma": [
        "advanced melanoma",
        "metastatic melanoma",
    ],
    "long covid": [
        "post covid syndrome",
        "post acute covid",
        "long haul covid",
    ],
    "chronic kidney disease": [
        "ckd",
        "chronic renal disease",
    ],
    "ulcerative colitis": [
        "inflammatory bowel disease ulcerative colitis",
        "uc disease",
    ],
    "migraine": [
        "chronic migraine",
        "migraine prevention",
    ],
}

COUNTRY_ALIASES = {
    "us": "united states",
    "usa": "united states",
    "u s": "united states",
    "u s a": "united states",
    "united states": "united states",
    "united states of america": "united states",
}

STATE_ALIASES = {
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "dc": "district of columbia",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "new hampshire",
    "nj": "new jersey",
    "nm": "new mexico",
    "ny": "new york",
    "nc": "north carolina",
    "nd": "north dakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhode island",
    "sc": "south carolina",
    "sd": "south dakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "west virginia",
    "wi": "wisconsin",
    "wy": "wyoming",
}

INTENT_QUERY_MARKERS = {
    "female": ("women", "woman", "female"),
    "pediatric": ("pediatric", "paediatric", "child", "children", "adolescent"),
    "biologic": ("biologic", "biological"),
    "immunotherapy": ("immunotherapy", "checkpoint", "pd 1", "pdl1", "ctla 4"),
    "prevention": ("prevention", "preventive", "prophylaxis", "prophylactic"),
}

INTENT_LEXICONS = {
    "female": (
        "female",
        "women",
        "woman",
        "girl",
        "girls",
    ),
    "pediatric": (
        "pediatric",
        "paediatric",
        "child",
        "children",
        "adolescent",
        "adolescents",
        "teen",
        "teens",
    ),
    "biologic": (
        "biologic",
        "biological",
        "monoclonal",
        "antibody",
        "adalimumab",
        "infliximab",
        "etanercept",
        "rituximab",
        "tocilizumab",
        "abatacept",
        "ustekinumab",
        "secukinumab",
    ),
    "immunotherapy": (
        "immunotherapy",
        "checkpoint",
        "pd 1",
        "pd l1",
        "pdl1",
        "ctla 4",
        "pembrolizumab",
        "nivolumab",
        "atezolizumab",
        "durvalumab",
        "ipilimumab",
        "cemiplimab",
    ),
    "prevention": (
        "prevention",
        "preventive",
        "prophylaxis",
        "prophylactic",
    ),
}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_no} row must be a JSON object")
            rows.append(payload)
    return rows


def dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm_text(text: str) -> str:
    return " ".join((text or "").lower().replace("-", " ").split())


def _tokenize(text: str) -> set[str]:
    return {token for token in _norm_text(text).split() if len(token) > 2}


def _normalize_country(text: str) -> str:
    token = _norm_text(text)
    return COUNTRY_ALIASES.get(token, token)


def _normalize_state(text: str) -> str:
    token = _norm_text(text)
    return STATE_ALIASES.get(token, token)


def _has_expected_location(expected_location: Dict[str, Any]) -> bool:
    if not isinstance(expected_location, dict):
        return False
    return any(
        str(expected_location.get(field) or "").strip()
        for field in ("country", "state", "city")
    )


def _extract_query_intents(query: Dict[str, Any]) -> List[str]:
    query_text = _norm_text(str(query.get("query") or ""))
    intents: List[str] = []
    for intent, markers in INTENT_QUERY_MARKERS.items():
        if any(_norm_text(marker) in query_text for marker in markers):
            intents.append(intent)
    return intents


def _contains_token_or_phrase(
    *,
    keyword: str,
    text_norm: str,
    tokens: set[str],
) -> bool:
    normalized = _norm_text(keyword)
    if not normalized:
        return False
    if " " in normalized:
        return normalized in text_norm
    return normalized in tokens


def _intent_match_count(
    intent_targets: Sequence[str],
    *,
    trial_text_norm: str,
    trial_tokens: set[str],
) -> int:
    matched = 0
    for intent in intent_targets:
        lexicon = INTENT_LEXICONS.get(intent, ())
        if any(
            _contains_token_or_phrase(
                keyword=keyword,
                text_norm=trial_text_norm,
                tokens=trial_tokens,
            )
            for keyword in lexicon
        ):
            matched += 1
    return matched


def _get_nested(raw: Dict[str, Any], path: Sequence[str]) -> Any:
    cursor: Any = raw
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def build_search_terms(query: Dict[str, Any]) -> List[str]:
    expected_conditions = [
        item.strip()
        for item in (query.get("expected_conditions") or [])
        if isinstance(item, str) and item.strip()
    ]
    query_text = str(query.get("query") or "").strip()
    expected_status = str(query.get("expected_status") or "").strip()
    expected_phase = str(query.get("expected_phase") or "").strip()

    terms: List[str] = []
    if query_text:
        terms.append(query_text)
    terms.extend(expected_conditions)

    for condition in expected_conditions:
        terms.extend(QUERY_SYNONYMS.get(_norm_text(condition), []))
        if expected_phase:
            terms.append(f"{condition} {expected_phase.lower()}")
        if expected_status:
            terms.append(f"{condition} {expected_status.lower()}")

    deduped: List[str] = []
    seen = set()
    for term in terms:
        normalized = _norm_text(term)
        if not normalized or normalized in seen:
            continue
        deduped.append(term.strip())
        seen.add(normalized)
    return deduped


def _extract_study_summary(study: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    nct_id = _get_nested(study, ("protocolSection", "identificationModule", "nctId"))
    if not isinstance(nct_id, str) or not nct_id.strip():
        return None

    brief_title = _get_nested(study, ("protocolSection", "identificationModule", "briefTitle"))
    official_title = _get_nested(
        study, ("protocolSection", "identificationModule", "officialTitle")
    )
    title = ""
    if isinstance(brief_title, str) and brief_title.strip():
        title = brief_title.strip()
    elif isinstance(official_title, str) and official_title.strip():
        title = official_title.strip()

    conditions_raw = _get_nested(study, ("protocolSection", "conditionsModule", "conditions"))
    conditions: List[str] = []
    if isinstance(conditions_raw, list):
        conditions = [str(item).strip() for item in conditions_raw if str(item).strip()]
    elif isinstance(conditions_raw, str) and conditions_raw.strip():
        conditions = [conditions_raw.strip()]

    status = _get_nested(study, ("protocolSection", "statusModule", "overallStatus"))
    status_text = status.strip() if isinstance(status, str) else ""

    phases_raw = _get_nested(study, ("protocolSection", "designModule", "phases"))
    phases: List[str] = []
    if isinstance(phases_raw, list):
        phases = [str(item).strip() for item in phases_raw if str(item).strip()]
    elif isinstance(phases_raw, str) and phases_raw.strip():
        phases = [phases_raw.strip()]

    raw_locations = _get_nested(
        study, ("protocolSection", "contactsLocationsModule", "locations")
    )
    locations: List[Dict[str, str]] = []
    if isinstance(raw_locations, list):
        for item in raw_locations:
            if not isinstance(item, dict):
                continue
            country = item.get("country")
            state = item.get("state")
            city = item.get("city")
            location = {
                "country": str(country).strip() if isinstance(country, str) else "",
                "state": str(state).strip() if isinstance(state, str) else "",
                "city": str(city).strip() if isinstance(city, str) else "",
            }
            if any(location.values()):
                locations.append(location)

    return {
        "nct_id": str(nct_id).strip(),
        "title": title,
        "conditions": conditions,
        "status": status_text,
        "phases": phases,
        "locations": locations,
    }


def _request_json(
    *,
    client: httpx.Client,
    base_url: str,
    path: str,
    params: Dict[str, str],
    max_retries: int = 3,
    backoff_seconds: float = 0.4,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            response = client.get(url, params=params)
            if response.status_code >= 500 or response.status_code == 429:
                raise httpx.HTTPStatusError(
                    f"server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("CTGov response is not JSON object")
            return payload
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(backoff_seconds * (2**attempt))

    raise RuntimeError(f"CTGov request failed: {last_error}") from last_error


def fetch_query_candidates(
    *,
    query: Dict[str, Any],
    base_url: str,
    timeout_seconds: float,
    page_size: int,
    page_limit_per_term: int,
    max_candidates_per_query: int,
) -> List[Dict[str, Any]]:
    terms = build_search_terms(query)
    studies_by_nct: Dict[str, Dict[str, Any]] = {}
    term_hits: Dict[str, List[str]] = defaultdict(list)

    with httpx.Client(timeout=timeout_seconds) as client:
        for term in terms:
            page_token: Optional[str] = None
            for _ in range(page_limit_per_term):
                params = {
                    "query.term": term,
                    "pageSize": str(page_size),
                }
                if page_token:
                    params["pageToken"] = page_token
                payload = _request_json(
                    client=client,
                    base_url=base_url,
                    path="/studies",
                    params=params,
                )
                studies = payload.get("studies")
                if not isinstance(studies, list):
                    studies = []
                for study in studies:
                    if not isinstance(study, dict):
                        continue
                    summary = _extract_study_summary(study)
                    if not summary:
                        continue
                    nct_id = summary["nct_id"]
                    if nct_id not in studies_by_nct:
                        studies_by_nct[nct_id] = summary
                    if term not in term_hits[nct_id]:
                        term_hits[nct_id].append(term)

                if len(studies_by_nct) >= max_candidates_per_query:
                    break
                next_token = payload.get("nextPageToken")
                if not isinstance(next_token, str) or not next_token.strip():
                    break
                page_token = next_token
            if len(studies_by_nct) >= max_candidates_per_query:
                break

    candidates = list(studies_by_nct.values())
    for candidate in candidates:
        candidate["term_hits"] = term_hits.get(candidate["nct_id"], [])
    return candidates


def _location_match_score(
    expected_location: Dict[str, Any], locations: Sequence[Dict[str, str]]
) -> int:
    if not isinstance(expected_location, dict) or not locations:
        return 0

    country = _normalize_country(str(expected_location.get("country") or ""))
    state = _normalize_state(str(expected_location.get("state") or ""))
    city = _norm_text(str(expected_location.get("city") or ""))
    score = 0

    if country:
        if any(country == _normalize_country(str(loc.get("country") or "")) for loc in locations):
            score += 1
    if state:
        if any(state == _normalize_state(str(loc.get("state") or "")) for loc in locations):
            score += 1
    if city:
        if any(city == _norm_text(str(loc.get("city") or "")) for loc in locations):
            score += 1
    return score


def score_trial_for_query(
    query: Dict[str, Any], trial: Dict[str, Any]
) -> Tuple[float, str, Dict[str, Any]]:
    expected_conditions = [
        item
        for item in (query.get("expected_conditions") or [])
        if isinstance(item, str) and item.strip()
    ]
    expected_condition_norms = [_norm_text(item) for item in expected_conditions]
    expected_phase = str(query.get("expected_phase") or "").strip().upper()
    expected_status = str(query.get("expected_status") or "").strip().upper()
    expected_location = query.get("expected_location") or {}
    intent_targets = _extract_query_intents(query)

    trial_title = str(trial.get("title") or "")
    trial_conditions = " ".join(str(item) for item in (trial.get("conditions") or []))
    trial_text = f"{trial_title} {trial_conditions}"
    trial_text_norm = _norm_text(trial_text)
    trial_tokens = _tokenize(trial_text)

    condition_exact = any(cond and cond in trial_text_norm for cond in expected_condition_norms)
    cond_overlap = 0
    for cond in expected_condition_norms:
        cond_overlap = max(cond_overlap, len(_tokenize(cond) & trial_tokens))

    query_overlap = len(_tokenize(str(query.get("query") or "")) & trial_tokens)
    status = str(trial.get("status") or "").strip().upper()
    phases = [str(item).strip().upper() for item in (trial.get("phases") or [])]
    status_match = bool(expected_status and status == expected_status)
    phase_match = bool(expected_phase and expected_phase in phases)
    location_match = _location_match_score(expected_location, trial.get("locations") or [])
    intent_match_count = _intent_match_count(
        intent_targets,
        trial_text_norm=trial_text_norm,
        trial_tokens=trial_tokens,
    )

    required_checks: List[bool] = []
    if expected_status:
        required_checks.append(status_match)
    if expected_phase:
        required_checks.append(phase_match)
    if _has_expected_location(expected_location):
        required_checks.append(location_match >= 1)
    if intent_targets:
        required_checks.append(intent_match_count >= 1)

    all_required_match = bool(required_checks) and all(required_checks)

    score = 0.0
    score += 6.0 if condition_exact else 0.0
    score += cond_overlap * 1.8
    score += 1.8 if status_match else 0.0
    score += 1.8 if phase_match else 0.0
    score += location_match * 1.2
    score += intent_match_count * 1.1
    score += 2.0 if all_required_match else 0.0
    if intent_targets and intent_match_count == 0:
        score -= 0.8
    score += min(query_overlap, 8) * 0.2

    if condition_exact and all_required_match:
        band = "likely_2"
    elif condition_exact or cond_overlap >= 2 or query_overlap >= 3:
        band = "likely_1"
    else:
        band = "hard_negative"

    features = {
        "condition_exact": condition_exact,
        "condition_token_overlap": cond_overlap,
        "query_token_overlap": query_overlap,
        "status_match": status_match,
        "phase_match": phase_match,
        "location_match_score": location_match,
        "intent_target_count": len(intent_targets),
        "intent_match_count": intent_match_count,
    }
    return round(score, 4), band, features


def load_excluded_pairs(paths: Sequence[Path]) -> set[Tuple[str, str]]:
    excluded: set[Tuple[str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        rows = load_jsonl(path)
        for row in rows:
            query_id = str(row.get("query_id") or "").strip()
            nct_id = str(row.get("nct_id") or "").strip()
            if query_id and nct_id:
                excluded.add((query_id, nct_id))
    return excluded


def build_pending_rows(
    *,
    queries: Sequence[Dict[str, Any]],
    candidates_by_query: Dict[str, List[Dict[str, Any]]],
    excluded_pairs: set[Tuple[str, str]],
    max_candidates_per_query: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {"queries": {}, "total_rows": 0}

    for query in queries:
        query_id = str(query.get("query_id") or "").strip()
        if not query_id:
            continue
        candidates = candidates_by_query.get(query_id, [])
        scored: List[Dict[str, Any]] = []
        for trial in candidates:
            pair = (query_id, trial["nct_id"])
            if pair in excluded_pairs:
                continue
            score, band, features = score_trial_for_query(query, trial)
            row = {
                "query_id": query_id,
                "nct_id": trial["nct_id"],
                "status": "PENDING",
                "task_type": "relevance",
                "guideline_version": "m4-v1",
                "source": "ctgov_v2",
                "band": band,
                "heuristic_score": score,
                "title": trial.get("title") or "",
                "overall_status": trial.get("status") or "",
                "phases": trial.get("phases") or [],
                "term_hits": trial.get("term_hits") or [],
                "features": features,
            }
            scored.append(row)

        scored.sort(key=lambda item: (-float(item["heuristic_score"]), str(item["nct_id"])))
        selected = scored[:max_candidates_per_query]
        rows.extend(selected)

        band_counts: Dict[str, int] = defaultdict(int)
        for item in selected:
            band_counts[str(item["band"])] += 1
        summary["queries"][query_id] = {
            "fetched_candidates": len(candidates),
            "after_exclusion": len(scored),
            "selected_candidates": len(selected),
            "band_counts": dict(sorted(band_counts.items())),
        }

    # Deterministic global order by query then score then nct_id.
    rows.sort(
        key=lambda item: (
            str(item["query_id"]),
            -float(item["heuristic_score"]),
            str(item["nct_id"]),
        )
    )
    for idx, row in enumerate(rows, start=1):
        row["task_id"] = f"relevance-v2-{idx:05d}"
    summary["total_rows"] = len(rows)
    return rows, summary


def build_round_batch(
    pending_rows: Sequence[Dict[str, Any]],
    *,
    target_per_query: int,
    likely2_quota: int,
    likely1_quota: int,
    hard_negative_quota: int,
    task_id_prefix: str = "relevance-v2r1",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    by_query: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: {"likely_2": [], "likely_1": [], "hard_negative": []}
    )
    for row in pending_rows:
        query_id = str(row["query_id"])
        band = str(row.get("band") or "hard_negative")
        if band not in by_query[query_id]:
            band = "hard_negative"
        by_query[query_id][band].append(row)

    selected: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {"queries": {}, "total_rows": 0}
    quota_map = {
        "likely_2": likely2_quota,
        "likely_1": likely1_quota,
        "hard_negative": hard_negative_quota,
    }

    for query_id in sorted(by_query):
        pools = by_query[query_id]
        picked: List[Dict[str, Any]] = []
        for band in ("likely_2", "likely_1", "hard_negative"):
            take = min(quota_map[band], len(pools[band]))
            picked.extend(pools[band][:take])
            pools[band] = pools[band][take:]

        # Fill remaining slots from the rest, prioritizing higher confidence bands.
        remaining_slots = max(target_per_query - len(picked), 0)
        fallback = pools["likely_2"] + pools["likely_1"] + pools["hard_negative"]
        picked.extend(fallback[:remaining_slots])

        picked.sort(key=lambda item: (-float(item["heuristic_score"]), str(item["nct_id"])))
        selected.extend(picked)

        picked_counts: Dict[str, int] = defaultdict(int)
        for item in picked:
            picked_counts[str(item["band"])] += 1
        summary["queries"][query_id] = {
            "picked": len(picked),
            "picked_band_counts": dict(sorted(picked_counts.items())),
            "requested_target": target_per_query,
            "shortfall": max(target_per_query - len(picked), 0),
        }

    selected.sort(
        key=lambda item: (
            str(item["query_id"]),
            -float(item["heuristic_score"]),
            str(item["nct_id"]),
        )
    )
    batch_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(selected, start=1):
        batch_row = dict(row)
        batch_row["task_id"] = f"{task_id_prefix}-{idx:05d}"
        batch_rows.append(batch_row)

    summary["total_rows"] = len(batch_rows)
    return batch_rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build v2 retrieval annotation pool and round-1 stratified batch."
    )
    parser.add_argument("--queries", default="eval/data/queries.jsonl")
    parser.add_argument("--ctgov-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--page-limit-per-term", type=int, default=2)
    parser.add_argument("--max-candidates-per-query", type=int, default=220)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional JSONL files containing query_id/nct_id pairs to exclude",
    )
    parser.add_argument(
        "--output-pending",
        default="eval/annotation_tasks/relevance.pending.v2.jsonl",
    )
    parser.add_argument(
        "--output-batch",
        default="eval/annotation_tasks/relevance.batch_v2_round1.700.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.relevance_v2_round1.json",
    )
    parser.add_argument("--target-per-query", type=int, default=70)
    parser.add_argument("--likely2-quota", type=int, default=20)
    parser.add_argument("--likely1-quota", type=int, default=30)
    parser.add_argument("--hard-negative-quota", type=int, default=20)
    parser.add_argument("--task-id-prefix", default="relevance-v2r1")
    args = parser.parse_args()

    if args.page_size < 1:
        raise ValueError("--page-size must be >= 1")
    if args.page_limit_per_term < 1:
        raise ValueError("--page-limit-per-term must be >= 1")
    if args.max_candidates_per_query < 1:
        raise ValueError("--max-candidates-per-query must be >= 1")
    if args.target_per_query < 1:
        raise ValueError("--target-per-query must be >= 1")

    queries = load_jsonl(Path(args.queries))
    exclude_paths: List[Path] = []
    for default_path in DEFAULT_EXCLUDE_FILES:
        path = Path(default_path)
        if path.exists():
            exclude_paths.append(path)
    for item in args.exclude:
        path = Path(item)
        if path not in exclude_paths:
            exclude_paths.append(path)
    excluded_pairs = load_excluded_pairs(exclude_paths)

    candidates_by_query: Dict[str, List[Dict[str, Any]]] = {}
    for query in queries:
        query_id = str(query.get("query_id") or "").strip()
        if not query_id:
            continue
        candidates_by_query[query_id] = fetch_query_candidates(
            query=query,
            base_url=args.ctgov_base_url,
            timeout_seconds=args.timeout_seconds,
            page_size=args.page_size,
            page_limit_per_term=args.page_limit_per_term,
            max_candidates_per_query=args.max_candidates_per_query * 2,
        )

    pending_rows, pending_summary = build_pending_rows(
        queries=queries,
        candidates_by_query=candidates_by_query,
        excluded_pairs=excluded_pairs,
        max_candidates_per_query=args.max_candidates_per_query,
    )
    batch_rows, batch_summary = build_round_batch(
        pending_rows,
        target_per_query=args.target_per_query,
        likely2_quota=args.likely2_quota,
        likely1_quota=args.likely1_quota,
        hard_negative_quota=args.hard_negative_quota,
        task_id_prefix=args.task_id_prefix,
    )

    output_pending = Path(args.output_pending)
    output_batch = Path(args.output_batch)
    output_manifest = Path(args.output_manifest)
    dump_jsonl(output_pending, pending_rows)
    dump_jsonl(output_batch, batch_rows)

    manifest = {
        "queries_path": args.queries,
        "excluded_files": [str(path) for path in exclude_paths],
        "excluded_pair_count": len(excluded_pairs),
        "pending": {
            "path": str(output_pending),
            "total_rows": len(pending_rows),
            "query_summary": pending_summary["queries"],
        },
        "batch_round_1": {
            "path": str(output_batch),
            "total_rows": len(batch_rows),
            "target_per_query": args.target_per_query,
            "quotas": {
                "likely_2": args.likely2_quota,
                "likely_1": args.likely1_quota,
                "hard_negative": args.hard_negative_quota,
            },
            "task_id_prefix": args.task_id_prefix,
            "query_summary": batch_summary["queries"],
        },
    }
    dump_json(output_manifest, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

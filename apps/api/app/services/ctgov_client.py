import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE_URL = "https://clinicaltrials.gov/api/v2"


@dataclass
class StudyPage:
    studies: List[Dict[str, Any]]
    next_page_token: Optional[str]


class CTGovClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        base = base_url or os.getenv("CTGOV_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = base.rstrip("/")
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def search_studies(
        self,
        condition: str,
        status: Optional[str] = None,
        page_token: Optional[str] = None,
    ) -> StudyPage:
        query_term = self._build_query_term(condition)
        params: Dict[str, str] = {"query.term": query_term}
        if status:
            params["filter.overallStatus"] = status
        if page_token:
            params["pageToken"] = page_token

        data = self._request_json("GET", "/studies", params=params)
        studies = data.get("studies", [])
        return StudyPage(studies=studies, next_page_token=data.get("nextPageToken"))

    def get_study(self, nct_id: str) -> Dict[str, Any]:
        return self._request_json("GET", f"/studies/{nct_id}")

    def _build_query_term(self, condition: str) -> str:
        term = condition.strip()
        if " " in term:
            term = f"\"{term}\""
        return f"AREA[ConditionSearch]{term}"

    def _request_json(
        self, method: str, path: str, params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(method, url, params=params)
                    if response.status_code >= 500 or response.status_code == 429:
                        raise httpx.HTTPStatusError(
                            f"server error {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(self.backoff_seconds * (2**attempt))

        raise RuntimeError(f"CTGov request failed: {last_error}") from last_error

"""Клиент DataLens API: ретраи (401/429/5xx/network), пагинация, связи."""
from __future__ import annotations

import random
import time
from typing import Any, Callable, Dict, List, Optional

import requests

API_BASE = "https://api.datalens.tech"


class DataLensClient:
    def __init__(self, org_id: str,
                 get_token: Callable[[], str],
                 refresh_token: Callable[[str], str],
                 sleeper: Callable[[float], None] = time.sleep,
                 jitter: Callable[[], float] = random.random,
                 max_retries: int = 5,
                 base_url: str = API_BASE,
                 verify_ssl: bool = False):
        self.org_id = org_id
        self._refresh_token = refresh_token
        self._sleep = sleeper
        self._jitter = jitter
        self.max_retries = max_retries
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.token = get_token()
        self.headers = {
            "accept": "application/json",
            "x-dl-api-version": "1",
            "Authorization": f"Bearer {self.token}",
            "x-dl-org-id": org_id,
            "Content-Type": "application/json",
        }

    def req(self, endpoint: str, data: Dict[str, Any], retry_on_401: bool = True):
        url = f"{self.base_url}{endpoint}"
        for attempt in range(self.max_retries):
            try:
                r = requests.post(url, headers=self.headers, json=data,
                                  verify=self.verify_ssl, timeout=60)
            except requests.exceptions.RequestException:
                if attempt < self.max_retries - 1:
                    self._sleep(self._backoff(attempt))
                    continue
                return None

            if r.status_code == 401 and retry_on_401:
                self.token = self._refresh_token(self.token)
                self.headers["Authorization"] = f"Bearer {self.token}"
                continue

            if r.status_code == 429 or 500 <= r.status_code < 600:
                wait = self._backoff(attempt)
                if r.status_code == 429 and "Retry-After" in r.headers:
                    try:
                        wait = float(r.headers["Retry-After"])
                    except ValueError:
                        pass
                if attempt < self.max_retries - 1:
                    self._sleep(wait)
                    continue
                return None

            if 400 <= r.status_code < 500:
                return None

            try:
                return r.json()
            except ValueError:
                return None
        return None

    def _backoff(self, attempt: int) -> float:
        return (2 ** attempt) + self._jitter()

    def get_entries_limit(self, scope: str, limit: int = 500) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            payload: Dict[str, Any] = {"scope": scope, "limit": limit}
            if page_token:
                payload["pageToken"] = page_token
            resp = self.req("/rpc/getEntries", payload)
            if not resp:
                break
            batch = resp.get("entries", [])
            entries.extend(batch)
            page_token = resp.get("nextPageToken")
            if not page_token or not batch:
                break
        return entries

    def get_entries_page(self, scope: str, page_size: int = 100) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        page = 1
        while True:
            resp = self.req("/rpc/getEntries", {"scope": scope, "page": page, "pageSize": page_size})
            if not resp:
                break
            batch = resp.get("entries", [])
            entries.extend(batch)
            if not resp.get("hasNextPage", False):
                break
            page += 1
        return entries

    def get_relations(self, entry_id: str, direction: str) -> List[str]:
        resp = self.req("/rpc/getEntriesRelations",
                        {"entryIds": [entry_id], "linkDirection": direction, "limit": 1000})
        if not resp:
            return []
        return list({rel["entryId"] for rel in resp.get("relations", []) if "entryId" in rel})

    def get_dataset(self, dataset_id: str):
        return self.req("/rpc/getDataset", {"datasetId": dataset_id})

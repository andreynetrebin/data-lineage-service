# fix_stage3.py
"""Перезаписывает файлы DataLens-коннектора Этапа 3. Запуск: python fix_stage3.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = {}

FILES["lineage_service/datalens/__init__.py"] = ""

FILES["lineage_service/datalens/client.py"] = r'''
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
'''

FILES["lineage_service/connectors/base.py"] = r'''
"""Базовый класс коннектора источника."""
from abc import ABC, abstractmethod
from typing import Dict, Optional

from ..model import Graph


class SourceConnector(ABC):
    system: str = "unknown"

    def __init__(self, cfg: Optional[Dict] = None):
        self.cfg = cfg or {}

    @abstractmethod
    def collect(self) -> Graph:
        """Собрать свой участок графа и вернуть Graph."""
'''

FILES["lineage_service/connectors/datalens.py"] = r'''
"""Коннектор DataLens: объекты, связи, скрытые датасеты -> Graph (объектный уровень)."""
from __future__ import annotations

from typing import Dict, Optional

from .. import config as app_config
from ..datalens import auth
from ..datalens.client import DataLensClient
from ..model import Edge, Graph, Node, node_id
from .base import SourceConnector

SCOPE_TYPE = {"dash": "dashboard", "dataset": "dataset",
              "connection": "connection", "widget": "widget"}


def build_client(cfg: Dict) -> DataLensClient:
    settings = app_config.load_settings()
    org_id = cfg.get("org_id") or settings.datalens_org_id
    if not org_id:
        raise auth.AuthError("Не задан DATALENS_ORG_ID (env или config.yaml).")
    return DataLensClient(
        org_id=org_id,
        get_token=lambda: auth.get_iam_token(settings),
        refresh_token=lambda used: auth.refresh_iam_token(settings, used),
    )


def _type_of(obj: Dict) -> str:
    return SCOPE_TYPE.get(obj.get("scope"), obj.get("scope", "object"))


class DataLensConnector(SourceConnector):
    system = "datalens"

    def __init__(self, cfg: Optional[Dict] = None, client: Optional[DataLensClient] = None):
        super().__init__(cfg or {})
        self.client = client or build_client(self.cfg)

    def collect(self) -> Graph:
        graph = Graph()
        objects: Dict[str, Dict] = {}

        for scope in ("connection", "dataset", "dash"):
            for entry in self.client.get_entries_limit(scope, 500):
                objects[entry["entryId"]] = entry
        for entry in self.client.get_entries_page("widget", 100):
            objects[entry["entryId"]] = entry

        missing = set()
        for obj_id, obj in objects.items():
            from_ids = self.client.get_relations(obj_id, "from")
            to_ids = self.client.get_relations(obj_id, "to")
            obj["from"], obj["to"] = from_ids, to_ids
            missing.update(x for x in from_ids + to_ids if x not in objects)

        for hidden_id in sorted(missing):
            resp = self.client.get_dataset(hidden_id)
            if resp and resp.get("id"):
                objects[hidden_id] = {
                    "entryId": hidden_id, "scope": "dataset",
                    "name": resp.get("name", hidden_id),
                    "createdAt": "", "updatedAt": "",
                    "from": [], "to": [], "hidden": True,
                }

        for obj_id, obj in objects.items():
            graph.add_node(Node(
                id=node_id("datalens", _type_of(obj), obj_id),
                system="datalens", type=_type_of(obj),
                name=obj.get("name") or obj_id,
                props={"scope": obj.get("scope"),
                       "createdAt": obj.get("createdAt"),
                       "updatedAt": obj.get("updatedAt"),
                       "hidden": bool(obj.get("hidden"))}))

        for obj_id, obj in objects.items():
            for rel in obj.get("to", []):
                if rel in objects:
                    graph.add_edge(Edge(src=node_id("datalens", _type_of(obj), obj_id),
                                        dst=node_id("datalens", _type_of(objects[rel]), rel),
                                        type="feeds", system="datalens"))
            for rel in obj.get("from", []):
                if rel in objects:
                    graph.add_edge(Edge(src=node_id("datalens", _type_of(objects[rel]), rel),
                                        dst=node_id("datalens", _type_of(obj), obj_id),
                                        type="feeds", system="datalens"))
        return graph
'''

FILES["lineage_service/connectors/__init__.py"] = r'''
"""Реестр коннекторов источников."""
from .datalens import DataLensConnector
# Этап 5: from .clickhouse_catalog import ClickHouseCatalogConnector
# Этап 6: from .airflow import AirflowOpenLineageConnector
#         from .extractor1c import Extractor1CConnector

REGISTRY = {
    "datalens": DataLensConnector,
}
'''


def main():
    for rel, content in FILES.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((content.strip("\n") + "\n") if content else "", encoding="utf-8")
        print(f"[write] {rel}")
    print("\nГотово. Проверьте импорты и тесты:")
    print('  python -c "from lineage_service.datalens.client import DataLensClient; '
          'from lineage_service.connectors.datalens import DataLensConnector; print(\'imports OK\')"')
    print("  pytest -q   (ожидаемо 37 passed)")


if __name__ == "__main__":
    main()
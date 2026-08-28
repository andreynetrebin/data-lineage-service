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

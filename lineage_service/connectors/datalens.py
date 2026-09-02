"""Коннектор DataLens: объекты + источники/аватары/поля -> Graph."""
from __future__ import annotations

import logging
from typing import Dict, Optional

from .. import config as app_config
from ..datalens import auth
from ..datalens.client import DataLensClient
from ..datalens.fields_parser import parse_dataset
from ..model import Edge, Graph, Node, node_id
from .base import SourceConnector

log = logging.getLogger("datalens.connector")

SCOPE_TYPE = {"dash": "dashboard", "dataset": "dataset",
              "connection": "connection", "widget": "widget"}


def build_client(cfg: Dict) -> DataLensClient:
    log.info("DataLens: инициализация клиента (получаем IAM-токен)...")
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

        log.info("DataLens: загрузка объектов (connection/dataset/dash/widget)...")
        for scope in ("connection", "dataset", "dash"):
            entries = self.client.get_entries_limit(scope, 500)
            log.info("  scope=%s: %d объектов", scope, len(entries))
            for entry in entries:
                objects[entry["entryId"]] = entry
        widgets = self.client.get_entries_page("widget", 100)
        log.info("  scope=widget: %d объектов", len(widgets))
        for entry in widgets:
            objects[entry["entryId"]] = entry

        log.info("DataLens: сбор связей для %d объектов...", len(objects))
        missing = set()
        total = len(objects)
        for idx, (obj_id, obj) in enumerate(objects.items(), 1):
            if idx == 1 or idx % 20 == 0 or idx == total:
                log.info("  связи %d/%d: %s", idx, total, obj_id)
            from_ids = self.client.get_relations(obj_id, "from")
            to_ids = self.client.get_relations(obj_id, "to")
            obj["from"], obj["to"] = from_ids, to_ids
            missing.update(x for x in from_ids + to_ids if x not in objects)

        log.info("DataLens: найдено %d скрытых объектов", len(missing))
        dataset_responses: Dict[str, Dict] = {}
        for hidden_id in sorted(missing):
            log.info("  скрытый: %s", hidden_id)
            resp = self.client.get_dataset(hidden_id)
            if resp and resp.get("id"):
                objects[hidden_id] = {
                    "entryId": hidden_id, "scope": "dataset",
                    "name": resp.get("name", hidden_id),
                    "createdAt": "", "updatedAt": "",
                    "from": [], "to": [], "hidden": True,
                }
                dataset_responses[hidden_id] = resp

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

        dataset_ids = [oid for oid, o in objects.items() if o.get("scope") == "dataset"]
        log.info("DataLens: обогащение %d датасетов (source/avatar/field)...",
                 len(dataset_ids))
        for ds_id in dataset_ids:
            log.debug("  обогащаем %s", ds_id)
            if ds_id in dataset_responses:
                resp = dataset_responses[ds_id]
            else:
                resp = self.client.get_dataset(ds_id)
            if not resp:
                continue
            try:
                parsed = parse_dataset(resp)
            except Exception:
                log.warning("  не удалось распарсить %s", ds_id)
                continue
            self._enrich_with_parsed_dataset(graph, ds_id, parsed)

        log.info("DataLens: готово, узлов=%d рёбер=%d",
                 graph.stats["nodes"], graph.stats["edges"])
        return graph

    @staticmethod
    def _enrich_with_parsed_dataset(graph: Graph, dataset_id: str, parsed) -> None:
        ds_node_id = node_id("datalens", "dataset", dataset_id)

        for src in parsed.sources:
            src_id = node_id("datalens", "source", src.id)
            graph.add_node(Node(id=src_id, system="datalens", type="source",
                                name=src.title,
                                props={"source_type": src.source_type}))
            graph.add_edge(Edge(src=src_id, dst=ds_node_id,
                                type="feeds", system="datalens"))
            for tbl in src.tables:
                tbl_full = tbl if "." in tbl else f"extractor.{tbl}"
                graph.add_node(Node(id=node_id("clickhouse", "table", tbl_full),
                                    system="clickhouse", type="table", name=tbl_full))
                graph.add_edge(Edge(src=node_id("clickhouse", "table", tbl_full),
                                    dst=src_id, type="feeds", system="datalens"))

        for av in parsed.avatars:
            av_id = node_id("datalens", "avatar", av.id)
            src_id = node_id("datalens", "source", av.source_id)
            graph.add_node(Node(id=av_id, system="datalens", type="avatar",
                                name=av.title, props={"is_root": av.is_root}))
            graph.add_edge(Edge(src=src_id, dst=av_id,
                                type="uses", system="datalens"))

        for rel in parsed.avatar_relations:
            left = node_id("datalens", "avatar", rel.left_avatar_id)
            right = node_id("datalens", "avatar", rel.right_avatar_id)
            graph.add_edge(Edge(src=left, dst=right, type="joins",
                                system="datalens",
                                props={"join_type": rel.join_type,
                                       "conditions": [{"left": c.left_source,
                                                        "right": c.right_source,
                                                        "op": c.operator}
                                                       for c in rel.conditions]}))

        for f in parsed.fields:
            f_id = node_id("datalens", "field", f.guid)
            graph.add_node(Node(id=f_id, system="datalens", type="field", name=f.title,
                                props={"type": f.type, "data_type": f.data_type,
                                       "calc_mode": f.calc_mode, "formula": f.formula}))
            if f.avatar_id:
                av_id = node_id("datalens", "avatar", f.avatar_id)
                graph.add_edge(Edge(src=av_id, dst=f_id,
                                    type="maps_to", system="datalens"))

        deps_by_id = {d.field_id: d.depends_on for d in parsed.field_dependencies}
        for f in parsed.fields:
            for ref in deps_by_id.get(f.guid, []):
                graph.add_edge(Edge(src=node_id("datalens", "field", f.guid),
                                    dst=node_id("datalens", "field", ref),
                                    type="depends_on", system="datalens"))

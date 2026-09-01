"""Коннектор DataLens: объекты + источники/аватары/поля -> Graph."""
from __future__ import annotations

from typing import Dict, Optional

from .. import config as app_config
from ..datalens import auth
from ..datalens.client import DataLensClient
from ..datalens.fields_parser import parse_dataset
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

        # 1. Все объекты из getEntries
        for scope in ("connection", "dataset", "dash"):
            for entry in self.client.get_entries_limit(scope, 500):
                objects[entry["entryId"]] = entry
        for entry in self.client.get_entries_page("widget", 100):
            objects[entry["entryId"]] = entry

        # 2. Связи + поиск скрытых объектов
        missing = set()
        for obj_id, obj in objects.items():
            from_ids = self.client.get_relations(obj_id, "from")
            to_ids = self.client.get_relations(obj_id, "to")
            obj["from"], obj["to"] = from_ids, to_ids
            missing.update(x for x in from_ids + to_ids if x not in objects)

        # 3. Скрытые dataset'ы — get_dataset, ответы кэшируем
        dataset_responses: Dict[str, Dict] = {}
        for hidden_id in sorted(missing):
            resp = self.client.get_dataset(hidden_id)
            if resp and resp.get("id"):
                objects[hidden_id] = {
                    "entryId": hidden_id, "scope": "dataset",
                    "name": resp.get("name", hidden_id),
                    "createdAt": "", "updatedAt": "",
                    "from": [], "to": [], "hidden": True,
                }
                dataset_responses[hidden_id] = resp

        # 4. Узлы объектов
        for obj_id, obj in objects.items():
            graph.add_node(Node(
                id=node_id("datalens", _type_of(obj), obj_id),
                system="datalens", type=_type_of(obj),
                name=obj.get("name") or obj_id,
                props={"scope": obj.get("scope"),
                       "createdAt": obj.get("createdAt"),
                       "updatedAt": obj.get("updatedAt"),
                       "hidden": bool(obj.get("hidden"))}))

        # 5. Рёбра между объектами (feeds, направление = поток данных)
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

        # 6. Обогащение: source/avatar/field для каждого dataset'а
        dataset_ids = [oid for oid, o in objects.items() if o.get("scope") == "dataset"]
        for ds_id in dataset_ids:
            if ds_id in dataset_responses:
                resp = dataset_responses[ds_id]
            else:
                resp = self.client.get_dataset(ds_id)
            if not resp:
                continue
            try:
                parsed = parse_dataset(resp)
            except Exception:
                continue
            self._enrich_with_parsed_dataset(graph, ds_id, parsed)

        return graph

    @staticmethod
    def _enrich_with_parsed_dataset(graph: Graph, dataset_id: str, parsed) -> None:
        ds_node_id = node_id("datalens", "dataset", dataset_id)

        # Источники -> dataset (feeds) и таблицы -> source (feeds)
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

        # Аватары -> source (uses)
        for av in parsed.avatars:
            av_id = node_id("datalens", "avatar", av.id)
            src_id = node_id("datalens", "source", av.source_id)
            graph.add_node(Node(id=av_id, system="datalens", type="avatar",
                                name=av.title, props={"is_root": av.is_root}))
            graph.add_edge(Edge(src=src_id, dst=av_id,
                                type="uses", system="datalens"))

        # Джойны между аватарами
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

        # Поля -> avatar (maps_to)
        for f in parsed.fields:
            f_id = node_id("datalens", "field", f.guid)
            graph.add_node(Node(id=f_id, system="datalens", type="field", name=f.title,
                                props={"type": f.type, "data_type": f.data_type,
                                       "calc_mode": f.calc_mode, "formula": f.formula}))
            if f.avatar_id:
                av_id = node_id("datalens", "avatar", f.avatar_id)
                graph.add_edge(Edge(src=av_id, dst=f_id,
                                    type="maps_to", system="datalens"))

        # Зависимости между полями (depends_on)
        deps_by_id = {d.field_id: d.depends_on for d in parsed.field_dependencies}
        for f in parsed.fields:
            for ref in deps_by_id.get(f.guid, []):
                graph.add_edge(Edge(src=node_id("datalens", "field", f.guid),
                                    dst=node_id("datalens", "field", ref),
                                    type="depends_on", system="datalens"))

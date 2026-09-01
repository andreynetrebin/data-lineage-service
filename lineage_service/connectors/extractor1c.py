"""Коннектор 1С Экстрактора: РасписаниеЭкстрактор -> source_1c -> table."""
from __future__ import annotations

from typing import Dict, Optional

from ..model import Edge, Graph, Node, node_id
from .base import SourceConnector


class Extractor1CConnector(SourceConnector):
    system = "1c"

    def __init__(self, cfg: Optional[Dict] = None, client=None):
        super().__init__(cfg or {})
        self.client = client or self._build_client()

    def _build_client(self):
        from ..sinks.clickhouse_sink import create_client
        return create_client(self.cfg.get("clickhouse", {}))

    def collect(self) -> Graph:
        graph = Graph()
        table = self.cfg.get("table")
        if not table:
            return graph

        sql = f"SELECT `Проект`, `Источник`, `Приемник` FROM {table}"
        try:
            rows = self.client.query(sql).result_rows
        except Exception:
            rows = []

        for project, src, dst in rows:
            if not src or not dst:
                continue
            src_id = node_id("1c", "source_1c", str(src))
            graph.add_node(Node(id=src_id, system="1c", type="source_1c",
                                name=str(src),
                                props={"project": str(project or "")}))
            dst_id = node_id("clickhouse", "table", f"extractor.{dst}")
            graph.add_node(Node(id=dst_id, system="clickhouse", type="table",
                                name=f"extractor.{dst}"))
            graph.add_edge(Edge(src=src_id, dst=dst_id,
                                type="extracts_to", system="1c"))
        return graph

"""Коннектор Airflow OpenLineage: читает dags_events, строит DAG + in/out таблицы."""
from __future__ import annotations

from typing import Dict, Optional, Set

from ..model import Edge, Graph, Node, node_id
from .base import SourceConnector


def normalize_uri(uri: str) -> str:
    """
    'clickhouse://:extractor.РН_ДанныеПоПрибыли' -> 'extractor.РН_ДанныеПоПрибыли'
    'clickhouse:///extractor.t'                  -> 'extractor.t'
    """
    if not uri:
        return ""
    s = str(uri)
    for prefix in ("clickhouse:///", "clickhouse://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    if s.startswith(":"):
        s = s[1:]
    return s


class AirflowOpenLineageConnector(SourceConnector):
    system = "airflow"

    def __init__(self, cfg: Optional[Dict] = None, client=None):
        super().__init__(cfg or {})
        self.client = client or self._build_client()

    def _build_client(self):
        from ..sinks.clickhouse_sink import create_client
        return create_client(self.cfg.get("clickhouse", {}))

    def collect(self) -> Graph:
        graph = Graph()
        lookback_days = int(self.cfg.get("lookback_days", 30))
        database = self.cfg.get("clickhouse", {}).get("database", "NetrebinAA")
        sql = (
            f"SELECT DISTINCT job_name, arrayJoin(inputs) AS i, arrayJoin(outputs) AS o "
            f"FROM {database}.dags_events "
            f"WHERE notEmpty(outputs) "
            f"AND event_time >= now() - INTERVAL {lookback_days} DAY"
        )
        try:
            rows = self.client.query(sql).result_rows
        except Exception:
            rows = []

        seen_dags: Set[str] = set()
        seen_tables: Set[str] = set()

        for job, inp, out in rows:
            if not job:
                continue
            dag_id = node_id("airflow", "dag", str(job))
            if dag_id not in seen_dags:
                graph.add_node(Node(id=dag_id, system="airflow",
                                    type="dag", name=str(job)))
                seen_dags.add(dag_id)

            if inp:
                in_norm = normalize_uri(inp)
                if in_norm:
                    in_id = node_id("clickhouse", "table", in_norm)
                    if in_id not in seen_tables:
                        graph.add_node(Node(id=in_id, system="clickhouse",
                                            type="table", name=in_norm))
                        seen_tables.add(in_id)
                    graph.add_edge(Edge(src=in_id, dst=dag_id,
                                        type="processed_by", system="airflow"))

            if out:
                out_norm = normalize_uri(out)
                if out_norm:
                    out_id = node_id("clickhouse", "table", out_norm)
                    if out_id not in seen_tables:
                        graph.add_node(Node(id=out_id, system="clickhouse",
                                            type="table", name=out_norm))
                        seen_tables.add(out_id)
                    graph.add_edge(Edge(src=dag_id, dst=out_id,
                                        type="produces", system="airflow"))
        return graph

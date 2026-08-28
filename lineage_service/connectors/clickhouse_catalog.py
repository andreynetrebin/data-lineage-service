"""Коннектор: каталог ClickHouse (system.databases / system.tables / system.columns)."""
from __future__ import annotations

from typing import Dict, List, Optional

from ..model import Edge, Graph, Node, node_id
from .base import SourceConnector

SKIP_DB = {"system", "INFORMATION_SCHEMA", "information_schema"}


class ClickHouseCatalogConnector(SourceConnector):
    system = "clickhouse"

    def __init__(self, cfg: Optional[Dict] = None, client=None):
        super().__init__(cfg or {})
        self.client = client or self._build_client()

    def _build_client(self):
        from ..sinks.clickhouse_sink import create_client
        return create_client(self.cfg.get("clickhouse", {}))

    def collect(self) -> Graph:
        graph = Graph()
        databases = self.cfg.get("databases", [])

        # Читаем список БД
        db_query = "SELECT name FROM system.databases"
        if databases:
            db_query += " WHERE name IN %(databases)s"
        db_rows = self.client.query(db_query, parameters={"databases": databases} if databases else {}).result_rows
        db_names = [r[0] for r in db_rows if r[0] not in SKIP_DB]

        # Узлы БД
        for db in db_names:
            graph.add_node(Node(
                id=node_id("clickhouse", "database", db),
                system="clickhouse",
                type="database",
                name=db,
            ))

        # Читаем таблицы
        tables_query = """
        SELECT database, name, engine, COALESCE(total_rows, 0) AS rows
        FROM system.tables
        WHERE database IN %(databases)s
        """
        table_rows = self.client.query(
            tables_query,
            parameters={"databases": db_names}
        ).result_rows

        for db, table, engine, rows_cnt in table_rows:
            table_id = node_id("clickhouse", "table", f"{db}.{table}")
            graph.add_node(Node(
                id=table_id,
                system="clickhouse",
                type="table",
                name=f"{db}.{table}",
                props={"engine": engine, "rows": int(rows_cnt)},
            ))
            graph.add_edge(Edge(
                src=node_id("clickhouse", "database", db),
                dst=table_id,
                type="contains",
                system="clickhouse",
            ))

        # Читаем колонки
        columns_query = """
        SELECT database, table, name, type, position
        FROM system.columns
        WHERE database IN %(databases)s
        ORDER BY database, table, position
        """
        column_rows = self.client.query(
            columns_query,
            parameters={"databases": db_names}
        ).result_rows

        for db, table, col, col_type, pos in column_rows:
            col_id = node_id("clickhouse", "column", f"{db}.{table}.{col}")
            graph.add_node(Node(
                id=col_id,
                system="clickhouse",
                type="column",
                name=col,
                props={
                    "table": f"{db}.{table}",
                    "data_type": col_type,
                    "position": int(pos),
                },
            ))
            graph.add_edge(Edge(
                src=node_id("clickhouse", "table", f"{db}.{table}"),
                dst=col_id,
                type="contains",
                system="clickhouse",
            ))

        return graph
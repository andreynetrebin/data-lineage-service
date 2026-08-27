"""ClickHouse-sink на clickhouse-connect (HTTP): версионированный граф + каталожные view."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from ..model import Edge, Node, Snapshot
from .base import Sink

# DDL-миграции: выполняются идемпотентно при инициализации Sink.
DDL: List[str] = [
    """CREATE TABLE IF NOT EXISTS meta_snapshots (
        snapshot_id String,
        started_at DateTime,
        finished_at Nullable(DateTime),
        status LowCardinality(String),
        stats String
    ) ENGINE = ReplacingMergeTree()
    ORDER BY snapshot_id""",
    """CREATE TABLE IF NOT EXISTS meta_nodes (
        snapshot_id String,
        node_id String,
        system LowCardinality(String),
        type LowCardinality(String),
        name String,
        props String
    ) ENGINE = ReplacingMergeTree()
    ORDER BY (node_id, snapshot_id)""",
    """CREATE TABLE IF NOT EXISTS meta_edges (
        snapshot_id String,
        src String,
        dst String,
        type LowCardinality(String),
        system LowCardinality(String),
        props String
    ) ENGINE = ReplacingMergeTree()
    ORDER BY (src, dst, type, snapshot_id)""",
    """CREATE OR REPLACE VIEW catalog_latest AS
       SELECT node_id, system, type, name, props
       FROM meta_nodes FINAL
       WHERE snapshot_id = (
           SELECT max(snapshot_id) FROM meta_snapshots FINAL WHERE status = 'success'
       )""",
    """CREATE OR REPLACE VIEW edges_latest AS
       SELECT src, dst, type, system, props
       FROM meta_edges FINAL
       WHERE snapshot_id = (
           SELECT max(snapshot_id) FROM meta_snapshots FINAL WHERE status = 'success'
       )""",
]

SNAPSHOT_COLUMNS = ["snapshot_id", "started_at", "finished_at", "status", "stats"]
NODE_COLUMNS = ["snapshot_id", "node_id", "system", "type", "name", "props"]
EDGE_COLUMNS = ["snapshot_id", "src", "dst", "type", "system", "props"]


def create_client(ch: Dict[str, Any]):
    """Фабрика клиента clickhouse-connect (HTTP-интерфейс, по умолчанию порт 8123)."""
    import clickhouse_connect  # ленивый импорт: модуль импортируется без установленного пакета

    return clickhouse_connect.get_client(
        host=ch["host"],
        port=int(ch["port"]),
        username=ch["user"],
        password=ch["password"],
        database=ch["database"],
    )


class ClickHouseSink(Sink):
    """Пишет снапшот в ClickHouse: running -> данные -> success."""

    def __init__(self, client: Any, batch_size: int = 1000, auto_ensure_schema: bool = True):
        self.client = client
        self.batch_size = max(1, int(batch_size))
        if auto_ensure_schema:
            self.ensure_schema()

    def ensure_schema(self) -> None:
        for stmt in DDL:
            self.client.command(stmt)

    # ---- Sink API -------------------------------------------------------
    def write(self, snapshot: Snapshot, nodes: Sequence[Node], edges: Sequence[Edge]) -> None:
        self._insert("meta_snapshots", SNAPSHOT_COLUMNS,
                     [(snapshot.id, snapshot.started_at, None, "running", "{}")])

        self._insert("meta_nodes", NODE_COLUMNS, [
            (snapshot.id, n.id, n.system, n.type, n.name,
             json.dumps(n.props, ensure_ascii=False, default=str))
            for n in nodes
        ])
        self._insert("meta_edges", EDGE_COLUMNS, [
            (snapshot.id, e.src, e.dst, e.type, e.system,
             json.dumps(e.props, ensure_ascii=False, default=str))
            for e in edges
        ])

        snapshot.finish(len(nodes), len(edges))
        self._insert("meta_snapshots", SNAPSHOT_COLUMNS,
                     [(snapshot.id, snapshot.started_at, snapshot.finished_at,
                       snapshot.status, json.dumps(snapshot.stats, ensure_ascii=False))])

    # ---- queries --------------------------------------------------------
    def list_snapshots(self, limit: int = 20) -> List[tuple]:
        result = self.client.query(
            "SELECT snapshot_id, started_at, status, stats "
            "FROM meta_snapshots FINAL ORDER BY started_at DESC LIMIT {limit:UInt32}",
            parameters={"limit": int(limit)},
        )
        return result.result_rows

    def latest_success(self):
        value = self.client.command(
            "SELECT max(snapshot_id) FROM meta_snapshots FINAL WHERE status = 'success'"
        )
        return value or None

    # ---- internals ------------------------------------------------------
    def _insert(self, table: str, columns: Sequence[str], rows: Sequence[tuple]) -> None:
        if not rows:
            return
        rows = list(rows)
        for i in range(0, len(rows), self.batch_size):
            self.client.insert(table, rows[i:i + self.batch_size], column_names=list(columns))
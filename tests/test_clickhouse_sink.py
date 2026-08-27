"""Тесты ClickHouse-sink (clickhouse-connect) через фейковый клиент."""
from datetime import datetime

from lineage_service.model import Edge, Node, Snapshot
from lineage_service.sinks.clickhouse_sink import (
    DDL, EDGE_COLUMNS, NODE_COLUMNS, SNAPSHOT_COLUMNS, ClickHouseSink,
)


class FakeQueryResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    """Повторяет интерфейс clickhouse-connect: command / insert / query."""

    def __init__(self, command_result="", query_rows=None):
        self.commands = []
        self.inserts = []
        self.queries = []
        self._command_result = command_result
        self._query_rows = query_rows if query_rows is not None else []

    def command(self, sql, parameters=None):
        self.commands.append((sql, parameters))
        return self._command_result

    def insert(self, table, data, column_names=None):
        self.inserts.append((table, list(data), column_names))

    def query(self, sql, parameters=None):
        self.queries.append((sql, parameters))
        return FakeQueryResult(self._query_rows)

    def inserts_of(self, table):
        return [i for i in self.inserts if i[0] == table]


def make_sink(client, **kwargs):
    return ClickHouseSink(client, auto_ensure_schema=False, **kwargs)


# ---- схема ---------------------------------------------------------------
def test_ensure_schema_executes_all_ddl_via_command():
    client = FakeClient()
    ClickHouseSink(client, auto_ensure_schema=True)
    assert [c[0] for c in client.commands] == DDL


def test_auto_ensure_schema_can_be_disabled():
    client = FakeClient()
    ClickHouseSink(client, auto_ensure_schema=False)
    assert client.commands == [] and client.inserts == []


# ---- запись снапшота -----------------------------------------------------
def test_write_transitions_snapshot_running_then_success():
    client = FakeClient()
    snap = Snapshot(id="s1", started_at=datetime(2026, 8, 26, 10, 0))
    make_sink(client).write(snap, [Node("a", "s", "t", "n")], [Edge("a", "b", "feeds", "s")])

    assert snap.status == "success"
    assert snap.stats == {"nodes": 1, "edges": 1}
    assert snap.finished_at is not None

    snap_inserts = client.inserts_of("meta_snapshots")
    assert len(snap_inserts) == 2
    assert snap_inserts[0][2] == SNAPSHOT_COLUMNS
    assert snap_inserts[0][1][0][3] == "running"
    assert snap_inserts[0][1][0][2] is None          # finished_at = NULL
    assert snap_inserts[1][1][0][3] == "success"
    assert snap_inserts[1][1][0][2] is not None


def test_write_inserts_nodes_and_edges_with_columns_and_json_props():
    client = FakeClient()
    snap = Snapshot(id="s2", started_at=datetime(2026, 8, 26))
    nodes = [Node("a", "s", "t", "n1"), Node("b", "s", "t", "n2", props={"k": "v"})]
    edges = [Edge("a", "b", "feeds", "s"), Edge("a", "c", "feeds", "s", props={"x": 1})]
    make_sink(client).write(snap, nodes, edges)

    node_ins, edge_ins = client.inserts_of("meta_nodes"), client.inserts_of("meta_edges")
    assert len(node_ins) == 1 and len(node_ins[0][1]) == 2 and node_ins[0][2] == NODE_COLUMNS
    assert len(edge_ins) == 1 and len(edge_ins[0][1]) == 2 and edge_ins[0][2] == EDGE_COLUMNS
    assert any('{"k": "v"}' in row[5] for row in node_ins[0][1])
    assert any('{"x": 1}' in row[5] for row in edge_ins[0][1])


def test_write_empty_graph_skips_node_and_edge_inserts():
    client = FakeClient()
    snap = Snapshot(id="s_empty", started_at=datetime(2026, 8, 26))
    make_sink(client).write(snap, [], [])

    assert client.inserts_of("meta_nodes") == []
    assert client.inserts_of("meta_edges") == []
    assert len(client.inserts_of("meta_snapshots")) == 2
    assert snap.stats == {"nodes": 0, "edges": 0}


# ---- батчирование --------------------------------------------------------
def test_inserts_are_batched_by_batch_size():
    client = FakeClient()
    snap = Snapshot(id="s3", started_at=datetime(2026, 8, 26))
    nodes = [Node(f"n{i}", "s", "t", f"n{i}") for i in range(5)]
    make_sink(client, batch_size=2).write(snap, nodes, [])

    assert [len(i[1]) for i in client.inserts_of("meta_nodes")] == [2, 2, 1]


# ---- запросы -------------------------------------------------------------
def test_latest_success_returns_none_for_empty_table():
    assert make_sink(FakeClient(command_result="")).latest_success() is None
    assert make_sink(FakeClient(command_result=None)).latest_success() is None


def test_latest_success_returns_snapshot_id():
    assert make_sink(FakeClient(command_result="s42")).latest_success() == "s42"


def test_list_snapshots_uses_typed_parameter_and_returns_rows():
    rows = [("s1", datetime(2026, 8, 26), "success", "{}")]
    client = FakeClient(query_rows=rows)
    assert make_sink(client).list_snapshots(limit=7) == rows

    sql, params = client.queries[0]
    assert "{limit:UInt32}" in sql
    assert params == {"limit": 7}
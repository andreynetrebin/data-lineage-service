"""Тесты CLI-команд lineage и diff (с моками ClickHouse)."""
from unittest.mock import MagicMock, patch

import pytest

from lineage_service import cli
from lineage_service.model import Edge, Node


class FakeQueryResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    def __init__(self, rows_by_table):
        self._rows = rows_by_table

    def query(self, sql, parameters=None):
        for table, rows in self._rows.items():
            if table in sql:
                return FakeQueryResult(rows)
        return FakeQueryResult([])


@patch("lineage_service.cli.create_client")
def test_lineage_downstream(mock_create, capsys):
    edges = [
        ("1c:source_1c:HW", "clickhouse:table:extractor.t1", "extracts_to", "1c"),
        ("clickhouse:table:extractor.t1", "datalens:source:s1", "feeds", "datalens"),
    ]
    mock_create.return_value = FakeClient({"edges_latest": edges})

    cli.lineage("1c:source_1c:HW", direction="downstream", depth=5)

    out = capsys.readouterr().out
    assert "Обход downstream" in out
    assert "1c:source_1c:HW" in out
    assert "clickhouse:table:extractor.t1" in out
    assert "datalens:source:s1" in out


@patch("lineage_service.cli.create_client")
def test_diff_detects_changes(mock_create, capsys):
    old_nodes = [("a", "s", "t", "A", "{}")]
    new_nodes = [("b", "s", "t", "B", "{}")]
    old_edges = [("a", "b", "feeds", "s", "{}")]
    new_edges = [("b", "c", "feeds", "s", "{}")]

    mock_create.return_value = FakeClient({
        "meta_nodes": old_nodes if "from_snap" in str(mock_create.call_args) else new_nodes,
        "meta_edges": old_edges if "from_snap" in str(mock_create.call_args) else new_edges,
    })

    # Мокаем параметры запроса
    def fake_query(sql, parameters=None):
        sid = (parameters or {}).get("sid", "")
        if "meta_nodes" in sql:
            return FakeQueryResult(old_nodes if sid == "from_snap" else new_nodes)
        if "meta_edges" in sql:
            return FakeQueryResult(old_edges if sid == "from_snap" else new_edges)
        return FakeQueryResult([])

    mock_create.return_value.query = fake_query

    cli.diff("from_snap", "to_snap")

    out = capsys.readouterr().out
    assert "Diff from_snap -> to_snap" in out
    assert "+ node b" in out or "- node a" in out


@patch("lineage_service.cli.create_client")
def test_snapshots_lists(mock_create, capsys):
    snaps = [
        ("snap1", "2026-09-02 10:00:00", "success", '{"nodes": 100, "edges": 50}'),
        ("snap2", "2026-09-02 09:00:00", "success", '{"nodes": 95, "edges": 48}'),
    ]
    mock_create.return_value = FakeClient({"meta_snapshots": snaps})

    cli.snapshots()

    out = capsys.readouterr().out
    assert "snap1" in out
    assert "snap2" in out

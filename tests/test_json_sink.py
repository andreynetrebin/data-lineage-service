"""Тесты JSON-sink: запись снапшота в файл."""
import json
from datetime import datetime
from pathlib import Path

from lineage_service.model import Edge, Node, Snapshot
from lineage_service.sinks.json_sink import JsonSink


def test_writes_snapshot_to_file(tmp_path: Path):
    sink = JsonSink(tmp_path)
    snap = Snapshot(id="abc123", started_at=datetime(2026, 8, 26, 12, 0, 0))
    snap.finish(nodes=2, edges=1)

    nodes = [
        Node(id="ch:table:t1", system="clickhouse", type="table", name="t1"),
        Node(id="dl:dataset:d1", system="datalens", type="dataset", name="d1",
             props={"scope": "dataset"}),
    ]
    edges = [Edge(src="ch:table:t1", dst="dl:dataset:d1", type="feeds", system="datalens")]

    path = sink.write(snap, nodes, edges)

    assert path.exists()
    assert path.name == "snapshot_abc123.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["snapshot"]["id"] == "abc123"
    assert data["snapshot"]["status"] == "success"
    assert data["snapshot"]["stats"] == {"nodes": 2, "edges": 1}
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["src"] == "ch:table:t1"
    assert data["nodes"][1]["props"] == {"scope": "dataset"}


def test_creates_nested_out_dir(tmp_path: Path):
    out = tmp_path / "nested" / "out"
    sink = JsonSink(out)
    assert out.is_dir()

    snap = Snapshot(id="x", started_at=datetime(2026, 8, 26))
    snap.finish(0, 0)
    assert sink.write(snap, [], []).exists()
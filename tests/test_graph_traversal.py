"""Тесты BFS-обхода графа lineage."""
import pytest

from lineage_service.graph_traversal import traverse
from lineage_service.model import Edge


def E(src, dst, t="feeds"):
    return Edge(src=src, dst=dst, type=t, system="test")


CHAIN = [
    E("1c:source_1c:HW", "clickhouse:table:extractor.t1", "extracts_to"),
    E("clickhouse:table:extractor.t1", "airflow:dag:d1", "processed_by"),
    E("airflow:dag:d1", "clickhouse:table:extractor.t2", "produces"),
    E("clickhouse:table:extractor.t2", "datalens:source:s1", "feeds"),
    E("datalens:source:s1", "datalens:avatar:a1", "uses"),
    E("datalens:avatar:a1", "datalens:field:f1", "maps_to"),
]


def test_downstream_reaches_end_of_chain():
    visited, edges = traverse(CHAIN, "1c:source_1c:HW", direction="downstream")
    assert "datalens:field:f1" in visited
    assert len(visited) == 7
    assert len(edges) == 6


def test_upstream_reaches_root():
    visited, edges = traverse(CHAIN, "datalens:field:f1", direction="upstream")
    assert "1c:source_1c:HW" in visited
    assert len(visited) == 7


def test_max_depth_limits_traversal():
    visited, _ = traverse(CHAIN, "1c:source_1c:HW",
                          direction="downstream", max_depth=2)
    assert "clickhouse:table:extractor.t1" in visited
    assert "airflow:dag:d1" in visited
    assert "clickhouse:table:extractor.t2" not in visited


def test_cycle_does_not_loop_forever():
    edges = [E("a", "b"), E("b", "a"), E("b", "c")]
    visited, _ = traverse(edges, "a", direction="downstream")
    assert visited == {"a", "b", "c"}


def test_invalid_direction_raises():
    with pytest.raises(ValueError):
        traverse(CHAIN, "a", direction="sideways")

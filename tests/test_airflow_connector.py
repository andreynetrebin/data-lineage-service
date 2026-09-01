"""Тесты AirflowOpenLineageConnector."""
from lineage_service.connectors.airflow_openlineage import (
    AirflowOpenLineageConnector, normalize_uri,
)


class FakeQueryResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def query(self, sql, parameters=None):
        self.queries.append(sql)
        return FakeQueryResult(self._rows)


def test_normalize_uri_strips_prefix_and_colon():
    assert normalize_uri("clickhouse://:extractor.t1") == "extractor.t1"
    assert normalize_uri("clickhouse:///db.tbl") == "db.tbl"
    assert normalize_uri("clickhouse://extractor.x") == "extractor.x"
    assert normalize_uri("extractor.y") == "extractor.y"
    assert normalize_uri("") == ""
    assert normalize_uri(None) == ""


def test_collect_builds_dag_and_processed_by_produces_edges():
    rows = [
        ("dag1", "clickhouse://:extractor.in1", "clickhouse://:extractor.out1"),
        ("dag1", "clickhouse://:extractor.in2", "clickhouse://:extractor.out1"),
    ]
    graph = AirflowOpenLineageConnector(
        cfg={"clickhouse": {"database": "NetrebinAA"}},
        client=FakeClient(rows),
    ).collect()

    assert "airflow:dag:dag1" in graph.nodes
    assert "clickhouse:table:extractor.in1" in graph.nodes
    assert "clickhouse:table:extractor.in2" in graph.nodes
    assert "clickhouse:table:extractor.out1" in graph.nodes

    keys = {e.key for e in graph.edges}
    assert ("clickhouse:table:extractor.in1", "airflow:dag:dag1",
            "processed_by", "airflow") in keys
    assert ("clickhouse:table:extractor.in2", "airflow:dag:dag1",
            "processed_by", "airflow") in keys
    assert ("airflow:dag:dag1", "clickhouse:table:extractor.out1",
            "produces", "airflow") in keys


def test_empty_rows_returns_empty_graph():
    graph = AirflowOpenLineageConnector(
        cfg={"clickhouse": {"database": "NetrebinAA"}},
        client=FakeClient([]),
    ).collect()
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


def test_skips_rows_without_job_name():
    rows = [("", "clickhouse://:extractor.in", "clickhouse://:extractor.out")]
    graph = AirflowOpenLineageConnector(
        cfg={"clickhouse": {"database": "NetrebinAA"}},
        client=FakeClient(rows),
    ).collect()
    assert len(graph.nodes) == 0

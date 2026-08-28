"""Тесты коннектора каталога ClickHouse (system.databases/tables/columns)."""
from __future__ import annotations

from lineage_service.connectors.clickhouse_catalog import ClickHouseCatalogConnector


class FakeQueryResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    """Мок клиента clickhouse-connect для тестов."""

    def __init__(self, db_rows=None, table_rows=None, column_rows=None):
        self.db_rows = db_rows or []
        self.table_rows = table_rows or []
        self.column_rows = column_rows or []
        self.queries = []

    def query(self, sql, parameters=None):
        self.queries.append((sql, parameters))
        if "system.databases" in sql:
            return FakeQueryResult(self.db_rows)
        if "system.tables" in sql:
            return FakeQueryResult(self.table_rows)
        if "system.columns" in sql:
            return FakeQueryResult(self.column_rows)
        return FakeQueryResult([])


def test_collects_databases_tables_columns():
    client = FakeClient(
        db_rows=[("extractor",), ("NetrebinAA",)],
        table_rows=[
            ("extractor", "Номенклатура", "MergeTree", 1000),
            ("extractor", "РН_ДанныеПоПрибыли", "MergeTree", 5000),
        ],
        column_rows=[
            ("extractor", "Номенклатура", "Ссылка", "String", 1),
            ("extractor", "Номенклатура", "Наименование", "String", 2),
            ("extractor", "РН_ДанныеПоПрибыли", "Период", "Date", 1),
        ],
    )

    graph = ClickHouseCatalogConnector(cfg={}, client=client).collect()

    # Узлы
    assert "clickhouse:database:extractor" in graph.nodes
    assert "clickhouse:database:NetrebinAA" in graph.nodes
    assert "clickhouse:table:extractor.Номенклатура" in graph.nodes
    assert "clickhouse:table:extractor.РН_ДанныеПоПрибыли" in graph.nodes
    assert "clickhouse:column:extractor.Номенклатура.Ссылка" in graph.nodes
    assert "clickhouse:column:extractor.Номенклатура.Наименование" in graph.nodes
    assert "clickhouse:column:extractor.РН_ДанныеПоПрибыли.Период" in graph.nodes

    # Рёбра contains
    edges = {(e.src, e.dst, e.type) for e in graph.edges}
    assert ("clickhouse:database:extractor", "clickhouse:table:extractor.Номенклатура", "contains") in edges
    assert ("clickhouse:table:extractor.Номенклатура", "clickhouse:column:extractor.Номенклатура.Ссылка", "contains") in edges


def test_skips_system_databases():
    client = FakeClient(
        db_rows=[("system",), ("INFORMATION_SCHEMA",), ("extractor",)],
        table_rows=[("extractor", "t1", "MergeTree", 100)],
        column_rows=[("extractor", "t1", "col1", "String", 1)],
    )

    graph = ClickHouseCatalogConnector(cfg={}, client=client).collect()

    assert "clickhouse:database:system" not in graph.nodes
    assert "clickhouse:database:INFORMATION_SCHEMA" not in graph.nodes
    assert "clickhouse:database:extractor" in graph.nodes


def test_filters_databases_by_config():
    client = FakeClient(
        db_rows=[("extractor",), ("NetrebinAA",)],
        table_rows=[("extractor", "t1", "MergeTree", 100)],
        column_rows=[("extractor", "t1", "col1", "String", 1)],
    )

    graph = ClickHouseCatalogConnector(
        cfg={"databases": ["extractor"]},
        client=client,
    ).collect()

    # Проверяем, что в запрос к system.databases передан параметр databases
    db_query = [q for q in client.queries if "system.databases" in q[0]][0]
    assert db_query[1] == {"databases": ["extractor"]}


def test_table_props_include_engine_and_rows():
    client = FakeClient(
        db_rows=[("extractor",)],
        table_rows=[("extractor", "Номенклатура", "MergeTree", 1234)],
        column_rows=[],
    )

    graph = ClickHouseCatalogConnector(cfg={}, client=client).collect()

    table_node = graph.nodes["clickhouse:table:extractor.Номенклатура"]
    assert table_node.props["engine"] == "MergeTree"
    assert table_node.props["rows"] == 1234


def test_column_props_include_table_data_type_position():
    client = FakeClient(
        db_rows=[("extractor",)],
        table_rows=[("extractor", "t1", "MergeTree", 100)],
        column_rows=[("extractor", "t1", "col1", "String", 5)],
    )

    graph = ClickHouseCatalogConnector(cfg={}, client=client).collect()

    col_node = graph.nodes["clickhouse:column:extractor.t1.col1"]
    assert col_node.props["table"] == "extractor.t1"
    assert col_node.props["data_type"] == "String"
    assert col_node.props["position"] == 5


def test_empty_catalog_returns_empty_graph():
    client = FakeClient(db_rows=[], table_rows=[], column_rows=[])

    graph = ClickHouseCatalogConnector(cfg={}, client=client).collect()

    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0
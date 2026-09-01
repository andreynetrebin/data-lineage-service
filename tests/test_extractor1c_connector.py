"""Тесты Extractor1CConnector."""
from lineage_service.connectors.extractor1c import Extractor1CConnector


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


def test_empty_config_returns_empty_graph():
    graph = Extractor1CConnector(cfg={}, client=FakeClient([])).collect()
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


def test_collect_builds_source_1c_and_extracts_to_table():
    rows = [
        ("Объекты", "План/Факт показателей (HW)", "HW_ПлановыеПоказатели"),
        ("Объекты", "РН ДанныеПоПрибыли", "РН_ДанныеПоПрибыли"),
    ]
    graph = Extractor1CConnector(
        cfg={"table": "SmirinMR.`РасписаниеЭкстрактор`"},
        client=FakeClient(rows),
    ).collect()

    assert "1c:source_1c:План/Факт показателей (HW)" in graph.nodes
    assert "1c:source_1c:РН ДанныеПоПрибыли" in graph.nodes
    assert "clickhouse:table:extractor.HW_ПлановыеПоказатели" in graph.nodes
    assert "clickhouse:table:extractor.РН_ДанныеПоПрибыли" in graph.nodes
    assert graph.nodes["1c:source_1c:План/Факт показателей (HW)"].props["project"] == "Объекты"

    keys = {e.key for e in graph.edges}
    assert ("1c:source_1c:План/Факт показателей (HW)",
            "clickhouse:table:extractor.HW_ПлановыеПоказатели",
            "extracts_to", "1c") in keys
    assert ("1c:source_1c:РН ДанныеПоПрибыли",
            "clickhouse:table:extractor.РН_ДанныеПоПрибыли",
            "extracts_to", "1c") in keys


def test_skips_rows_with_missing_source_or_target():
    rows = [
        ("Объекты", "", "t1"),
        ("Объекты", "src", ""),
        ("Объекты", "src", "t2"),
    ]
    graph = Extractor1CConnector(
        cfg={"table": "SmirinMR.`РасписаниеЭкстрактор`"},
        client=FakeClient(rows),
    ).collect()
    # Только одна валидная пара
    assert len([e for e in graph.edges if e.type == "extracts_to"]) == 1

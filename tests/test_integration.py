"""Интеграционный тест: сквозной путь 1c -> ch_table -> source -> avatar -> field."""
from collections import deque

from lineage_service.connectors.airflow_openlineage import AirflowOpenLineageConnector
from lineage_service.connectors.datalens import DataLensConnector
from lineage_service.connectors.extractor1c import Extractor1CConnector
from lineage_service.model import Graph


class FakeQueryResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeCHClient:
    def __init__(self, rows_by_snippet):
        self._rows = rows_by_snippet

    def query(self, sql, parameters=None):
        for snippet, rows in self._rows.items():
            if snippet in sql:
                return FakeQueryResult(rows)
        return FakeQueryResult([])


class FakeDLClient:
    def __init__(self, entries, relations, datasets):
        self.entries = entries
        self.relations = relations
        self.datasets = datasets

    def get_entries_limit(self, scope, limit=500):
        return self.entries.get(scope, [])

    def get_entries_page(self, scope, page_size=100):
        return self.entries.get(scope, [])

    def get_relations(self, entry_id, direction):
        return self.relations.get(entry_id, {}).get(direction, [])

    def get_dataset(self, dataset_id):
        return self.datasets.get(dataset_id)


MINI_DATASET = {
    "id": "d1",
    "name": "Mini DS",
    "dataset": {
        "sources": [{"id": "src1", "source_type": "CH_TABLE", "title": "src1",
                     "parameters": {"db_name": "extractor", "table_name": "t1"}}],
        "source_avatars": [{"id": "av1", "title": "av1", "source_id": "src1",
                            "is_root": True}],
        "avatar_relations": [],
        "result_schema": [
            {"guid": "f1", "title": "F1", "type": "DIMENSION", "data_type": "string",
             "calc_mode": "direct", "avatar_id": "av1", "source": "col1"},
        ],
        "result_schema_aux": {"inter_dependencies": {"deps": []}},
    },
}


def _bfs_reachable(graph: Graph, start: str) -> set:
    adj = {}
    for e in graph.edges:
        adj.setdefault(e.src, []).append(e.dst)
    visited = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                q.append(nxt)
    return visited


def test_end_to_end_path_from_1c_to_field():
    # 1C: extractor.Источник -> extractor.t1
    ext1c = Extractor1CConnector(
        cfg={"table": "SmirinMR.`РасписаниеЭкстрактор`"},
        client=FakeCHClient({"РасписаниеЭкстрактор": [("Объекты", "Источник", "t1")]}),
    )

    # Airflow: нет данных
    airflow = AirflowOpenLineageConnector(
        cfg={"clickhouse": {"database": "NetrebinAA"}},
        client=FakeCHClient({}),
    )

    # DataLens: dataset d1 с source, читающим extractor.t1
    datalens = DataLensConnector(
        cfg={},
        client=FakeDLClient(
            entries={"dataset": [{"entryId": "d1", "scope": "dataset", "name": "DS"}],
                     "connection": [], "dash": [], "widget": []},
            relations={"d1": {}},
            datasets={"d1": MINI_DATASET},
        ),
    )

    # Собираем единый граф
    unified = Graph()
    for conn in (ext1c, airflow, datalens):
        unified.extend(conn.collect())

    # Сквозной путь: 1c:source_1c:Источник -> clickhouse:table:extractor.t1 ->
    #                datalens:source:src1 -> datalens:avatar:av1 -> datalens:field:f1
    start = "1c:source_1c:Источник"
    target = "datalens:field:f1"
    reachable = _bfs_reachable(unified, start)
    assert target in reachable, (
        f"Не найден путь от {start} до {target}. "
        f"Доступные узлы: {sorted(reachable)}"
    )

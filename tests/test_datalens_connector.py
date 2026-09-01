"""Тесты DataLensConnector (объекты + source/avatar/field/depends_on)."""
from lineage_service.connectors.datalens import DataLensConnector


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
            {"guid": "f2", "title": "F2", "type": "MEASURE", "data_type": "float",
             "calc_mode": "formula", "formula": "SUM([F1])", "avatar_id": "av1"},
        ],
        "result_schema_aux": {"inter_dependencies": {"deps": [
            {"dep_field_id": "f2", "ref_field_ids": ["f1"]}
        ]}},
    },
}


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


def test_collect_builds_object_level_edges():
    fake = FakeDLClient(
        entries={
            "connection": [{"entryId": "c1", "scope": "connection", "name": "CH"}],
            "dataset": [{"entryId": "d1", "scope": "dataset", "name": "DS"}],
            "dash": [{"entryId": "dash1", "scope": "dash", "name": "Dash"}],
            "widget": [{"entryId": "w1", "scope": "widget", "name": "W"}],
        },
        relations={
            "c1": {"to": ["d1"]},
            "d1": {"from": ["c1"], "to": ["dash1"]},
            "dash1": {"from": ["d1"]},
            "w1": {},
        },
        datasets={"d1": MINI_DATASET},
    )
    graph = DataLensConnector(cfg={}, client=fake).collect()

    # Объектный уровень
    assert "datalens:dataset:d1" in graph.nodes
    keys = {e.key for e in graph.edges}
    assert ("datalens:connection:c1", "datalens:dataset:d1", "feeds", "datalens") in keys
    assert ("datalens:dataset:d1", "datalens:dashboard:dash1", "feeds", "datalens") in keys


def test_collect_enriches_with_source_avatar_field_nodes():
    fake = FakeDLClient(
        entries={"dataset": [{"entryId": "d1", "scope": "dataset", "name": "DS"}],
                 "connection": [], "dash": [], "widget": []},
        relations={"d1": {}},
        datasets={"d1": MINI_DATASET},
    )
    graph = DataLensConnector(cfg={}, client=fake).collect()

    # Узлы source/avatar/field
    assert "datalens:source:src1" in graph.nodes
    assert "datalens:avatar:av1" in graph.nodes
    assert "datalens:field:f1" in graph.nodes
    assert "datalens:field:f2" in graph.nodes
    assert graph.nodes["datalens:avatar:av1"].props["is_root"] is True
    assert graph.nodes["datalens:field:f2"].props["calc_mode"] == "formula"

    # Рёбра обогащения
    keys = {e.key for e in graph.edges}
    assert ("clickhouse:table:extractor.t1", "datalens:source:src1",
            "feeds", "datalens") in keys
    assert ("datalens:source:src1", "datalens:dataset:d1",
            "feeds", "datalens") in keys
    assert ("datalens:source:src1", "datalens:avatar:av1",
            "uses", "datalens") in keys
    assert ("datalens:avatar:av1", "datalens:field:f1",
            "maps_to", "datalens") in keys
    assert ("datalens:field:f2", "datalens:field:f1",
            "depends_on", "datalens") in keys


def test_hidden_dataset_also_enriched():
    fake = FakeDLClient(
        entries={"connection": [{"entryId": "c1", "scope": "connection", "name": "CH"}],
                 "dataset": [{"entryId": "d1", "scope": "dataset", "name": "DS"}],
                 "dash": [{"entryId": "dash1", "scope": "dash", "name": "Dash"}],
                 "widget": []},
        relations={"d1": {"to": ["h1"]}, "dash1": {}, "c1": {}},
        datasets={"h1": {**MINI_DATASET, "id": "h1", "name": "Hidden"}},
    )
    graph = DataLensConnector(cfg={}, client=fake).collect()

    assert "datalens:dataset:h1" in graph.nodes
    assert graph.nodes["datalens:dataset:h1"].props["hidden"] is True
    # Обогащение тоже сработало для скрытого dataset
    assert "datalens:source:src1" in graph.nodes
    assert "datalens:avatar:av1" in graph.nodes

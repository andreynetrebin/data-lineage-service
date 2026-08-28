from lineage_service.connectors.datalens import DataLensConnector


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


def test_collect_builds_nodes_feeds_edges_and_discovers_hidden():
    fake = FakeDLClient(
        entries={
            "connection": [{"entryId": "c1", "scope": "connection", "name": "CH"}],
            "dataset": [{"entryId": "d1", "scope": "dataset", "name": "DS"}],
            "dash": [{"entryId": "dash1", "scope": "dash", "name": "Dash"}],
            "widget": [{"entryId": "w1", "scope": "widget", "name": "W"}],
        },
        relations={
            "c1": {"to": ["d1"]},
            "d1": {"from": ["c1"], "to": ["dash1", "h1"]},
            "dash1": {"from": ["d1"]},
            "w1": {},
        },
        datasets={"h1": {"id": "h1", "name": "Hidden DS"}},
    )
    graph = DataLensConnector(cfg={}, client=fake).collect()

    assert set(graph.nodes) == {
        "datalens:connection:c1", "datalens:dataset:d1",
        "datalens:dashboard:dash1", "datalens:dataset:h1", "datalens:widget:w1",
    }
    assert graph.nodes["datalens:dataset:h1"].props["hidden"] is True

    keys = {e.key for e in graph.edges}
    assert ("datalens:connection:c1", "datalens:dataset:d1", "feeds", "datalens") in keys
    assert ("datalens:dataset:d1", "datalens:dashboard:dash1", "feeds", "datalens") in keys
    assert ("datalens:dataset:d1", "datalens:dataset:h1", "feeds", "datalens") in keys
    assert len(graph.edges) == 3  # дедупликация встречных описаний связей
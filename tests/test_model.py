from lineage_service.model import Edge, Graph, Node, Snapshot, node_id


def test_node_id_format():
    assert node_id("clickhouse", "table", "extractor.t") == "clickhouse:table:extractor.t"


def test_add_node_merges_props():
    g = Graph()
    g.add_node(Node(id="a", system="s", type="t", name="n", props={"x": 1}))
    g.add_node(Node(id="a", system="s", type="t", name="", props={"y": 2}))
    assert len(g.nodes) == 1
    assert g.nodes["a"].props == {"x": 1, "y": 2}
    assert g.nodes["a"].name == "n"            # пустое имя не затирает


def test_add_edge_dedup():
    g = Graph()
    assert g.add_edge(Edge("a", "b", "feeds", "s")) is True
    assert g.add_edge(Edge("a", "b", "feeds", "s")) is False
    assert g.add_edge(Edge("a", "b", "contains", "s")) is True
    assert len(g.edges) == 2


def test_extend_merges_graphs():
    g1, g2 = Graph(), Graph()
    g1.add_node(Node("a", "s", "t", "a"))
    g2.add_node(Node("a", "s", "t", "a", props={"k": "v"}))
    g2.add_edge(Edge("a", "b", "feeds", "s"))
    g1.extend(g2)
    assert g1.nodes["a"].props == {"k": "v"}
    assert g1.stats == {"nodes": 1, "edges": 1}


def test_snapshot_finish():
    snap = Snapshot(id="x")
    assert snap.status == "running"
    snap.finish(3, 2)
    assert snap.status == "success"
    assert snap.stats == {"nodes": 3, "edges": 2}
    assert snap.finished_at is not None
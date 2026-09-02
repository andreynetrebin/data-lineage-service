"""Тесты diff снапшотов графа."""
from lineage_service.model import Edge, Node
from lineage_service.snapshot_diff import diff_graphs, summarize


def N(i, name=None):
    return Node(id=i, system="s", type="t", name=name or i)


def E(src, dst, t="feeds"):
    return Edge(src=src, dst=dst, type=t, system="s")


def test_detects_added_and_removed_nodes_and_edges():
    diff = diff_graphs([N("a"), N("b")], [E("a", "b")],
                       [N("b"), N("c")], [E("b", "c")])

    assert [n.id for n in diff.added_nodes] == ["c"]
    assert [n.id for n in diff.removed_nodes] == ["a"]
    assert [e.key for e in diff.added_edges] == [E("b", "c").key]
    assert [e.key for e in diff.removed_edges] == [E("a", "b").key]
    assert not diff.is_empty


def test_identical_graphs_is_empty():
    nodes = [N("a"), N("b")]
    edges = [E("a", "b")]
    diff = diff_graphs(nodes, edges, list(nodes), list(edges))
    assert diff.is_empty


def test_summarize_formats_lines():
    diff = diff_graphs([N("a", "Alpha")], [E("a", "b")],
                       [N("b", "Beta")], [])
    lines = summarize(diff)
    assert "+ node b (Beta)" in lines
    assert "- node a (Alpha)" in lines
    assert "- edge a -[feeds]-> b" in lines


def test_summarize_empty_diff():
    assert summarize(diff_graphs([], [], [], [])) == []

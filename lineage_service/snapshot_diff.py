"""Diff двух снапшотов графа: добавленные/удалённые узлы и рёбра + changelog."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .model import Edge, Node


@dataclass
class DiffResult:
    added_nodes: List[Node] = field(default_factory=list)
    removed_nodes: List[Node] = field(default_factory=list)
    added_edges: List[Edge] = field(default_factory=list)
    removed_edges: List[Edge] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added_nodes or self.removed_nodes
                    or self.added_edges or self.removed_edges)


def diff_graphs(old_nodes: List[Node], old_edges: List[Edge],
                new_nodes: List[Node], new_edges: List[Edge]) -> DiffResult:
    old_n = {n.id: n for n in old_nodes}
    new_n = {n.id: n for n in new_nodes}
    old_e = {e.key: e for e in old_edges}
    new_e = {e.key: e for e in new_edges}

    diff = DiffResult()
    diff.added_nodes = [new_n[i] for i in sorted(new_n.keys() - old_n.keys())]
    diff.removed_nodes = [old_n[i] for i in sorted(old_n.keys() - new_n.keys())]
    diff.added_edges = [new_e[k] for k in sorted(new_e.keys() - old_e.keys())]
    diff.removed_edges = [old_e[k] for k in sorted(old_e.keys() - new_e.keys())]
    return diff


def summarize(diff: DiffResult, limit: int = 20) -> List[str]:
    """Человекочитаемые строки changelog (с ограничением длины)."""
    if diff.is_empty:
        return []

    lines: List[str] = []
    for n in diff.added_nodes[:limit]:
        lines.append(f"+ node {n.id} ({n.name})")
    for n in diff.removed_nodes[:limit]:
        lines.append(f"- node {n.id} ({n.name})")
    for e in diff.added_edges[:limit]:
        lines.append(f"+ edge {e.src} -[{e.type}]-> {e.dst}")
    for e in diff.removed_edges[:limit]:
        lines.append(f"- edge {e.src} -[{e.type}]-> {e.dst}")

    total = (len(diff.added_nodes) + len(diff.removed_nodes)
             + len(diff.added_edges) + len(diff.removed_edges))
    shown = min(len(diff.added_nodes), limit) + min(len(diff.removed_nodes), limit) \
        + min(len(diff.added_edges), limit) + min(len(diff.removed_edges), limit)
    if total > shown:
        lines.append(f"… и ещё {total - shown} изменений")
    return lines

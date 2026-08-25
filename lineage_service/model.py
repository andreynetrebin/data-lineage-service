"""Доменная модель: узлы, рёбра, снапшоты и контейнер графа с дедупликацией."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def node_id(system: str, type_: str, key: str) -> str:
    """Естественный ключ узла: <система>:<тип>:<ключ>."""
    return f"{system}:{type_}:{key}"


@dataclass
class Node:
    id: str
    system: str      # datalens | clickhouse | airflow | 1c
    type: str        # dashboard | dataset | table | column | dag | source_1c | ...
    name: str
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    type: str        # feeds | contains | produces | processed_by | extracts_to | ...
    system: str
    props: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, str, str, str]:
        return (self.src, self.dst, self.type, self.system)


@dataclass
class Snapshot:
    id: str
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    status: str = "running"
    stats: Dict[str, int] = field(default_factory=dict)

    def finish(self, nodes: int, edges: int, status: str = "success") -> None:
        self.finished_at = datetime.now()
        self.status = status
        self.stats = {"nodes": nodes, "edges": edges}


@dataclass
class Graph:
    """Контейнер графа: слияние узлов по id, дедупликация рёбер по ключу."""
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)
    _edge_keys: set = field(default_factory=set)

    def add_node(self, node: Node) -> Node:
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return node
        existing.props.update(node.props)
        if not existing.name and node.name:
            existing.name = node.name
        return existing

    def add_edge(self, edge: Edge) -> bool:
        if edge.key in self._edge_keys:
            return False
        self._edge_keys.add(edge.key)
        self.edges.append(edge)
        return True

    def extend(self, other: "Graph") -> None:
        for node in other.nodes.values():
            self.add_node(node)
        for edge in other.edges:
            self.add_edge(edge)

    @property
    def stats(self) -> Dict[str, int]:
        return {"nodes": len(self.nodes), "edges": len(self.edges)}
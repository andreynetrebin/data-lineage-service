"""BFS-обход графа lineage: downstream (куда текут данные) / upstream (откуда пришли)."""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from .model import Edge


def build_adjacency(edges: List[Edge], direction: str = "downstream") -> Dict[str, List[Edge]]:
    adj: Dict[str, List[Edge]] = {}
    for e in edges:
        key = e.src if direction == "downstream" else e.dst
        adj.setdefault(key, []).append(e)
    return adj


def traverse(edges: List[Edge], start: str, direction: str = "downstream",
             max_depth: Optional[int] = None) -> Tuple[Set[str], List[Edge]]:
    """BFS от start. Возвращает (множество достижимых node_id, рёбра BFS-дерева)."""
    if direction not in ("downstream", "upstream"):
        raise ValueError("direction must be 'downstream' or 'upstream'")

    adj = build_adjacency(edges, direction)
    visited: Set[str] = {start}
    path_edges: List[Edge] = []
    queue = deque([(start, 0)])

    while queue:
        cur, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue
        for e in adj.get(cur, []):
            nxt = e.dst if direction == "downstream" else e.src
            if nxt not in visited:
                visited.add(nxt)
                path_edges.append(e)
                queue.append((nxt, depth + 1))

    return visited, path_edges

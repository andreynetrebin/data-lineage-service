"""JSON-sink: raw-слой снапшотов в файловой системе."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List

from ..model import Edge, Node, Snapshot
from .base import Sink


class JsonSink(Sink):
    """Сохраняет снапшот в `out_dir/snapshot_<id>.json`."""

    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def write(self, snapshot: Snapshot, nodes: List[Node], edges: List[Edge]) -> Path:
        path = self.out_dir / f"snapshot_{snapshot.id}.json"
        payload = {
            "snapshot": asdict(snapshot),
            "nodes": [asdict(n) for n in nodes],
            "edges": [asdict(e) for e in edges],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        return path
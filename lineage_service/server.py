"""FastAPI-сервис: /collect, /catalog/search, /lineage, /diff, /health."""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import cli, config
from .graph_traversal import traverse
from .model import Edge
from .sinks.clickhouse_sink import create_client

app = FastAPI(title="Data Catalog + Lineage Service", version="1.0.0")


class CollectResponse(BaseModel):
    status: str
    message: str


class LineageRequest(BaseModel):
    node: str
    direction: str = "downstream"
    depth: int = 10


class DiffRequest(BaseModel):
    from_snap: str
    to_snap: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/collect", response_model=CollectResponse)
def collect():
    try:
        cli.collect()
        return CollectResponse(status="success", message="Snapshot collected")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/catalog/search")
def catalog_search(q: str = ""):
    client = create_client(config.CLICKHOUSE)
    rows = client.query(
        "SELECT node_id, system, type, name FROM catalog_latest "
        "WHERE lower(name) LIKE %(q)s LIMIT 100",
        parameters={"q": f"%{q.lower()}%"},
    ).result_rows
    return [
        {"node_id": r[0], "system": r[1], "type": r[2], "name": r[3]}
        for r in rows
    ]


@app.post("/lineage")
def lineage(req: LineageRequest):
    client = create_client(config.CLICKHOUSE)
    rows = client.query("SELECT src, dst, type, system FROM edges_latest").result_rows
    edges = [Edge(src=r[0], dst=r[1], type=r[2], system=r[3]) for r in rows]

    visited, path_edges = traverse(
        edges, req.node, direction=req.direction, max_depth=req.depth
    )
    return {
        "start": req.node,
        "direction": req.direction,
        "depth": req.depth,
        "reachable_nodes": sorted(visited),
        "path_edges": [
            {"src": e.src, "dst": e.dst, "type": e.type}
            for e in path_edges[:50]
        ],
    }


@app.post("/diff")
def diff(req: DiffRequest):
    client = create_client(config.CLICKHOUSE)

    def load_nodes(sid):
        rows = client.query(
            "SELECT node_id, system, type, name, props FROM meta_nodes FINAL "
            "WHERE snapshot_id = %(sid)s",
            parameters={"sid": sid},
        ).result_rows
        return [
            {"id": r[0], "system": r[1], "type": r[2], "name": r[3]}
            for r in rows
        ]

    def load_edges(sid):
        rows = client.query(
            "SELECT src, dst, type, system FROM meta_edges FINAL "
            "WHERE snapshot_id = %(sid)s",
            parameters={"sid": sid},
        ).result_rows
        return [{"src": r[0], "dst": r[1], "type": r[2]} for r in rows]

    from .snapshot_diff import diff_graphs, summarize
    from .model import Node

    old_n = [Node(id=n["id"], system=n["system"], type=n["type"], name=n["name"])
             for n in load_nodes(req.from_snap)]
    new_n = [Node(id=n["id"], system=n["system"], type=n["type"], name=n["name"])
             for n in load_nodes(req.to_snap)]
    old_e = [Edge(src=e["src"], dst=e["dst"], type=e["type"], system="")
             for e in load_edges(req.from_snap)]
    new_e = [Edge(src=e["src"], dst=e["dst"], type=e["type"], system="")
             for e in load_edges(req.to_snap)]

    diff_result = diff_graphs(old_n, old_e, new_n, new_e)
    return {
        "from_snap": req.from_snap,
        "to_snap": req.to_snap,
        "summary": summarize(diff_result, limit=30),
        "stats": {
            "added_nodes": len(diff_result.added_nodes),
            "removed_nodes": len(diff_result.removed_nodes),
            "added_edges": len(diff_result.added_edges),
            "removed_edges": len(diff_result.removed_edges),
        },
    }


def run():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

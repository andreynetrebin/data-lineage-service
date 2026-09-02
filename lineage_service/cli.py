"""CLI: collect | lineage | diff | snapshots | serve."""
import argparse
import uuid

from . import config
from .alerts import TelegramAlerter
from .connectors import REGISTRY
from .graph_traversal import traverse
from .logging_setup import setup_logging
from .model import Edge, Node, Snapshot
from .sinks.clickhouse_sink import ClickHouseSink, create_client
from .sinks.json_sink import JsonSink
from .snapshot_diff import diff_graphs


def _build_sinks():
    sinks = []
    if config.SINKS.get("clickhouse", True):
        client = create_client(config.CLICKHOUSE)
        sinks.append(ClickHouseSink(client, config.BATCH_SIZE))
    if config.SINKS.get("json", True):
        sinks.append(JsonSink(config.OUT_DIR))
    return sinks


def _enabled_connectors():
    for name, src in config.SOURCES.items():
        cls = REGISTRY.get(name)
        if cls is None or not src.enabled:
            continue
        yield name, cls({**src.params, "clickhouse": config.CLICKHOUSE})


def collect():
    sinks = _build_sinks()
    snap = Snapshot(id=uuid.uuid4().hex[:12])
    nodes_by_id, edges = {}, []

    for name, conn in _enabled_connectors():
        print(f"\n=== Коннектор: {name} ===")
        g = conn.collect()
        print(f"  узлов={g.stats['nodes']}, рёбер={g.stats['edges']}")
        for node in g.nodes.values():
            if node.id in nodes_by_id:
                nodes_by_id[node.id].props.update(node.props)
            else:
                nodes_by_id[node.id] = node
        edges.extend(g.edges)

    seen, dedup_edges = set(), []
    for e in edges:
        key = e.key
        if key not in seen:
            seen.add(key)
            dedup_edges.append(e)

    nodes = list(nodes_by_id.values())
    for sink in sinks:
        sink.write(snap, nodes, dedup_edges)
    print(f"\nСнапшот {snap.id}: узлов={len(nodes)}, рёбер={len(dedup_edges)}")


def lineage(node: str, direction: str = "downstream", depth: int = 10):
    client = create_client(config.CLICKHOUSE)
    rows = client.query("SELECT src, dst, type, system FROM edges_latest").result_rows
    edges = [Edge(src=r[0], dst=r[1], type=r[2], system=r[3]) for r in rows]

    visited, path_edges = traverse(edges, node, direction=direction, max_depth=depth)
    print(f"Обход {direction} от {node} (depth={depth}):")
    print(f"  Достижимых узлов: {len(visited)}")
    for n in sorted(visited):
        print(f"    {n}")
    print(f"  Рёбер в пути: {len(path_edges)}")
    for e in path_edges[:20]:
        print(f"    {e.src} -[{e.type}]-> {e.dst}")


def diff(from_snap: str, to_snap: str):
    client = create_client(config.CLICKHOUSE)

    def load_nodes(sid):
        rows = client.query(
            "SELECT node_id, system, type, name, props FROM meta_nodes FINAL "
            "WHERE snapshot_id = %(sid)s", parameters={"sid": sid},
        ).result_rows
        return [Node(id=r[0], system=r[1], type=r[2], name=r[3], props={}) for r in rows]

    def load_edges(sid):
        rows = client.query(
            "SELECT src, dst, type, system, props FROM meta_edges FINAL "
            "WHERE snapshot_id = %(sid)s", parameters={"sid": sid},
        ).result_rows
        return [Edge(src=r[0], dst=r[1], type=r[2], system=r[3]) for r in rows]

    diff_result = diff_graphs(load_nodes(from_snap), load_edges(from_snap),
                              load_nodes(to_snap), load_edges(to_snap))
    if diff_result.is_empty:
        print("Изменений не обнаружено.")
        return

    from .snapshot_diff import summarize
    print(f"\nDiff {from_snap} -> {to_snap}:")
    for line in summarize(diff_result, limit=30):
        print(f"  {line}")

    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        alerter = TelegramAlerter(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        if alerter.notify_diff(diff_result,
                               title=f"Lineage diff {from_snap[:8]}→{to_snap[:8]}"):
            print("\n✓ Алерт отправлен в Telegram")


def snapshots():
    client = create_client(config.CLICKHOUSE)
    rows = client.query(
        "SELECT snapshot_id, started_at, status, stats FROM meta_snapshots FINAL "
        "ORDER BY started_at DESC LIMIT 20"
    ).result_rows
    for r in rows:
        print(f"{r[0]}  {r[1]}  {r[2]}  {r[3]}")


def serve():
    from .server import run
    run()


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    p = argparse.ArgumentParser(prog="lineage_service")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("collect", parents=[common], help="снять снапшот графа метаданных")
    sub.add_parser("snapshots", parents=[common], help="список снапшотов")

    lin = sub.add_parser("lineage", parents=[common], help="BFS-обход графа")
    lin.add_argument("node")
    lin.add_argument("--direction", choices=["downstream", "upstream"],
                     default="downstream")
    lin.add_argument("--depth", type=int, default=10)

    d = sub.add_parser("diff", parents=[common], help="diff двух снапшотов")
    d.add_argument("from_snap")
    d.add_argument("to_snap")

    sub.add_parser("serve", parents=[common], help="FastAPI-сервис")

    args = p.parse_args()
    setup_logging(args.log_level)

    if args.cmd == "collect":
        collect()
    elif args.cmd == "snapshots":
        snapshots()
    elif args.cmd == "lineage":
        lineage(args.node, args.direction, args.depth)
    elif args.cmd == "diff":
        diff(args.from_snap, args.to_snap)
    elif args.cmd == "serve":
        serve()
    else:
        p.print_help()


if __name__ == "__main__":
    main()

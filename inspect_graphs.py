"""Visual inspection tool for pickled networkx instance graphs.

Loads a pickle of List[networkx.DiGraph] -- as produced by instance_graphs.py
(step 2) or g_to_networkx.py -- and renders individual graphs as PNGs for
quick visual sanity-checking, e.g. before feeding them to step 3.

Since instance graphs are DAGs (each one is built from a single trace, so no
cycles), nodes are laid out in layers by causal depth (topological
generation) rather than with a generic spring layout: this reads left-to-right
as "what can happen after what", which is far more legible than a
force-directed layout once a graph has more than a handful of nodes.

Usage:
    python inspect_graphs.py PICKLE_PATH --list [--limit N]
    python inspect_graphs.py PICKLE_PATH --index N [-o FILE.png]
    python inspect_graphs.py PICKLE_PATH --all [--output-dir DIR] [--max N]
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx

DEFAULT_OUTPUT_DIR = Path("output/graph_inspection")


def load(path: Path) -> List[nx.DiGraph]:
    with open(path, "rb") as pickle_file:
        graphs = pickle.load(pickle_file)
    if not isinstance(graphs, list) or (graphs and not isinstance(graphs[0], nx.Graph)):
        raise ValueError(f"'{path}' does not contain a list of networkx graphs.")
    return graphs


def list_graphs(graphs: List[nx.DiGraph], limit: Optional[int] = None) -> None:
    print(f"{len(graphs)} graph(s) in file")
    for index, graph in enumerate(graphs):
        if limit is not None and index >= limit:
            print(f"  ... ({len(graphs) - limit} more, use --limit to see more)")
            break
        labels = [data.get("label", str(node)) for node, data in graph.nodes(data=True)]
        preview = ", ".join(labels[:5]) + (", ..." if len(labels) > 5 else "")
        print(
            f"  [{index}] {graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges: {preview}"
        )


def layered_positions(graph: nx.DiGraph) -> Dict[int, Tuple[float, float]]:
    """Left-to-right layout by topological depth; falls back to spring layout
    if the graph isn't a DAG (shouldn't happen for instance graphs, but the
    node/edge structure isn't guaranteed by this script's caller)."""
    try:
        generations = list(nx.topological_generations(graph))
    except nx.NetworkXUnfeasible:
        return nx.spring_layout(graph, seed=42)

    positions: Dict[int, Tuple[float, float]] = {}
    for x, layer in enumerate(generations):
        layer = sorted(layer)
        n = len(layer)
        for i, node in enumerate(layer):
            y = i - (n - 1) / 2
            positions[node] = (x, y)
    return positions


def render(graph: nx.DiGraph, output_path: Path, title: Optional[str] = None) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pos = layered_positions(graph)
    labels = {node: data.get("label", str(node)) for node, data in graph.nodes(data=True)}

    n_layers = len(set(x for x, _ in pos.values())) if pos else 1
    layer_sizes = (sum(1 for p in pos.values() if p[0] == x) for x in range(n_layers))
    max_layer_height = max(layer_sizes, default=1)
    # Long labels need real horizontal room per layer, not just per node --
    # this is tuned for typical activity-name lengths (~15-30 chars) rotated
    # at 60 degrees (below), rather than for node count alone.
    width = max(8, n_layers * 1.6)
    height = max(5, max_layer_height * 1.4)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(width, height))
    nx.draw_networkx_nodes(graph, pos, node_color="#a7c7e7", node_size=250)
    nx.draw_networkx_edges(graph, pos, arrows=True, arrowsize=10, node_size=250)
    ax = plt.gca()
    for node, (x, y) in pos.items():
        ax.text(
            x,
            y + 0.12,
            labels[node],
            fontsize=7,
            rotation=55,
            ha="left",
            va="bottom",
        )
    plt.axis("off")
    if title:
        plt.title(title)
    plt.margins(0.15)
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render pickled networkx instance graphs as PNGs for visual inspection."
    )
    parser.add_argument("pickle_path", help="Path to a pickle of List[networkx.DiGraph].")
    parser.add_argument(
        "--list", action="store_true", help="Print a summary of every graph and exit."
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="With --list, max graphs to print (default 20)."
    )
    parser.add_argument("--index", type=int, default=None, help="Render only graph at this index.")
    parser.add_argument(
        "-o", "--output", default=None, help="Output PNG path for --index (default: auto-named)."
    )
    parser.add_argument("--all", action="store_true", help="Render every graph in the file.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for --all renders (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=20,
        help="With --all, safety cap on how many graphs to render (default 20; "
        "large collections can mean thousands of PNGs otherwise).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    try:
        graphs = load(Path(args.pickle_path))

        if args.list or (not args.all and args.index is None):
            list_graphs(graphs, limit=args.limit)
            if not args.all and args.index is None:
                print("\nUse --index N to render one graph, or --all to render several.")
            return

        if args.index is not None:
            if not (0 <= args.index < len(graphs)):
                raise ValueError(f"--index {args.index} out of range (0..{len(graphs) - 1}).")
            output_path = Path(args.output) if args.output else Path(
                f"output/graph_inspection/graph_{args.index}.png"
            )
            render(graphs[args.index], output_path, title=f"Graph {args.index}")
            print(f"Rendered graph {args.index} -> '{output_path}'")

        if args.all:
            n = min(len(graphs), args.max)
            if len(graphs) > args.max:
                print(
                    f"Note: {len(graphs)} graphs found, rendering only the first {args.max} "
                    "(use --max to change this)."
                )
            output_dir = Path(args.output_dir)
            for index in range(n):
                render(
                    graphs[index], output_dir / f"graph_{index}.png", title=f"Graph {index}"
                )
            print(f"Rendered {n} graph(s) to '{output_dir}'")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

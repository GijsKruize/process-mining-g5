"""Render BIG instance graphs from output/instance_graphs.pkl.

Examples:
    python visualize_instance_graphs.py --graphs-path output_resource_50_model_original/instance_graphs.pkl
    python visualize_instance_graphs.py --graphs-path output_resource_50_model_original/instance_graphs.pkl --trace-ids 0,5,10
"""
import argparse
import pickle
from pathlib import Path

import networkx as nx


def parse_trace_ids(value, total):
    if value.lower() == "all":
        return list(range(total))
    trace_ids = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        trace_id = int(part)
        if trace_id < 0 or trace_id >= total:
            raise ValueError(f"trace id {trace_id} is outside 0..{total - 1}")
        trace_ids.append(trace_id)
    return trace_ids


def render_graph(graph, output_path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = {
        node: data.get("label", str(node))
        for node, data in graph.nodes(data=True)
    }
    width = max(8, min(18, graph.number_of_nodes() * 0.35))
    height = max(6, min(14, graph.number_of_nodes() * 0.25))
    plt.figure(figsize=(width, height))
    pos = nx.spring_layout(graph, seed=42, k=1.2) if graph.number_of_nodes() else {}
    nx.draw(
        graph,
        pos,
        labels=labels,
        with_labels=True,
        node_color="#b7d6f2",
        node_size=1100,
        font_size=6,
        arrows=True,
        arrowsize=12,
        edge_color="#555555",
    )
    plt.title(title)
    plt.savefig(output_path, bbox_inches="tight", dpi=160)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Render selected BIG instance graphs.")
    parser.add_argument("--graphs-path", default="output/instance_graphs.pkl")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--trace-ids", default="0",
                        help="Comma-separated 0-based trace ids, or 'all'")
    parser.add_argument("--max-graphs", type=int, default=20,
                        help="Safety cap when --trace-ids all is used")
    args = parser.parse_args()

    graphs_path = Path(args.graphs_path)
    output_dir = Path(args.output_dir) if args.output_dir else graphs_path.parent / "instance_graph_views"
    output_dir.mkdir(parents=True, exist_ok=True)

    with graphs_path.open("rb") as f:
        graphs = pickle.load(f)

    trace_ids = parse_trace_ids(args.trace_ids, len(graphs))
    if args.trace_ids.lower() == "all":
        trace_ids = trace_ids[:args.max_graphs]

    rows = []
    for trace_id in trace_ids:
        graph = graphs[trace_id]
        output_path = output_dir / f"trace_{trace_id}.png"
        render_graph(
            graph,
            output_path,
            f"Trace {trace_id} ({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges)",
        )
        rows.append({
            "trace_id": trace_id,
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "path": str(output_path),
        })

    print(f"Rendered {len(rows)} instance graph(s) to '{output_dir}'")
    for row in rows:
        print(f"trace {row['trace_id']}: {row['nodes']} nodes, {row['edges']} edges -> {row['path']}")


if __name__ == "__main__":
    main()

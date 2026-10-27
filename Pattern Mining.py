"""Mine patterns from the saved BIG instance graphs with SUBDUE."""
import pickle
import sys
from pathlib import Path

import networkx as nx


PROJECT_ROOT = Path(__file__).resolve().parent
INSTANCE_GRAPH_DIR = PROJECT_ROOT / "output" / "instance graphs"
GRAPHS_PATH = INSTANCE_GRAPH_DIR / "instance_graphs_pm4py.pkl"
PATTERN_OUTPUT_DIR = PROJECT_ROOT / "output" / "patterns"
SUBDUE_DIR = PROJECT_ROOT / "subdue"
MIN_PATTERN_EDGES = 3
MAX_PATTERN_EDGES = 8


def build_subdue_graph(graphs):
    """Combine all trace graphs into one disconnected SUBDUE graph."""
    sys.path.insert(0, str(SUBDUE_DIR))
    import Graph

    combined = Graph.Graph()
    entries = []
    for graph in graphs:
        for node, data in graph.nodes(data=True):
            entries.append({
                "vertex": {
                    "id": str(node),
                    "attributes": {"label": str(data["label"])},
                }
            })
        for source, target in graph.edges:
            entries.append({
                "edge": {
                    "id": f"{source}-{target}",
                    "source": str(source),
                    "target": str(target),
                    "directed": "true",
                    "attributes": {"label": "next"},
                }
            })
    combined.load_from_json(entries)
    return combined


def pattern_to_networkx(definition):
    """Convert a native SUBDUE pattern definition to NetworkX."""
    graph = nx.DiGraph()
    for node_id, vertex in definition.vertices.items():
        graph.add_node(node_id, label=vertex.attributes.get("label", str(node_id)))
    for edge in definition.edges.values():
        graph.add_edge(edge.source.id, edge.target.id)
    return graph


def run_subdue(graphs):
    """Run the provided paper implementation."""
    sys.path.insert(0, str(SUBDUE_DIR))
    import Parameters
    import Subdue

    parameters = Parameters.Parameters()
    parameters.beamWidth = 4
    parameters.iterations = 3
    parameters.minSize = 2
    parameters.maxSize = 0
    parameters.numBest = 20
    parameters.overlap = "vertex"
    subdue_graph = build_subdue_graph(graphs)
    parameters.limit = min(len(subdue_graph.edges) // 2, 1000)
    parameters.set_defaults_for_graph(subdue_graph)
    print("Running the provided SUBDUE implementation...", flush=True)
    iterations = Subdue.Subdue(parameters, subdue_graph)
    return iterations[0] if iterations else []


def export_subdue_patterns(patterns, graphs):
    """Save pattern statistics, the trace matrix, and pattern PNGs."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    PATTERN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    matrix = {}
    for rank, pattern in enumerate(patterns, start=1):
        pattern_id = f"P{rank}"
        pattern_graph = pattern_to_networkx(pattern.definition)
        traces = sorted({
            int(str(vertex.id).split("_", 1)[0][1:])
            for instance in pattern.instances
            for vertex in instance.vertices
            if str(vertex.id).startswith("g")
        })
        rows.append({
            "pattern": pattern_id,
            "edges": pattern_graph.number_of_edges(),
            "instances": len(pattern.instances),
            "traces": len(traces),
            "support_pct": round(100 * len(traces) / len(graphs), 2),
            "subdue_value": pattern.value,
        })
        matrix[pattern_id] = {
            index: int(index in traces) for index in range(len(graphs))
        }
        plt.figure(figsize=(8, 5))
        node_labels = nx.get_node_attributes(pattern_graph, "label")
        nx.draw_networkx(
            pattern_graph, node_size=900, font_size=7,
            labels=node_labels, arrows=True, with_labels=True,
        )
        plt.title(f"{pattern_id}: {len(traces)} traces, value={pattern.value:.3f}")
        plt.savefig(PATTERN_OUTPUT_DIR / f"{pattern_id}.png",
                    dpi=150, bbox_inches="tight")
        plt.close()

    pd.DataFrame(rows).to_csv(PATTERN_OUTPUT_DIR / "patterns.csv", index=False)
    pd.DataFrame(matrix).fillna(0).astype(int).to_csv(
        PATTERN_OUTPUT_DIR / "trace_pattern_matrix.csv", index_label="trace"
    )
    return rows


def main():
    if not GRAPHS_PATH.exists():
        raise FileNotFoundError(
            f"Run 'Instance Graph Mining.py' first; missing {GRAPHS_PATH}"
        )
    with open(GRAPHS_PATH, "rb") as file:
        graphs = pickle.load(file)

    patterns = run_subdue(graphs)
    rows = export_subdue_patterns(patterns, graphs)
    print(f"Mined {len(rows)} patterns in {PATTERN_OUTPUT_DIR}")


if __name__ == "__main__":
    main()

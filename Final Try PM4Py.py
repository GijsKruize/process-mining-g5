"""Faster PM4Py experiment.

This is a separate copy of the pipeline.  The process model is mined from
plain activity names, while BIG still receives activity-resource names.
That keeps the organizational detail in the graphs without making the model
contain thousands of resource-specific activities.
"""
import importlib.util
import os
import pickle
import sys
from pathlib import Path

import pm4py
import networkx as nx
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pyspark.sql import SparkSession


PROJECT_ROOT = Path(__file__).resolve().parent
DATASET_PATH = PROJECT_ROOT / "data/BPI2017Denied_10pct.xes"
BIG_LOG_PATH = PROJECT_ROOT / "BPI2017Denied_pm4py.xes"
BIG_OUTPUT_PATH = PROJECT_ROOT / "graph_pm4py.g"
GRAPHS_PATH = PROJECT_ROOT / "instance_graphs_pm4py.pkl"
PATTERN_OUTPUT_DIR = PROJECT_ROOT / "output" / "patterns"
SUBDUE_DIR = PROJECT_ROOT / "subdue"
SELECTED_ATTRIBUTE = "org:resource"
NOISE_THRESHOLD = 0.4
CPU_COUNT = 10


def load_pipeline_helpers():
    """Reuse only the functions from Final Try.py; never import OLD."""
    path = PROJECT_ROOT / "Final Try.py"
    spec = importlib.util.spec_from_file_location("final_try_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_subdue_graph(graphs):
    """Combine all trace graphs into one disconnected graph for SUBDUE."""
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
    """Run the provided paper implementation and return its native patterns."""
    sys.path.insert(0, str(SUBDUE_DIR))
    import Parameters
    import Subdue

    parameters = Parameters.Parameters()
    parameters.beamWidth = 4
    parameters.iterations = 1
    parameters.minSize = 2
    parameters.maxSize = 4
    parameters.numBest = 20
    parameters.overlap = "none"
    subdue_graph = build_subdue_graph(graphs)
    parameters.limit = min(len(subdue_graph.edges) // 2, 1000)
    parameters.set_defaults_for_graph(subdue_graph)
    print("Running the provided SUBDUE implementation...", flush=True)
    iterations = Subdue.Subdue(parameters, subdue_graph)
    return iterations[0] if iterations else []


def export_subdue_patterns(patterns, graphs):
    """Save every native SUBDUE pattern and its support as a PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

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
        nx.draw_networkx(pattern_graph, node_size=900, font_size=7,
                         arrows=True, with_labels=True)
        plt.title(f"{pattern_id}: {len(traces)} traces, value={pattern.value:.3f}")
        plt.savefig(PATTERN_OUTPUT_DIR / f"{pattern_id}.png",
                    dpi=150, bbox_inches="tight")
        plt.close()

    import pandas as pd
    pd.DataFrame(rows).to_csv(PATTERN_OUTPUT_DIR / "patterns.csv", index=False)
    pd.DataFrame(matrix).fillna(0).astype(int).to_csv(
        PATTERN_OUTPUT_DIR / "trace_pattern_matrix.csv", index_label="trace"
    )
    return rows


def main():
    helpers = load_pipeline_helpers()
    import BIG

    print("Loading event log...", flush=True)
    event_log = log_converter.apply(
        xes_importer.apply(str(DATASET_PATH)),
        variant=log_converter.Variants.TO_DATA_FRAME,
    )
    print("Available attributes:")
    print("\n".join(f"- {column}" for column in event_log.columns))
    if SELECTED_ATTRIBUTE not in event_log.columns:
        raise ValueError(f"Unknown attribute: {SELECTED_ATTRIBUTE}")

    event_log["activity_selectedAttribute"] = (
        event_log["concept:name"].fillna("UNKNOWN").astype(str)
        + "_"
        + event_log[SELECTED_ATTRIBUTE].fillna("UNKNOWN").astype(str)
    )

    # BIG keeps the resource-task label.
    big_log = event_log.copy()
    big_log["concept:name"] = big_log["activity_selectedAttribute"]
    big_event_log = log_converter.apply(
        big_log, variant=log_converter.Variants.TO_EVENT_LOG
    )
    xes_exporter.apply(big_event_log, str(BIG_LOG_PATH))

    # BIG must receive a model with the same labels as its event log.
    # Therefore the model is mined from the resource-enriched event log too.
    print("Discovering the PM4Py Inductive Miner model...", flush=True)
    net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(
        big_event_log, noise_threshold=NOISE_THRESHOLD
    )
    print("Petri-net discovery complete.", flush=True)

    trace_count = len(big_event_log)
    workers = min(CPU_COUNT, trace_count) or 1
    chunk_size = (trace_count + workers - 1) // workers
    chunks = []
    for start in range(0, trace_count, chunk_size):
        output = PROJECT_ROOT / f"graph_pm4py_chunk_{start}.g"
        output.unlink(missing_ok=True)
        chunks.append((
            start, min(start + chunk_size, trace_count), str(output),
            initial_marking, final_marking, net, str(BIG_LOG_PATH)
        ))

    print(f"Running BIG with Spark local[{workers}]", flush=True)
    java17 = Path("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
    if java17.is_dir():
        os.environ.setdefault("JAVA_HOME", str(java17))
    spark = (
        SparkSession.builder.master(f"local[{workers}]")
        .appName("BIG-PM4Py")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    spark.sparkContext.parallelize(chunks, workers).map(BIG.run_big_chunk).collect()
    spark.stop()

    BIG_OUTPUT_PATH.write_text(
        "\n".join(Path(chunk[2]).read_text() for chunk in chunks)
    )
    for chunk in chunks:
        Path(chunk[2]).unlink()

    graphs = helpers.read_big_graphs(BIG_OUTPUT_PATH)
    for index, graph in enumerate(graphs):
        graph.graph["graph_index"] = index
    with open(GRAPHS_PATH, "wb") as file:
        pickle.dump(graphs, file)

    # Step 3: run the provided SUBDUE implementation and export every pattern.
    subdue_patterns = run_subdue(graphs)
    rows = export_subdue_patterns(subdue_patterns, graphs)
    print(f"Generated {len(graphs)} graphs and mined {len(rows)} patterns")
    return graphs


if __name__ == "__main__":
    main()

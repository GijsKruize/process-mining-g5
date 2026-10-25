import os
import pickle
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Spark 3/4 requires a supported Java runtime; use Homebrew Java 17 when present.
JAVA_17 = Path("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
if JAVA_17.is_dir():
    os.environ.setdefault("JAVA_HOME", str(JAVA_17))

import networkx as nx
from pyspark.sql import SparkSession
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer

import BIG


# Change this value to analyse another event-log attribute.
SELECTED_ATTRIBUTE = "org:resource"
PROJECT_ROOT = Path(__file__).resolve().parent
DATASET_PATH = PROJECT_ROOT / "data/BPI2017Denied_10pct.xes"
BIG_LOG_PATH = PROJECT_ROOT / "BPI2017Denied_selected.xes"
BIG_OUTPUT_PATH = PROJECT_ROOT / "graph.g"
GRAPHS_PATH = PROJECT_ROOT / "instance_graphs.pkl"
PATTERN_OUTPUT_DIR = PROJECT_ROOT / "patterns"
GOLD_STANDARD_PATH = PROJECT_ROOT / "data/artificial_gold_standard.csv"
NOISE_THRESHOLD = 0.4
CPU_COUNT = 10


def read_big_graphs(path):
    """Convert BIG's XP/v/e text blocks to uniquely identified graphs."""
    graphs = []
    graph = None
    for line in Path(path).read_text().splitlines():
        parts = line.split(maxsplit=3)
        if not parts:
            continue
        if parts[0] == "XP":
            graph = nx.DiGraph()
            graphs.append(graph)
        elif graph is not None and parts[0] == "v":
            node_id, label = parts[1], parts[2]
            graph.add_node(f"g{len(graphs) - 1}_n{node_id}", label=label)
        elif graph is not None and parts[0] == "e":
            source = f"g{len(graphs) - 1}_n{parts[1]}"
            target = f"g{len(graphs) - 1}_n{parts[2]}"
            label = parts[3] if len(parts) > 3 else ""
            graph.add_edge(source, target, label=label)
    return graphs


def save_graphs(graphs, path):
    """Save the NetworkX graphs so SUBDUE and later steps can reuse them."""
    for index, graph in enumerate(graphs):
        graph.graph["graph_index"] = index
    with open(path, "wb") as file:
        pickle.dump(graphs, file)


def show_graph(graph, path):
    """Small helper for visualising one graph without a complicated UI."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    nx.draw_networkx(graph, with_labels=True, node_size=500, font_size=6)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()


@dataclass
class Pattern:
    """A small mined pattern and the traces in which it occurs."""

    pattern_id: str
    graph: nx.DiGraph
    traces: list


def path_patterns(graph, length=3):
    """Return directed label paths of ``length`` edges in one instance graph."""
    labels = nx.get_node_attributes(graph, "label")
    paths = set()

    def extend(nodes):
        if len(nodes) == length + 1:
            paths.add(tuple(labels[node] for node in nodes))
            return
        for successor in graph.successors(nodes[-1]):
            extend(nodes + [successor])

    for node in graph:
        extend([node])
    return paths


def mine_patterns(graphs, number=20, length=3):
    """Mine frequent connected subgraphs as directed paths.

    This is deliberately small and readable: a path is a valid connected
    subgraph, support is the number of traces containing it, and each path is
    converted to a NetworkX graph for the next steps.
    """
    counts = Counter()
    occurrences = {}
    for trace_id, graph in enumerate(graphs):
        paths = path_patterns(graph, length)
        counts.update(paths)
        for path in paths:
            occurrences.setdefault(path, []).append(trace_id)

    patterns = []
    for rank, (path, _) in enumerate(counts.most_common(number), start=1):
        pattern_graph = nx.DiGraph()
        for node, label in enumerate(path):
            pattern_graph.add_node(node, label=label)
            if node:
                pattern_graph.add_edge(node - 1, node)
        patterns.append(Pattern(f"P{rank}", pattern_graph, occurrences[path]))
    return patterns


def pattern_statistics(patterns, graphs):
    """Write support and the required trace x pattern matrix."""
    rows = []
    matrix = {}
    for pattern in patterns:
        rows.append({
            "pattern": pattern.pattern_id,
            "nodes": pattern.graph.number_of_nodes(),
            "edges": pattern.graph.number_of_edges(),
            "support": len(pattern.traces),
            "support_pct": round(100 * len(pattern.traces) / len(graphs), 2),
        })
        matrix[pattern.pattern_id] = {
            trace: int(trace in pattern.traces) for trace in range(len(graphs))
        }
    table = __import__("pandas").DataFrame(rows)
    trace_matrix = __import__("pandas").DataFrame(matrix).fillna(0).astype(int)
    trace_matrix.index.name = "trace"
    return table, trace_matrix


def evaluate_patterns(patterns, gold_path):
    """Compare discovered edge labels with a manually prepared CSV gold standard."""
    import pandas as pd

    gold = pd.read_csv(gold_path)
    gold_edges = set()
    for edges in gold["edges"]:
        for edge in edges.split(";"):
            source, target = (part.strip() for part in edge.split("->"))
            gold_edges.add((source, target))

    discovered_edges = {
        (pattern.graph.nodes[source]["label"], target_data["label"])
        for pattern in patterns
        for source, target in pattern.graph.edges
        for target_data in [pattern.graph.nodes[target]]
    }
    precision = len(discovered_edges & gold_edges) / len(discovered_edges) \
        if discovered_edges else 0
    recall = len(discovered_edges & gold_edges) / len(gold_edges) if gold_edges else 0
    return precision, recall


def main():
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

    big_log = event_log.copy()
    big_log["concept:name"] = big_log["activity_selectedAttribute"]
    pm4py_log = log_converter.apply(
        big_log,
        variant=log_converter.Variants.TO_EVENT_LOG,
    )
    xes_exporter.apply(pm4py_log, str(BIG_LOG_PATH))

    print("Discovering the Inductive Miner Infrequent model (single-process step)...",
          flush=True)
    net, initial_marking, final_marking = inductive_miner.apply(
        pm4py_log,
        variant=inductive_miner.Variants.IMf,
        parameters={"noise_threshold": NOISE_THRESHOLD},
    )
    print("Petri-net discovery complete.", flush=True)

    n_traces = len(pm4py_log)
    worker_count = min(CPU_COUNT, n_traces) or 1
    chunk_size = (n_traces + worker_count - 1) // worker_count
    chunks = []
    for start in range(0, n_traces, chunk_size):
        output_path = PROJECT_ROOT / f"graph_chunk_{start}.g"
        output_path.unlink(missing_ok=True)
        chunks.append((
            start,
            min(start + chunk_size, n_traces),
            str(output_path),
            initial_marking,
            final_marking,
            net,
            str(BIG_LOG_PATH),
        ))

    print(f"Running BIG with Spark local[{worker_count}]", flush=True)
    spark = (
        SparkSession.builder
        .master(f"local[{worker_count}]")
        .appName("BIG-instance-graphs")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    spark_chunks = spark.sparkContext.parallelize(chunks, worker_count)
    spark_chunks.map(BIG.run_big_chunk).collect()
    spark.stop()

    BIG_OUTPUT_PATH.write_text(
        "\n".join(Path(chunk[2]).read_text() for chunk in chunks)
    )
    for chunk in chunks:
        Path(chunk[2]).unlink()

    instance_graphs = read_big_graphs(BIG_OUTPUT_PATH)
    save_graphs(instance_graphs, GRAPHS_PATH)
    print(f"Generated {len(instance_graphs)} instance graphs")

    # Step 3: mine frequent connected path subgraphs and calculate support.
    patterns = mine_patterns(instance_graphs, number=20, length=3)
    pattern_table, trace_pattern_matrix = pattern_statistics(patterns, instance_graphs)
    PATTERN_OUTPUT_DIR.mkdir(exist_ok=True)
    pattern_table.to_csv(PATTERN_OUTPUT_DIR / "patterns.csv", index=False)
    trace_pattern_matrix.to_csv(PATTERN_OUTPUT_DIR / "trace_pattern_matrix.csv")
    print(f"Mined {len(patterns)} patterns")

    if patterns:
        show_graph(patterns[0].graph, PROJECT_ROOT / "pattern_1.png")

    # Evaluation is optional because the assignment requires a manually made
    # gold-standard file. Put it at gold_standard.csv when it is available.
    if GOLD_STANDARD_PATH.exists():
        precision, recall = evaluate_patterns(patterns, GOLD_STANDARD_PATH)
        print(f"Precision: {precision:.3f}")
        print(f"Recall: {recall:.3f}")

    return instance_graphs


if __name__ == "__main__":
    instance_graphs = main()

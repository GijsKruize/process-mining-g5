"""Create and save the BIG instance graphs."""
import os
import pickle
from pathlib import Path

import networkx as nx
import pm4py
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pyspark.sql import SparkSession

import BIG


PROJECT_ROOT = Path(__file__).resolve().parent
DATASET_PATH = PROJECT_ROOT / "data/BPI2017Denied(3).xes"
INSTANCE_GRAPH_DIR = PROJECT_ROOT / "output" / "instance graphs"
BIG_LOG_PATH = INSTANCE_GRAPH_DIR / "BPI2017Denied_pm4py.xes"
BIG_OUTPUT_PATH = INSTANCE_GRAPH_DIR / "graph_pm4py.g"
GRAPHS_PATH = INSTANCE_GRAPH_DIR / "instance_graphs_pm4py.pkl"
PETRI_NET_PATH = INSTANCE_GRAPH_DIR / "petri_net_pm4py.pnml"
SELECTED_ATTRIBUTE = "org:resource"
NOISE_THRESHOLD = 0.4
CPU_COUNT = 10


def read_big_graphs(path):
    """Convert BIG's XP/v/e text blocks into uniquely identified graphs."""
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


def main():
    INSTANCE_GRAPH_DIR.mkdir(parents=True, exist_ok=True)

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
    big_event_log = log_converter.apply(
        big_log, variant=log_converter.Variants.TO_EVENT_LOG
    )
    xes_exporter.apply(big_event_log, str(BIG_LOG_PATH))

    print("Discovering the PM4Py Inductive Miner model...", flush=True)
    net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(
        big_event_log, noise_threshold=NOISE_THRESHOLD
    )
    pm4py.write_pnml(
        net, initial_marking, final_marking, str(PETRI_NET_PATH)
    )
    print("Petri-net discovery complete.", flush=True)

    trace_count = len(big_event_log)
    workers = min(CPU_COUNT, trace_count) or 1
    chunk_size = (trace_count + workers - 1) // workers
    chunks = []
    for start in range(0, trace_count, chunk_size):
        output = INSTANCE_GRAPH_DIR / f"graph_pm4py_chunk_{start}.g"
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

    graphs = read_big_graphs(BIG_OUTPUT_PATH)
    for index, graph in enumerate(graphs):
        graph.graph["graph_index"] = index
    with open(GRAPHS_PATH, "wb") as file:
        pickle.dump(graphs, file)

    print(f"Saved {len(graphs)} instance graphs in {INSTANCE_GRAPH_DIR}")


if __name__ == "__main__":
    main()

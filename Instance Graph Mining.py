"""Create and save the BIG instance graphs."""
import os
import pickle
from collections import Counter
from pathlib import Path

import networkx as nx
import pandas as pd
import pm4py
from pm4py.algo.organizational_mining.roles import algorithm as role_discovery
from pm4py.algo.organizational_mining.roles.variants.pandas import Parameters as RoleParameters
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
RESOURCE_ROLES_PATH = INSTANCE_GRAPH_DIR / "resource_roles.csv"
SELECTED_ATTRIBUTE = "org:resource"
NOISE_THRESHOLD = 0.4
CPU_COUNT = 10

# Replace every resource by its role (pm4py role discovery, Burattin et al. 2013)
GROUP_ROLES = True
ROLES_THRESHOLD = 0.65
# Drop the lifecycle step of the W- work items and merge directly repeated labels
COLLAPSE_LIFECYCLE = True
LIFECYCLE_SUFFIX = r"-(schedule|start|suspend|resume|complete|ate-abort|withdraw)$"


def ask_yes_no(question):
    """Ask a y/n question in the terminal, re-prompting until answered clearly."""
    while True:
        answer = input(f"{question} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


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


def discover_roles(event_log):
    """Map every resource to its dominant role: the discovered role in which it
    performs most of its events. Role_1 is the role with the most events."""
    frame = pd.DataFrame({
        "resource": event_log[SELECTED_ATTRIBUTE].fillna("UNKNOWN").astype(str),
        "activity": event_log["concept:name"].astype(str),
    })
    roles = role_discovery.apply(frame, parameters={
        RoleParameters.RESOURCE_KEY: "resource",
        RoleParameters.ACTIVITY_KEY: "activity",
        RoleParameters.ROLES_THRESHOLD_PARAMETER: ROLES_THRESHOLD,
    })
    dominant = {}  # resource -> (role index, events in that role); first role wins a tie
    for role_index, (_, resource_counts) in enumerate(roles):
        for resource, events in resource_counts.items():
            if resource not in dominant or events > dominant[resource][1]:
                dominant[resource] = (role_index, events)

    events_per_resource = Counter(frame["resource"])
    events_per_role = Counter()
    for resource, (role_index, _) in dominant.items():
        events_per_role[role_index] += events_per_resource[resource]
    ranked = sorted(events_per_role, key=lambda index: (-events_per_role[index], index))
    role_names = {index: f"Role_{rank}" for rank, index in enumerate(ranked, start=1)}
    return {resource: role_names[role_index] for resource, (role_index, _) in dominant.items()}


def relabel_events(event_log, role_mapping=None):
    """Add the `activity_selectedAttribute` label: roles first, then the lifecycle collapse.

    A role change inside a work item is a handover and stays two events."""
    event_log = event_log.copy()
    activity = event_log["concept:name"].fillna("UNKNOWN").astype(str)
    value = event_log[SELECTED_ATTRIBUTE].fillna("UNKNOWN").astype(str)
    if role_mapping is not None:
        value = value.map(role_mapping).fillna("UNKNOWN")
    if COLLAPSE_LIFECYCLE:
        is_work_item = activity.str.startswith("W-")
        activity = activity.where(~is_work_item, activity.str.replace(LIFECYCLE_SUFFIX, "", regex=True))
    event_log["activity_selectedAttribute"] = activity + "_" + value

    if COLLAPSE_LIFECYCLE:
        case = event_log["case:concept:name"]
        repeated = (event_log["activity_selectedAttribute"] == event_log["activity_selectedAttribute"].shift()) & (case == case.shift())
        event_log = event_log[~repeated].reset_index(drop=True)
    return event_log


def load_big_event_log():
    """(Re)build the attribute-relabeled event log needed for discovery/BIG, from the raw dataset."""
    print("Loading event log...", flush=True)
    event_log = log_converter.apply(
        xes_importer.apply(str(DATASET_PATH)),
        variant=log_converter.Variants.TO_DATA_FRAME,
    )
    print("Available attributes:")
    print("\n".join(f"- {column}" for column in event_log.columns))
    if SELECTED_ATTRIBUTE not in event_log.columns:
        raise ValueError(f"Unknown attribute: {SELECTED_ATTRIBUTE}")

    role_mapping = None
    if GROUP_ROLES:
        role_mapping = discover_roles(event_log)
        pd.DataFrame(sorted(role_mapping.items()), columns=["resource", "role"]).to_csv(
            RESOURCE_ROLES_PATH, index=False
        )
        print(f"Grouped {len(role_mapping)} resources into {len(set(role_mapping.values()))} roles "
              f"(saved to {RESOURCE_ROLES_PATH})", flush=True)

    events_before = len(event_log)
    event_log = relabel_events(event_log, role_mapping)
    print(f"{event_log['activity_selectedAttribute'].nunique()} distinct labels, "
          f"{len(event_log)} of {events_before} events kept", flush=True)

    big_log = event_log.copy()
    big_log["concept:name"] = big_log["activity_selectedAttribute"]
    return log_converter.apply(big_log, variant=log_converter.Variants.TO_EVENT_LOG)


def main():
    INSTANCE_GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    big_event_log = None  # lazily (re)loaded only when a step actually needs it in memory

    # Step 1: relabeled BIG log
    if BIG_LOG_PATH.exists() and ask_yes_no(
        f"Found existing relabeled log at {BIG_LOG_PATH}. Use it instead of rebuilding?"
    ):
        print(f"Reusing relabeled log at {BIG_LOG_PATH}", flush=True)
    else:
        big_event_log = load_big_event_log()
        xes_exporter.apply(big_event_log, str(BIG_LOG_PATH))
        print(f"Saved relabeled log to {BIG_LOG_PATH}", flush=True)

    # Step 2: Petri net discovery
    if PETRI_NET_PATH.exists() and ask_yes_no(
        f"Found existing Petri net at {PETRI_NET_PATH}. Use it instead of mining a new one?"
    ):
        print(f"Reusing Petri net at {PETRI_NET_PATH}", flush=True)
        net, initial_marking, final_marking = pm4py.read_pnml(str(PETRI_NET_PATH))
    else:
        if big_event_log is None:
            big_event_log = log_converter.apply(
                xes_importer.apply(str(BIG_LOG_PATH)),
                variant=log_converter.Variants.TO_EVENT_LOG,
            )
        print("Discovering the PM4Py Inductive Miner model...", flush=True)
        net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(
            big_event_log, noise_threshold=NOISE_THRESHOLD
        )
        pm4py.write_pnml(net, initial_marking, final_marking, str(PETRI_NET_PATH))
        print("Petri-net discovery complete.", flush=True)

    # Step 3: BIG algorithm run (the slow, Spark-parallelized step)
    if BIG_OUTPUT_PATH.exists() and ask_yes_no(
        f"Found existing BIG output at {BIG_OUTPUT_PATH}. Use it instead of regenerating with Spark?"
    ):
        print(f"Reusing BIG output at {BIG_OUTPUT_PATH}", flush=True)
    else:
        if big_event_log is None:
            big_event_log = log_converter.apply(
                xes_importer.apply(str(BIG_LOG_PATH)),
                variant=log_converter.Variants.TO_EVENT_LOG,
            )
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

    # Step 4: parse the .g file into networkx graphs and pickle them
    if GRAPHS_PATH.exists() and ask_yes_no(
        f"Found existing instance graphs pickle at {GRAPHS_PATH}. Use it instead of rebuilding it?"
    ):
        print(f"Reusing instance graphs pickle at {GRAPHS_PATH}", flush=True)
        with open(GRAPHS_PATH, "rb") as file:
            graphs = pickle.load(file)
    else:
        graphs = read_big_graphs(BIG_OUTPUT_PATH)
        for index, graph in enumerate(graphs):
            graph.graph["graph_index"] = index
        with open(GRAPHS_PATH, "wb") as file:
            pickle.dump(graphs, file)

    print(f"Saved {len(graphs)} instance graphs in {INSTANCE_GRAPH_DIR}")


if __name__ == "__main__":
    main()

"""Evaluate the 10% log against the saved Petri net and instance graphs.

Petri-net conformance uses PM4Py alignments.  Instance graphs do not have a
standard PM4Py alignment implementation, so their event labels are compared
with the graph's topological event order using the same edit-distance idea.
"""
import csv
import copy
import json
import pickle
from pathlib import Path

import networkx as nx
import pm4py
from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.petri_net.importer import importer as pnml_importer


PROJECT_ROOT = Path(__file__).resolve().parent
LOG_PATH = PROJECT_ROOT / "data/BPI2017Denied_10pct.xes"
PETRI_NET_PATH = (
    PROJECT_ROOT / "output" / "instance graphs" / "petri_net_pm4py.pnml"
)
INSTANCE_GRAPHS_PATH = (
    PROJECT_ROOT / "output" / "instance graphs" / "instance_graphs_pm4py.pkl"
)
OUTPUT_DIR = PROJECT_ROOT / "output" / "alignment_evaluation"


def enriched_trace(trace):
    """Use the same activity-resource labels as the saved instance graphs."""
    return [
        f"{event.get('concept:name', 'UNKNOWN')}_"
        f"{event.get('org:resource', 'UNKNOWN')}"
        for event in trace
    ]


def edit_distance(left, right):
    """Return insert/delete/substitute distance and alignment statistics."""
    previous = list(range(len(right) + 1))
    for left_index, left_value in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_value in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_value != right_value),
            ))
        previous = current

    distance = previous[-1]
    matches = sum(value in right for value in left)
    return distance, matches


def graph_sequence(graph):
    """Return the graph's event labels in topological order."""
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("An instance graph is cyclic; cannot define its order.")
    return [
        graph.nodes[node]["label"]
        for node in nx.topological_sort(graph)
    ]


def evaluate_instance_graphs(log, graphs):
    """Compare every log trace with its corresponding saved instance graph."""
    if len(log) != len(graphs):
        raise ValueError(
            f"Expected one graph per trace, got {len(log)} traces and "
            f"{len(graphs)} graphs."
        )

    results = []
    for index, (trace, graph) in enumerate(zip(log, graphs)):
        observed = enriched_trace(trace)
        generated = graph_sequence(graph)
        distance, matches = edit_distance(observed, generated)
        results.append({
            "trace": index,
            "events": len(observed),
            "graph_nodes": len(generated),
            "edit_distance": distance,
            "matching_labels": matches,
            "fitness": round(
                1 - distance / max(len(observed), len(generated)), 6
            ),
        })
    return results


def evaluate_petri_net(log):
    """Calculate PM4Py alignment fitness for resource-enriched traces."""
    net, initial_marking, final_marking = pnml_importer.apply(
        str(PETRI_NET_PATH)
    )
    enriched_log = copy.deepcopy(log)
    for trace in enriched_log:
        for event, label in zip(trace, enriched_trace(trace)):
            event["concept:name"] = label
    alignments_result = alignments.apply(
        enriched_log, net, initial_marking, final_marking
    )
    results = []
    for index, alignment in enumerate(alignments_result):
        results.append({
            "trace": index,
            "cost": alignment.get("cost"),
            "fitness": alignment.get("fitness"),
            "queued_states": alignment.get("visited_states"),
        })
    return results


def summary(results, name):
    fitness = [row["fitness"] for row in results]
    return {
        "model": name,
        "traces": len(results),
        "mean_fitness": round(sum(fitness) / len(fitness), 6),
        "perfect_fitness": sum(value == 1 for value in fitness),
        "min_fitness": min(fitness),
        "max_fitness": max(fitness),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log = xes_importer.apply(str(LOG_PATH))
    print(f"Loaded {len(log)} traces from {LOG_PATH}")

    print("Calculating Petri-net alignments...", flush=True)
    petri_results = evaluate_petri_net(log)
    print("Calculating instance-graph alignments...", flush=True)
    with open(INSTANCE_GRAPHS_PATH, "rb") as file:
        graphs = pickle.load(file)
    graph_results = evaluate_instance_graphs(log, graphs)

    summaries = [
        summary(petri_results, "Petri net"),
        summary(graph_results, "Instance graphs"),
    ]
    with open(OUTPUT_DIR / "summary.json", "w") as file:
        json.dump(summaries, file, indent=2)
    for name, rows in [
        ("petri_net_alignments.csv", petri_results),
        ("instance_graph_alignments.csv", graph_results),
    ]:
        with open(OUTPUT_DIR / name, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    print(json.dumps(summaries, indent=2))
    print(f"Saved alignment results in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

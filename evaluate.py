"""Step 4: evaluate the mined patterns against a manually curated gold standard.

The assignment asks us to check how well the approach discovers real
behavioral patterns, using precision/recall against a gold standard we
build ourselves by inspecting the log. There's no way to automate writing
that gold standard -- gold_standard.csv is a small starting example, edit
it for your own attribute/analysis.

Each line in the gold standard file is one pattern you believe is a real
behavioral pattern, written as a comma-separated list of activity labels
(the same labels SUBDUE matched on, i.e. relabeled_log.csv's concept:name).
A mined pattern counts as a match if it has the exact same set of activity
labels as a gold pattern.
"""
import argparse
import csv
from pathlib import Path


def load_gold_standard(path):
    patterns = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            row = [activity.strip() for activity in row if activity.strip()]
            if row and not row[0].startswith("#"):
                patterns.append(frozenset(row))
    return patterns


def mined_pattern_signatures(patterns, union_graph):
    signatures = []
    for pattern in patterns:
        representative = pattern[0]
        labels = {union_graph.nodes[n]["label"] for n in representative["nodes"]}
        signatures.append(frozenset(labels))
    return signatures


def evaluate(mined_signatures, gold_standard):
    """Precision/recall on exact activity-set matches between mined and gold patterns."""
    matched_mined = sum(1 for m in mined_signatures if m in gold_standard)
    matched_gold = sum(1 for g in gold_standard if g in mined_signatures)
    precision = matched_mined / len(mined_signatures) if mined_signatures else 0.0
    recall = matched_gold / len(gold_standard) if gold_standard else 0.0
    return precision, recall


def main():
    parser = argparse.ArgumentParser(description="Step 4: evaluate mined patterns with precision/recall.")
    parser.add_argument("--gold-standard", default="gold_standard.csv")
    parser.add_argument("--patterns-path", default="output/patterns.pkl")
    parser.add_argument("--graphs-path", default="output/instance_graphs.pkl")
    args = parser.parse_args()

    import pickle

    with open(args.patterns_path, "rb") as f:
        patterns = pickle.load(f)
    with open(args.graphs_path, "rb") as f:
        graphs = pickle.load(f)

    import networkx as nx
    union_graph = nx.DiGraph()
    for graph in graphs:
        union_graph.add_nodes_from(graph.nodes(data=True))

    gold_standard = load_gold_standard(args.gold_standard)
    mined_signatures = mined_pattern_signatures(patterns, union_graph)

    precision, recall = evaluate(mined_signatures, gold_standard)
    print(f"Gold standard patterns: {len(gold_standard)}")
    print(f"Mined patterns:         {len(mined_signatures)}")
    print(f"Precision: {precision:.2f}")
    print(f"Recall:    {recall:.2f}")


if __name__ == "__main__":
    main()

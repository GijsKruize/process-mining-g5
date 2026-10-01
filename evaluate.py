"""Step 4: evaluate mined patterns against a curated gold standard.

The assignment asks us to check how well the approach discovers behavioral
patterns with precision/recall. The preferred gold-standard format is now
edge based, because behavior is about relations, not just the set of labels:

    Activity_A->Activity_B
    Activity_A->Activity_B,Activity_B->Activity_C

For backwards compatibility, rows without ``->`` are still read as the old
comma-separated activity-label sets.
"""
import argparse
import csv


def _parse_edge(cell):
    source, _, target = cell.partition("->")
    if not source or not target:
        raise ValueError(f"Invalid edge gold-standard cell: {cell!r}")
    return source.strip(), target.strip()


def load_gold_standard(path):
    patterns = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            cells = [cell.strip() for cell in row if cell.strip()]
            if not cells or cells[0].startswith("#"):
                continue
            if any("->" in cell for cell in cells):
                patterns.append({
                    "kind": "edges",
                    "items": frozenset(_parse_edge(cell) for cell in cells),
                })
            else:
                patterns.append({
                    "kind": "labels",
                    "items": frozenset(cells),
                })
    return patterns


def _node_label(union_graph, node):
    if node not in union_graph:
        return str(node)
    return union_graph.nodes[node].get("label", str(node))


def mined_pattern_signatures(patterns, union_graph):
    signatures = []
    for pattern in patterns:
        representative = pattern[0] if pattern else {"nodes": [], "edges": []}
        labels = frozenset(
            _node_label(union_graph, node)
            for node in representative["nodes"]
        )
        edges = frozenset(
            (_node_label(union_graph, source), _node_label(union_graph, target))
            for source, target in representative["edges"]
        )
        signatures.append({
            "labels": labels,
            "edges": edges,
        })
    return signatures


def _signature_matches_gold(signature, gold_pattern):
    if gold_pattern["kind"] == "edges":
        return signature["edges"] == gold_pattern["items"]
    return signature["labels"] == gold_pattern["items"]


def evaluate(mined_signatures, gold_standard):
    """Precision/recall on exact matches between mined and gold patterns."""
    matched_mined = sum(
        1
        for signature in mined_signatures
        if any(_signature_matches_gold(signature, gold) for gold in gold_standard)
    )
    matched_gold = sum(
        1
        for gold in gold_standard
        if any(_signature_matches_gold(signature, gold) for signature in mined_signatures)
    )
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
    import pattern_mining

    with open(args.patterns_path, "rb") as f:
        patterns = pickle.load(f)
    with open(args.graphs_path, "rb") as f:
        graphs = pickle.load(f)

    union_graph, _ = pattern_mining.PatternMiner.build_union_graph(graphs)
    gold_standard = load_gold_standard(args.gold_standard)
    mined_signatures = mined_pattern_signatures(patterns, union_graph)

    precision, recall = evaluate(mined_signatures, gold_standard)
    n_edge_gold = sum(1 for pattern in gold_standard if pattern["kind"] == "edges")
    n_label_gold = len(gold_standard) - n_edge_gold
    print(f"Gold standard patterns: {len(gold_standard)} "
          f"({n_edge_gold} edge-based, {n_label_gold} label-set)")
    print(f"Mined patterns:         {len(mined_signatures)}")
    print(f"Precision: {precision:.2f}")
    print(f"Recall:    {recall:.2f}")


if __name__ == "__main__":
    main()

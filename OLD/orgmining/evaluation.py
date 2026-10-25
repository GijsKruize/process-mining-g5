"""Evaluation: compare discovered patterns with a hand-made gold standard.

The gold standard (``gold_standard/*.csv``) lists the work practices we expect
in the log, each as a small labelled graph (``"A_Role_1 -> B_Role_1; ..."``).

Matching (labels must be equal, including the role):

* a gold pattern is **found** if at least one discovered pattern contains it
  as a subgraph (every gold edge present, between nodes with the same labels);
* a discovered pattern is **correct** if it contains at least one gold
  pattern, or is itself part of a gold pattern.

    precision = correct discovered patterns / discovered patterns
    recall    = found gold patterns / gold patterns

The same is reported at **edge level** (an edge is a pair of labels): which
share of the discovered edges is in the gold standard, and which share of the
gold edges was discovered. This gives partial credit to patterns that cover
most, but not all, of a gold pattern.

As a simple comparison method, ``FrequentPathBaseline`` returns the most
frequent paths of a fixed length in the instance graphs (comparable to
sequential pattern mining, which ignores parallelism and compression).
"""
from collections import Counter
from dataclasses import dataclass

import networkx as nx
import pandas as pd
from networkx.algorithms.isomorphism import DiGraphMatcher


def parse_edges(text):
    """'A -> B; B -> C' -> networkx.DiGraph with a 'label' on every node."""
    graph = nx.DiGraph()
    for part in text.split(";"):
        source, target = (label.strip() for label in part.split("->"))
        graph.add_node(source, label=source)
        graph.add_node(target, label=target)
        graph.add_edge(source, target)
    return graph


def label_edges(graph):
    """The edges of a graph as (source label, target label) pairs."""
    labels = nx.get_node_attributes(graph, "label")
    return {(labels[u], labels[v]) for u, v in graph.edges}


def contains(big, small):
    """True if ``small`` occurs in ``big``: all its edges, between equally labelled nodes."""
    if small.number_of_nodes() > big.number_of_nodes():
        return False
    if not label_edges(small) <= label_edges(big):      # quick necessary check
        return False
    matcher = DiGraphMatcher(big, small, node_match=lambda a, b: a["label"] == b["label"])
    return matcher.subgraph_is_monomorphic()


@dataclass
class GoldPattern:
    gold_id: str
    name: str
    graph: nx.DiGraph


class GoldStandard:
    def __init__(self, patterns):
        self.patterns = patterns

    @classmethod
    def from_csv(cls, path):
        table = pd.read_csv(path)
        return cls([GoldPattern(row.id, row.name, parse_edges(row.edges))
                    for row in table.itertuples()])

    @property
    def edges(self):
        return set().union(*(label_edges(p.graph) for p in self.patterns))


@dataclass
class EvaluationResult:
    method: str
    n_patterns: int
    precision: float
    recall: float
    edge_precision: float
    edge_recall: float
    found: list          # gold ids that were found
    per_pattern: pd.DataFrame

    @property
    def f1(self):
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0

    def as_row(self):
        return {"method": self.method, "patterns": self.n_patterns,
                "precision": round(self.precision, 3), "recall": round(self.recall, 3),
                "f1": round(self.f1, 3), "edge_precision": round(self.edge_precision, 3),
                "edge_recall": round(self.edge_recall, 3), "gold_found": ", ".join(self.found)}


def evaluate(method, discovered, gold):
    """``discovered``: list of (pattern id, networkx graph with node 'label')."""
    rows, found = [], set()
    for pattern_id, graph in discovered:
        contained_gold = [g.gold_id for g in gold.patterns if contains(graph, g.graph)]
        part_of_gold = [g.gold_id for g in gold.patterns if contains(g.graph, graph)]
        found.update(contained_gold)
        rows.append({"pattern": pattern_id, "contains_gold": ", ".join(contained_gold),
                     "part_of_gold": ", ".join(part_of_gold),
                     "correct": bool(contained_gold or part_of_gold)})
    per_pattern = pd.DataFrame(rows)
    discovered_edges = set().union(*(label_edges(g) for _, g in discovered)) if discovered else set()
    gold_edges = gold.edges
    hits = discovered_edges & gold_edges
    return EvaluationResult(
        method=method,
        n_patterns=len(discovered),
        precision=per_pattern["correct"].mean() if rows else 0.0,
        recall=len(found) / len(gold.patterns),
        edge_precision=len(hits) / len(discovered_edges) if discovered_edges else 0.0,
        edge_recall=len(hits) / len(gold_edges),
        found=sorted(found, key=lambda gold_id: int(gold_id[1:])),
        per_pattern=per_pattern)


class FrequentPathBaseline:
    """Most frequent label paths of ``length`` edges, counted once per trace."""

    def __init__(self, length=3):
        self.length = length

    def paths(self, graph):
        labels = nx.get_node_attributes(graph, "label")
        found = set()

        def extend(path):
            if len(path) == self.length + 1:
                found.add(tuple(labels[node] for node in path))
                return
            for successor in graph.successors(path[-1]):
                extend(path + [successor])

        for node in graph:
            extend([node])
        return found

    def discover(self, graphs, top):
        counts = Counter()
        for graph in graphs:
            counts.update(self.paths(graph))
        patterns = []
        for rank, (path, _) in enumerate(counts.most_common(top), start=1):
            graph = nx.DiGraph()
            for index, label in enumerate(path):          # node ids by position: repeats allowed
                graph.add_node(index, label=label)
            graph.add_edges_from((i, i + 1) for i in range(len(path) - 1))
            patterns.append((f"B{rank}", graph))
        return patterns


def load_mined_patterns(step3_dir):
    """Discovered patterns of a step 3 run as (pattern id, graph) pairs."""
    import pickle
    from pathlib import Path
    with open(Path(step3_dir) / "patterns.pkl", "rb") as file:
        return [(p.pattern_id, p.definition) for p in pickle.load(file)]


def run_evaluation(runs, gold_csv, graphs, output_dir, baseline_lengths=(2, 3, 4)):
    """Evaluate step 3 runs and the frequent-path baseline; write tables and a figure.

    ``runs``: {method name: step 3 output folder}. The baseline returns as many
    patterns as the largest run, so the comparison is fair.
    """
    from pathlib import Path

    gold = GoldStandard.from_csv(gold_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for method, step3_dir in runs.items():
        results.append(evaluate(method, load_mined_patterns(step3_dir), gold))
    n_patterns = max(result.n_patterns for result in results)
    for length in baseline_lengths:
        baseline = FrequentPathBaseline(length).discover(graphs, n_patterns)
        results.append(evaluate(f"frequent paths ({length} edges)", baseline, gold))

    table = pd.DataFrame([result.as_row() for result in results])
    table.to_csv(output_dir / "evaluation.csv", index=False)
    details = pd.concat([result.per_pattern.assign(method=result.method) for result in results])
    details.to_csv(output_dir / "evaluation_per_pattern.csv", index=False)
    plot_evaluation(table, output_dir / "evaluation.png")
    return table


def plot_evaluation(table, path):
    """Grouped horizontal bars: precision, recall and F1 per method."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .pattern_report import GRID_COLOUR, MUTED_COLOUR, _style_axes
    from .visualization import CATEGORICAL_COLOURS, TEXT_COLOUR

    measures = [("precision", "Precision"), ("recall", "Recall"), ("f1", "F1")]
    data = table.iloc[::-1].reset_index(drop=True)
    height = 0.26
    fig, ax = plt.subplots(figsize=(7.5, 0.8 + 0.85 * len(data)))
    for i, (column, label) in enumerate(measures):
        positions = [y + (1 - i) * height for y in range(len(data))]
        ax.barh(positions, data[column], height=height - 0.03, color=CATEGORICAL_COLOURS[i],
                label=label)
        for y, value in zip(positions, data[column]):
            ax.text(value + 0.01, y, f"{value:.2f}", va="center", fontsize=7, color=TEXT_COLOUR)
    ax.set_yticks(range(len(data)))
    ax.set_yticklabels(data["method"], fontsize=8, color=TEXT_COLOUR)
    ax.set_xlim(0, 1.1)
    ax.set_xlabel("score (pattern level, against the gold standard)", fontsize=8,
                  color=MUTED_COLOUR)
    ax.xaxis.grid(True, color=GRID_COLOUR, linewidth=0.8)
    ax.set_axisbelow(True)
    _style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, loc="lower right", frameon=False, fontsize=8)
    ax.set_title("Discovered patterns against the gold standard", fontsize=10,
                 color=TEXT_COLOUR, loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path

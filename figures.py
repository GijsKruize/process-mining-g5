"""Figures of one chosen case for the paper and the poster, like Figure 1 of
the assignment: the case's trace, its instance graph, and the behavioral
patterns that occur in it.

Run with::

    python figures.py

Pick which results to use (BPI 2017 from ``output/``, or one of the two
synthetic evaluations from ``output/synthetic validation/``), then:

    L  list candidate cases: short cases with parallel work and several
       patterns make the clearest example - pick one by hand from this list
    C  all figures of one case (by case id)
    P  one pattern, highlighted in the shortest cases that contain it

It only reads what steps 1 and 2 of ``main.py`` saved; nothing is recomputed
or overwritten there. Figures go to ``<results>/figures/``.
"""
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

from main import (
    INSTANCE_GRAPH_DIR, PATTERN_OUTPUT_DIR, PROJECT_ROOT, SYNTHETIC_OUTPUT_DIR,
    PatternMiningStep, contains_pattern, pattern_occurrences, split_label,
)

RESULTS = {
    "1": ("BPI 2017 (output/)", INSTANCE_GRAPH_DIR, PATTERN_OUTPUT_DIR,
          PROJECT_ROOT / "output" / "figures"),
    **{key: (f"Synthetic log, {evaluation} (output/synthetic validation/{evaluation}/)",
             SYNTHETIC_OUTPUT_DIR / evaluation / "instance graphs",
             SYNTHETIC_OUTPUT_DIR / evaluation / "patterns",
             SYNTHETIC_OUTPUT_DIR / evaluation / "figures")
       for key, evaluation in (("2", "eval1_known_roles"), ("3", "eval2_full_pipeline"))},
}


class CaseFigures:
    """Loads one set of results (instance graphs + SUBDUE patterns) and
    draws figures of chosen cases and patterns."""

    MAX_PATTERNS_IN_FIGURE = 3

    def __init__(self, graph_dir, pattern_dir, figure_dir):
        mining_step = PatternMiningStep(Path(graph_dir) / "instance_graphs_pm4py.pkl", pattern_dir)
        with open(mining_step.graphs_path, "rb") as file:
            self.graphs = pickle.load(file)
        self.case_ids = PatternMiningStep.case_ids(self.graphs)
        self.graph_of_case = dict(zip(self.case_ids, self.graphs))
        self.patterns = {f"P{rank}": mining_step.pattern_to_networkx(pattern.definition)
                         for rank, pattern in enumerate(mining_step.load_patterns(), start=1)}
        self.statistics = pd.read_csv(Path(pattern_dir) / "patterns.csv").set_index("pattern")
        self.matrix = self.trace_pattern_matrix(Path(pattern_dir) / "trace_pattern_matrix.csv")
        self.figure_dir = Path(figure_dir)
        self.values = PatternMiningStep.all_values(self.graphs)

    def trace_pattern_matrix(self, path):
        """Step 2's matrix (rows: case ids), or computed here for results
        saved before step 2 wrote it by case id."""
        if path.exists():
            matrix = pd.read_csv(path, dtype={"case_id": str})
            if "case_id" in matrix.columns and set(matrix["case_id"]) == set(self.case_ids):
                return matrix.set_index("case_id")
        return pd.DataFrame(
            {name: [int(contains_pattern(graph, pattern)) for graph in self.graphs]
             for name, pattern in self.patterns.items()},
            index=pd.Index(self.case_ids, name="case_id"))

    # -- describing cases ------------------------------------------------

    @staticmethod
    def trace_labels(graph):
        """The case's events in log order: BIG numbers the nodes of a graph
        by the position of their event in the trace ('g<i>_n<position>')."""
        nodes = sorted(graph.nodes, key=lambda node: int(str(node).rsplit("_n", 1)[-1]))
        return [graph.nodes[node]["label"] for node in nodes]

    def patterns_in(self, case_id):
        row = self.matrix.loc[case_id]
        return [name for name in self.matrix.columns if row[name]]

    def candidates(self):
        """One row per case, best example candidates first: some parallel
        work, many patterns, few events."""
        variant_size = pd.Series([tuple(self.trace_labels(graph)) for graph in self.graphs]).value_counts()
        rows = []
        for case_id, graph in zip(self.case_ids, self.graphs):
            labels = tuple(self.trace_labels(graph))
            found = self.patterns_in(case_id)
            rows.append({
                "case_id": case_id,
                "events": graph.number_of_nodes(),
                "parallel_splits": sum(1 for node in graph if graph.out_degree(node) > 1),
                "patterns": len(found),
                "which": " ".join(found[:8]) + (" ..." if len(found) > 8 else ""),
                "cases_same_variant": int(variant_size[labels]),
            })
        frame = pd.DataFrame(rows)
        frame["has_parallel"] = frame["parallel_splits"] > 0
        return frame.sort_values(["has_parallel", "patterns", "events"],
                                 ascending=[False, False, True]).drop(columns="has_parallel")

    # -- drawing ---------------------------------------------------------

    @staticmethod
    def layers(graph):
        """How many nodes wide the drawing is (long graphs wrap, see draw_graph)."""
        return min(max(1, len(list(nx.topological_generations(graph)))), PatternMiningStep.WRAP_LAYERS)

    def draw(self, *args, **kwargs):
        """``PatternMiningStep.draw_graph`` with one colour per value across all figures."""
        PatternMiningStep.draw_graph(*args, all_values=self.values, **kwargs)

    def draw_trace(self, graph, case_id, ax):
        """The trace as a table (left column of Figure 1)."""
        rows = [[index, *split_label(label)]
                for index, label in enumerate(self.trace_labels(graph), start=1)]
        ax.axis("off")
        table = ax.table(cellText=rows, colLabels=["#", "activity", "value"],
                         loc="upper center", cellLoc="left", colLoc="left")
        table.auto_set_font_size(False)
        table.set_fontsize(7)
        table.auto_set_column_width([0, 1, 2])
        ax.set_title(f"Trace of case {case_id}", fontsize=9)

    def pattern_title(self, name):
        row = self.statistics.loc[name]
        return f"{name}: support {row['support']} cases ({row['support_pct']}%)"

    def occurrence(self, graph, name):
        """The nodes of the first occurrence of pattern ``name`` in ``graph``."""
        mapping = next(pattern_occurrences(graph, self.patterns[name]), {})
        return set(mapping)

    def case_figures(self, case_id):
        graph = self.graph_of_case[case_id]
        found = self.patterns_in(case_id)
        output_dir = self.figure_dir / str(case_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        draw = self.draw

        figure, ax = plt.subplots(figsize=(4.5, 0.25 * graph.number_of_nodes() + 1))
        self.draw_trace(graph, case_id, ax)
        figure.savefig(output_dir / "trace.png", dpi=150, bbox_inches="tight")
        plt.close(figure)

        draw(graph, f"Instance graph of case {case_id}", output_dir / "instance_graph.png")
        for name in found:
            draw(self.patterns[name], self.pattern_title(name), output_dir / f"{name}.png")
            draw(graph, f"{self.pattern_title(name)} - highlighted in case {case_id}",
                 output_dir / f"{name}_in_case.png", highlight=self.occurrence(graph, name))

        # Figure 1: trace -> instance graph -> patterns
        # Each panel is as wide as the number of layers it shows, ~1.9 inch per layer.
        shown = found[:self.MAX_PATTERNS_IN_FIGURE]
        widths = [4.0, 1.9 * self.layers(graph),
                  1.9 * max([self.layers(self.patterns[name]) for name in shown] or [1])]
        figure = plt.figure(figsize=(sum(widths), max(6.0, 2.6 * max(1, len(shown)))))
        grid = figure.add_gridspec(max(1, len(shown)), 3, width_ratios=widths)
        self.draw_trace(graph, case_id, figure.add_subplot(grid[:, 0]))
        draw(graph, f"Instance graph of case {case_id}", ax=figure.add_subplot(grid[:, 1]))
        for row, name in enumerate(shown):
            draw(self.patterns[name], self.pattern_title(name), ax=figure.add_subplot(grid[row, 2]))
        figure.savefig(output_dir / "figure1.png", dpi=130, bbox_inches="tight")
        plt.close(figure)

        print(f"Case {case_id}: {graph.number_of_nodes()} events, patterns {', '.join(found) or 'none'}")
        print(f"Figures saved in {output_dir}")

    def pattern_figures(self, name, examples=3):
        output_dir = self.figure_dir / name
        output_dir.mkdir(parents=True, exist_ok=True)
        self.draw(self.patterns[name], self.pattern_title(name),
                                     output_dir / f"{name}.png")
        cases = [case for case in self.case_ids if self.matrix.loc[case, name]]
        cases.sort(key=lambda case: self.graph_of_case[case].number_of_nodes())
        for case_id in cases[:examples]:
            graph = self.graph_of_case[case_id]
            self.draw(
                graph, f"{name} in case {case_id}", output_dir / f"{name}_in_{case_id}.png",
                highlight=self.occurrence(graph, name))
        print(f"{name} occurs in {len(cases)} cases; figures saved in {output_dir}")


def main():
    print("Which results?")
    for key, (title, *_) in RESULTS.items():
        print(f"  {key}. {title}")
    choice = input("Your choice (Enter for 1): ").strip() or "1"
    _, graph_dir, pattern_dir, figure_dir = RESULTS.get(choice, RESULTS["1"])
    figures = CaseFigures(graph_dir, pattern_dir, figure_dir)

    while True:
        print("\n  L. List candidate cases\n  C. Figures of one case\n"
              "  P. Figures of one pattern\n  0. Exit")
        choice = input("Select: ").strip().upper()
        if choice == "0":
            return
        if choice == "L":
            print(figures.candidates().head(20).to_string(index=False))
        elif choice == "C":
            case_id = input("Case id: ").strip()
            if case_id in figures.graph_of_case:
                figures.case_figures(case_id)
            else:
                print(f"'{case_id}' is not a case of these results.")
        elif choice == "P":
            name = input("Pattern (e.g. P1): ").strip().upper()
            if name in figures.patterns:
                figures.pattern_figures(name)
            else:
                print(f"'{name}' is not one of the patterns P1-P{len(figures.patterns)}.")
        else:
            print(f"'{choice}' is not a valid choice.")


if __name__ == "__main__":
    main()

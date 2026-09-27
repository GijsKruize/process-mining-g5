"""Step 3: pattern mining.

Merges the instance graphs from step 2 into one union graph (their node ids
are already unique across the whole collection, so this is equivalent to
mining every trace separately, just in one pass) and mines recurring
behavioral patterns from it with SUBDUE (vendored under subdue/, from
https://github.com/holderlb/Subdue). For each pattern it reports support,
a trace-pattern occurrence matrix, and a rendered example instance.
"""
import argparse
import pickle
import sys
from pathlib import Path

import networkx as nx
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "subdue"))
from Subdue import nx_subdue  # noqa: E402  (needs the path set up above)


class PatternMiner:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        (self.output_dir / "patterns").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def build_union_graph(graphs):
        """Merge instance graphs into one graph, tracking which trace each node came from."""
        union = nx.DiGraph()
        node_to_trace = {}
        for trace_id, graph in enumerate(graphs):
            union.add_nodes_from(graph.nodes(data=True))
            union.add_edges_from(graph.edges(data=True))
            for node in graph.nodes:
                node_to_trace[node] = trace_id
        return union, node_to_trace

    @staticmethod
    def mine(union_graph, **subdue_kwargs):
        result = nx_subdue(
            union_graph, node_attributes=["label"], edge_attributes=["label"],
            verbose=False, **subdue_kwargs,
        )
        if not result:
            return []
        # SUBDUE returns node/edge ids as strings; cast back to our int ids
        return [
            [
                {"nodes": [int(n) for n in inst["nodes"]],
                 "edges": [(int(s), int(t)) for s, t in inst["edges"]]}
                for inst in pattern
            ]
            for pattern in result
        ]

    @staticmethod
    def pattern_stats(patterns, node_to_trace, n_traces):
        matrix = pd.DataFrame(0, index=range(n_traces),
                               columns=[f"pattern_{i}" for i in range(len(patterns))])
        rows = []
        for i, pattern in enumerate(patterns):
            traces = sorted({node_to_trace[n] for inst in pattern for n in inst["nodes"]})
            matrix.loc[traces, f"pattern_{i}"] = 1
            representative = pattern[0]
            rows.append({
                "pattern_id": i,
                "num_nodes": len(representative["nodes"]),
                "num_edges": len(representative["edges"]),
                "num_instances": len(pattern),
                "support_count": len(traces),
                "support_fraction": len(traces) / n_traces if n_traces else 0.0,
            })
        return pd.DataFrame(rows), matrix

    @staticmethod
    def describe(pattern_id, pattern, union_graph):
        representative = pattern[0]
        labels = {n: union_graph.nodes[n].get("label", str(n)) for n in representative["nodes"]}
        edges = [f"{labels[s]} -> {labels[t]}" for s, t in representative["edges"]]
        print(f"Pattern {pattern_id}: {len(pattern)} instance(s), "
              f"activities: {sorted(set(labels.values()))}")
        print(f"  edges: {edges}")

    def render(self, pattern_id, pattern, union_graph, support_count):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        representative = pattern[0]
        subgraph = union_graph.subgraph(representative["nodes"])
        labels = {n: subgraph.nodes[n].get("label", str(n)) for n in subgraph.nodes}

        plt.figure(figsize=(6, 6))
        pos = nx.spring_layout(subgraph, seed=42)
        nx.draw(subgraph, pos, labels=labels, with_labels=True, node_color="#a7c7e7",
                node_size=1200, font_size=7, arrows=True, arrowsize=15)
        plt.title(f"Pattern {pattern_id} (support={support_count})")
        plt.savefig(self.output_dir / "patterns" / f"pattern_{pattern_id}.png", bbox_inches="tight")
        plt.close()

    def run(self, graphs_path, **subdue_kwargs):
        with open(graphs_path, "rb") as f:
            graphs = pickle.load(f)
        print(f"Loaded {len(graphs)} instance graphs from '{graphs_path}'")

        union_graph, node_to_trace = self.build_union_graph(graphs)
        print(f"Union graph: {union_graph.number_of_nodes()} nodes, "
              f"{union_graph.number_of_edges()} edges")

        patterns = self.mine(union_graph, **subdue_kwargs)
        print(f"Discovered {len(patterns)} pattern(s)")

        stats, matrix = self.pattern_stats(patterns, node_to_trace, len(graphs))
        with open(self.output_dir / "patterns.pkl", "wb") as f:
            pickle.dump(patterns, f)
        stats.to_csv(self.output_dir / "pattern_stats.csv", index=False)
        matrix.to_csv(self.output_dir / "trace_pattern_matrix.csv")
        print(f"Saved patterns, stats, and trace-pattern matrix to '{self.output_dir}/'")

        for i, pattern in enumerate(patterns):
            self.describe(i, pattern, union_graph)
            self.render(i, pattern, union_graph, int(stats.loc[i, "support_count"]))
        if patterns:
            print(f"Pattern visualizations saved to '{self.output_dir}/patterns/'")

        return patterns, stats, matrix, union_graph


def main():
    parser = argparse.ArgumentParser(description="Step 3: mine behavioral patterns with SUBDUE.")
    parser.add_argument("--graphs-path", default="output/instance_graphs.pkl")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--num-best", type=int, default=6)
    parser.add_argument("--min-size", type=int, default=1, help="minimum pattern size (#edges)")
    parser.add_argument("--max-size", type=int, default=8, help="maximum pattern size (#edges)")
    parser.add_argument("--beam-width", type=int, default=4)
    parser.add_argument("--limit", type=int, default=500, help="max patterns considered per iteration")
    args = parser.parse_args()
    PatternMiner(args.output_dir).run(
        args.graphs_path,
        numBest=args.num_best, minSize=args.min_size, maxSize=args.max_size,
        beamWidth=args.beam_width, limit=args.limit,
        overlap="none", prune=False, valueBased=False, iterations=1,
    )


if __name__ == "__main__":
    main()

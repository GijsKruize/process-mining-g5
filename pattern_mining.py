"""Step 3: pattern mining.

Merges the instance graphs from step 2 into one union graph (their node ids
are already unique across the whole collection, so this is equivalent to
mining every trace separately, just in one pass) and mines recurring
behavioral patterns from it with SUBDUE (vendored under subdue/, from
https://github.com/holderlb/Subdue).

For each discovered pattern this module reports support, a trace-pattern
occurrence matrix, and a rendered example instance. SUBDUE's iterative mode
compresses the best pattern from one iteration into synthetic nodes named
``PATTERN-i-j``; those hierarchical patterns are preserved in
``pattern_hierarchy.pkl`` and expanded back to original event nodes for
statistics, evaluation, and visualization.
"""
import argparse
import pickle
import re
import sys
from pathlib import Path

import networkx as nx
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "subdue"))
from Subdue import nx_subdue  # noqa: E402  (needs the path set up above)


DEFAULT_SUBDUE_KWARGS = {
    "numBest": 6,
    "minSize": 1,
    "maxSize": 8,
    "beamWidth": 4,
    "limit": 500,
    "overlap": "none",
    "prune": False,
    "valueBased": False,
    "iterations": 1,
    "temporal": False,
}

COMPRESSED_NODE_RE = re.compile(r"^PATTERN-(\d+)-(\d+)$")


def default_subdue_kwargs(**overrides):
    """Return the shared SUBDUE defaults used by both main.py and this CLI."""
    kwargs = dict(DEFAULT_SUBDUE_KWARGS)
    for key, value in overrides.items():
        if value is not None:
            kwargs[key] = value
    return kwargs


def add_subdue_arguments(parser):
    """Attach the SUBDUE options used by this project to an argparse parser."""
    parser.add_argument("--num-best", type=int, default=DEFAULT_SUBDUE_KWARGS["numBest"],
                        help="number of best patterns SUBDUE reports")
    parser.add_argument("--min-size", type=int, default=DEFAULT_SUBDUE_KWARGS["minSize"],
                        help="minimum pattern size (#edges)")
    parser.add_argument("--max-size", type=int, default=DEFAULT_SUBDUE_KWARGS["maxSize"],
                        help="maximum pattern size (#edges)")
    parser.add_argument("--beam-width", type=int, default=DEFAULT_SUBDUE_KWARGS["beamWidth"])
    parser.add_argument("--limit", type=int, default=DEFAULT_SUBDUE_KWARGS["limit"],
                        help="max patterns considered per iteration")
    parser.add_argument("--iterations", type=int, default=DEFAULT_SUBDUE_KWARGS["iterations"],
                        help="SUBDUE compression iterations; >1 enables hierarchical patterns")
    parser.add_argument("--overlap", choices=["none", "vertex", "edge"],
                        default=DEFAULT_SUBDUE_KWARGS["overlap"])
    parser.add_argument("--prune", action="store_true", default=DEFAULT_SUBDUE_KWARGS["prune"])
    parser.add_argument("--value-based", action="store_true",
                        default=DEFAULT_SUBDUE_KWARGS["valueBased"])
    parser.add_argument("--temporal", action="store_true", default=DEFAULT_SUBDUE_KWARGS["temporal"])


def subdue_kwargs_from_args(args):
    """Translate argparse's snake_case names to SUBDUE's expected kwargs."""
    return default_subdue_kwargs(
        numBest=args.num_best,
        minSize=args.min_size,
        maxSize=args.max_size,
        beamWidth=args.beam_width,
        limit=args.limit,
        overlap=args.overlap,
        prune=args.prune,
        valueBased=args.value_based,
        iterations=args.iterations,
        temporal=args.temporal,
    )


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
    def _coerce_node_id(node_id):
        if isinstance(node_id, int):
            return node_id
        if isinstance(node_id, str):
            try:
                return int(node_id)
            except ValueError:
                return node_id
        return node_id

    @classmethod
    def _normalise_instance(cls, instance):
        return {
            "nodes": [cls._coerce_node_id(node) for node in instance["nodes"]],
            "edges": [
                (cls._coerce_node_id(src), cls._coerce_node_id(dst))
                for src, dst in instance["edges"]
            ],
        }

    @classmethod
    def _looks_like_flat_pattern_output(cls, result):
        if not result:
            return True
        first_pattern = result[0]
        return bool(first_pattern) and isinstance(first_pattern[0], dict)

    @classmethod
    def _normalise_subdue_output(cls, result):
        """Return SUBDUE output as iterations -> patterns -> instances."""
        if not result:
            return []

        raw_iterations = [result] if cls._looks_like_flat_pattern_output(result) else result
        iterations = []
        for iteration in raw_iterations:
            normalised_patterns = []
            for pattern in iteration:
                normalised_patterns.append([cls._normalise_instance(inst) for inst in pattern])
            iterations.append(normalised_patterns)
        return iterations

    @classmethod
    def mine(cls, union_graph, **subdue_kwargs):
        kwargs = default_subdue_kwargs(**subdue_kwargs)
        result = nx_subdue(
            union_graph,
            node_attributes=["label"],
            edge_attributes=["label"],
            verbose=False,
            **kwargs,
        )
        return cls._normalise_subdue_output(result)

    @staticmethod
    def _sort_ids(ids):
        return sorted(ids, key=lambda item: (str(type(item)), str(item)))

    @staticmethod
    def _is_compressed_node(node_id):
        return isinstance(node_id, str) and COMPRESSED_NODE_RE.match(node_id) is not None

    @classmethod
    def _contains_compressed_node(cls, pattern):
        for instance in pattern:
            if any(cls._is_compressed_node(node) for node in instance["nodes"]):
                return True
            if any(cls._is_compressed_node(src) or cls._is_compressed_node(dst)
                   for src, dst in instance["edges"]):
                return True
        return False

    @staticmethod
    def _find_original_edges(source_nodes, target_nodes, union_graph):
        edges = set()
        for source in source_nodes:
            for target in target_nodes:
                if union_graph.has_edge(source, target):
                    edges.add((source, target))
        return edges

    @classmethod
    def _expanded_node(cls, node_id, iteration_patterns, union_graph, seen):
        """Expand a SUBDUE PATTERN-i-j node to its original event nodes and edges."""
        match = COMPRESSED_NODE_RE.match(node_id) if isinstance(node_id, str) else None
        if not match:
            return {node_id}, set()

        iteration_index = int(match.group(1)) - 1
        instance_index = int(match.group(2)) - 1
        key = (iteration_index, instance_index)
        if key in seen:
            raise ValueError(f"Cycle detected while expanding compressed node {node_id}")
        if iteration_index < 0 or iteration_index >= len(iteration_patterns):
            raise ValueError(f"Compressed node {node_id} references a missing iteration")
        if not iteration_patterns[iteration_index]:
            raise ValueError(f"Compressed node {node_id} references an empty iteration")

        best_previous_pattern = iteration_patterns[iteration_index][0]
        if instance_index < 0 or instance_index >= len(best_previous_pattern):
            raise ValueError(f"Compressed node {node_id} references a missing instance")

        expanded = cls.expand_instance(
            best_previous_pattern[instance_index],
            iteration_patterns,
            union_graph,
            seen | {key},
        )
        return set(expanded["nodes"]), set(expanded["edges"])

    @classmethod
    def expand_instance(cls, instance, iteration_patterns, union_graph, seen=None):
        """Replace compressed SUBDUE nodes by the original event nodes they summarize."""
        seen = seen or set()
        all_raw_nodes = set(instance["nodes"])
        for source, target in instance["edges"]:
            all_raw_nodes.add(source)
            all_raw_nodes.add(target)

        expanded_by_raw_node = {}
        expanded_nodes = set()
        expanded_edges = set()

        for node in all_raw_nodes:
            nodes, edges = cls._expanded_node(node, iteration_patterns, union_graph, seen)
            expanded_by_raw_node[node] = nodes
            expanded_nodes.update(nodes)
            expanded_edges.update(edges)

        for source, target in instance["edges"]:
            source_nodes = expanded_by_raw_node[source]
            target_nodes = expanded_by_raw_node[target]
            original_edges = cls._find_original_edges(source_nodes, target_nodes, union_graph)
            if original_edges:
                expanded_edges.update(original_edges)
            elif not cls._is_compressed_node(source) and not cls._is_compressed_node(target):
                expanded_edges.add((source, target))

        return {
            "nodes": cls._sort_ids(expanded_nodes),
            "edges": cls._sort_ids(expanded_edges),
        }

    @classmethod
    def expand_pattern(cls, pattern, iteration_patterns, union_graph):
        return [
            cls.expand_instance(instance, iteration_patterns, union_graph)
            for instance in pattern
        ]

    @classmethod
    def flatten_pattern_records(cls, iteration_patterns, union_graph):
        """Return core patterns first, then hierarchy-expanded patterns."""
        records = []
        for iteration_index, patterns in enumerate(iteration_patterns, start=1):
            for subdue_rank, pattern in enumerate(patterns):
                contains_inner = cls._contains_compressed_node(pattern)
                records.append({
                    "iteration": iteration_index,
                    "subdue_rank": subdue_rank,
                    "category": "hierarchical_expanded" if contains_inner else "core",
                    "contains_inner_patterns": contains_inner,
                    "raw_pattern": pattern,
                    "expanded_pattern": cls.expand_pattern(pattern, iteration_patterns, union_graph),
                })

        records.sort(key=lambda row: (
            1 if row["contains_inner_patterns"] else 0,
            row["iteration"],
            row["subdue_rank"],
        ))
        for pattern_id, record in enumerate(records):
            record["pattern_id"] = pattern_id
        return records

    @staticmethod
    def pattern_stats(patterns, node_to_trace, n_traces, records=None):
        matrix = pd.DataFrame(0, index=range(n_traces),
                              columns=[f"pattern_{i}" for i in range(len(patterns))])
        rows = []
        for i, pattern in enumerate(patterns):
            traces = sorted({
                node_to_trace[node]
                for instance in pattern
                for node in instance["nodes"]
                if node in node_to_trace
            })
            matrix.loc[traces, f"pattern_{i}"] = 1
            representative = pattern[0] if pattern else {"nodes": [], "edges": []}
            record = records[i] if records else {}
            rows.append({
                "pattern_id": i,
                "category": record.get("category", "core"),
                "iteration": record.get("iteration", 1),
                "subdue_rank": record.get("subdue_rank", i),
                "contains_inner_patterns": record.get("contains_inner_patterns", False),
                "num_nodes": len(representative["nodes"]),
                "num_edges": len(representative["edges"]),
                "num_instances": len(pattern),
                "support_count": len(traces),
                "support_fraction": len(traces) / n_traces if n_traces else 0.0,
            })
        return pd.DataFrame(rows), matrix

    @staticmethod
    def describe(pattern_id, pattern, union_graph, record=None):
        representative = pattern[0] if pattern else {"nodes": [], "edges": []}
        labels = {
            node: union_graph.nodes[node].get("label", str(node))
            for node in representative["nodes"]
            if node in union_graph
        }
        edges = [
            f"{labels.get(source, source)} -> {labels.get(target, target)}"
            for source, target in representative["edges"]
        ]
        category = record.get("category", "core") if record else "core"
        iteration = record.get("iteration", 1) if record else 1
        rank = record.get("subdue_rank", pattern_id) if record else pattern_id
        print(f"Pattern {pattern_id} [{category}, iteration={iteration}, subdue_rank={rank}]: "
              f"{len(pattern)} instance(s), activities: {sorted(set(labels.values()))}")
        print(f"  edges: {edges}")

    def render(self, pattern_id, pattern, union_graph, support_count):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        representative = pattern[0] if pattern else {"nodes": [], "edges": []}
        subgraph = nx.DiGraph()
        for node in representative["nodes"]:
            if node in union_graph:
                subgraph.add_node(node, **dict(union_graph.nodes[node]))
        for source, target in representative["edges"]:
            if source in union_graph and target in union_graph:
                edge_attrs = union_graph.get_edge_data(source, target, default={}) or {}
                subgraph.add_edge(source, target, **edge_attrs)

        labels = {node: subgraph.nodes[node].get("label", str(node)) for node in subgraph.nodes}

        plt.figure(figsize=(6, 6))
        pos = nx.spring_layout(subgraph, seed=42) if subgraph.number_of_nodes() else {}
        nx.draw(subgraph, pos, labels=labels, with_labels=True, node_color="#a7c7e7",
                node_size=1200, font_size=7, arrows=True, arrowsize=15)
        plt.title(f"Pattern {pattern_id} (support={support_count})")
        plt.savefig(self.output_dir / "patterns" / f"pattern_{pattern_id}.png", bbox_inches="tight")
        plt.close()

    def run(self, graphs_path, **subdue_kwargs):
        kwargs = default_subdue_kwargs(**subdue_kwargs)
        with open(graphs_path, "rb") as f:
            graphs = pickle.load(f)
        print(f"Loaded {len(graphs)} instance graphs from '{graphs_path}'")

        union_graph, node_to_trace = self.build_union_graph(graphs)
        print(f"Union graph: {union_graph.number_of_nodes()} nodes, "
              f"{union_graph.number_of_edges()} edges")
        print("SUBDUE parameters: "
              + ", ".join(f"{key}={value}" for key, value in sorted(kwargs.items())))

        iteration_patterns = self.mine(union_graph, **kwargs)
        records = self.flatten_pattern_records(iteration_patterns, union_graph)
        patterns = [record["expanded_pattern"] for record in records]
        print(f"Discovered {len(patterns)} pattern(s)")

        stats, matrix = self.pattern_stats(patterns, node_to_trace, len(graphs), records)
        with open(self.output_dir / "patterns.pkl", "wb") as f:
            pickle.dump(patterns, f)
        with open(self.output_dir / "pattern_hierarchy.pkl", "wb") as f:
            pickle.dump(records, f)
        stats.to_csv(self.output_dir / "pattern_stats.csv", index=False)
        matrix.to_csv(self.output_dir / "trace_pattern_matrix.csv")

        hierarchy_rows = [
            {
                "pattern_id": record["pattern_id"],
                "category": record["category"],
                "iteration": record["iteration"],
                "subdue_rank": record["subdue_rank"],
                "contains_inner_patterns": record["contains_inner_patterns"],
            }
            for record in records
        ]
        pd.DataFrame(hierarchy_rows).to_csv(self.output_dir / "pattern_hierarchy.csv", index=False)
        print(f"Saved patterns, hierarchy, stats, and trace-pattern matrix to '{self.output_dir}/'")

        for i, pattern in enumerate(patterns):
            self.describe(i, pattern, union_graph, records[i])
            self.render(i, pattern, union_graph, int(stats.loc[i, "support_count"]))
        if patterns:
            print(f"Pattern visualizations saved to '{self.output_dir}/patterns/'")

        return patterns, stats, matrix, union_graph


def main():
    parser = argparse.ArgumentParser(description="Step 3: mine behavioral patterns with SUBDUE.")
    parser.add_argument("--graphs-path", default="output/instance_graphs.pkl")
    parser.add_argument("--output-dir", default="output")
    add_subdue_arguments(parser)
    args = parser.parse_args()
    PatternMiner(args.output_dir).run(args.graphs_path, **subdue_kwargs_from_args(args))


if __name__ == "__main__":
    main()

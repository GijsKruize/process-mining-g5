"""Step 3: pattern mining.

Merges the instance graphs from step 2 into one union graph (their node ids
are already unique across the whole collection, so this is equivalent to
mining every trace separately, just in one pass) and mines recurring
behavioral patterns from it with SUBDUE (vendored under subdue/, from
https://github.com/holderlb/Subdue).

For each discovered pattern this module reports its support, a trace-pattern
matrix and a rendered example. SUBDUE's iterative mode compresses the best
pattern of an iteration into nodes named ``PATTERN-i-j``; those hierarchical
patterns are kept in ``pattern_hierarchy.pkl`` and expanded back to the
original events for statistics, evaluation and visualization.

Decisions that affect the results (and why)
-------------------------------------------
* **Search budget.** SUBDUE's ``limit`` is the number of patterns it may
  extend, and the first level already contains every single-edge pattern
  that occurs at least twice. With a limit below that number the search
  stops before any pattern can grow beyond two edges, and which patterns get
  extended depends on the order of the traces. The default is therefore 0,
  SUBDUE's own default of half the number of edges, which always covers the
  first level; later levels only extend ``beamWidth`` patterns each.
* **Patterns must repeat.** SUBDUE fills its result list up to ``numBest``
  even with patterns that have a single instance. Those are not frequent
  behaviour, so patterns with fewer than ``--min-instances`` (default 2)
  instances are dropped.
* **Support is counted by matching, not by SUBDUE's instance list.** A
  pattern "occurs in a trace" if the pattern graph is a subgraph of that
  trace's instance graph with the same labels and edge directions. SUBDUE
  only keeps non-overlapping instances while it searches, so its own list
  can miss traces; the matrix required by the assignment should not depend
  on that. SUBDUE's number of instances is still reported.
* **Support is relative to all traces** and the matrix is indexed by case id.
"""
import argparse
import json
import pickle
import re
import sys
from collections import Counter
from pathlib import Path

import networkx as nx
import pandas as pd
from networkx.algorithms import isomorphism

sys.path.insert(0, str(Path(__file__).parent / "subdue"))
from Subdue import nx_subdue  # noqa: E402  (needs the path set up above)


DEFAULT_SUBDUE_KWARGS = {
    "numBest": 6,
    "minSize": 1,
    "maxSize": 8,
    "beamWidth": 4,
    "limit": 0,  # 0 = SUBDUE's default (|E|/2); see module docstring
    "overlap": "none",
    "prune": False,
    "valueBased": False,
    "iterations": 1,
    "temporal": False,
}
DEFAULT_MIN_INSTANCES = 2

COMPRESSED_NODE_RE = re.compile(r"^PATTERN-(\d+)-(\d+)$")


def default_subdue_kwargs(**overrides):
    """Return the shared SUBDUE defaults used by both main.py and this CLI."""
    kwargs = dict(DEFAULT_SUBDUE_KWARGS)
    for key, value in overrides.items():
        if value is not None:
            kwargs[key] = value
    return kwargs


def add_subdue_arguments(parser):
    """Attach the step 3 options to an argparse parser."""
    parser.add_argument("--num-best", type=int, default=DEFAULT_SUBDUE_KWARGS["numBest"],
                        help="number of best patterns SUBDUE reports")
    parser.add_argument("--min-size", type=int, default=DEFAULT_SUBDUE_KWARGS["minSize"],
                        help="minimum pattern size (#edges)")
    parser.add_argument("--max-size", type=int, default=DEFAULT_SUBDUE_KWARGS["maxSize"],
                        help="maximum pattern size (#edges)")
    parser.add_argument("--beam-width", type=int, default=DEFAULT_SUBDUE_KWARGS["beamWidth"])
    parser.add_argument("--limit", type=int, default=DEFAULT_SUBDUE_KWARGS["limit"],
                        help="max patterns SUBDUE extends; 0 (default) = half the number of edges, "
                             "enough to extend every single-edge pattern")
    parser.add_argument("--iterations", type=int, default=DEFAULT_SUBDUE_KWARGS["iterations"],
                        help="SUBDUE compression iterations; >1 enables hierarchical patterns")
    parser.add_argument("--overlap", choices=["none", "vertex", "edge"],
                        default=DEFAULT_SUBDUE_KWARGS["overlap"])
    parser.add_argument("--prune", action="store_true", default=DEFAULT_SUBDUE_KWARGS["prune"])
    parser.add_argument("--value-based", action="store_true",
                        default=DEFAULT_SUBDUE_KWARGS["valueBased"])
    parser.add_argument("--temporal", action="store_true", default=DEFAULT_SUBDUE_KWARGS["temporal"])
    parser.add_argument("--min-instances", type=int, default=DEFAULT_MIN_INSTANCES,
                        help="drop patterns with fewer instances than this (default 2)")
    parser.add_argument("--exclude-activities", default="",
                        help="Comma-separated activity names to remove before SUBDUE, e.g. start,end. "
                             "Neighbours of a removed event are connected to each other")


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


def excluded_activities_from_args(args):
    return [
        activity.strip()
        for activity in getattr(args, "exclude_activities", "").split(",")
        if activity.strip()
    ]


class PatternMiner:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        (self.output_dir / "patterns").mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------------
    # Input graphs
    # ----------------------------------------------------------------------

    @staticmethod
    def case_ids(graphs):
        """Case id per graph (set by step 2); falls back to the position in the list."""
        return [str(graph.graph.get("case_id", index)) for index, graph in enumerate(graphs)]

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
    def label_matches_activity(label, activity):
        """Match raw activity labels and fused labels like Activity_Role_1."""
        return label == activity or label.startswith(f"{activity}_")

    @classmethod
    def filter_graphs_by_activity(cls, graphs, excluded_activities):
        """Remove the events of the given activities from every instance graph.

        When an event is removed, each of its predecessors is connected to
        each of its successors, the same rule BIG uses for a deleted event.
        Without this, removing an event in the middle of a trace would cut
        the graph in two and no pattern could span the gap. For source and
        sink events such as ``start`` and ``end`` nothing is added.
        """
        stats = {
            "enabled": bool(excluded_activities),
            "excluded_activities": list(excluded_activities),
            "removed_nodes": 0,
            "bridging_edges_added": 0,
            "input_graphs": len(graphs),
            "empty_graphs_after_filter": 0,
        }
        if not excluded_activities:
            stats["empty_graphs_after_filter"] = sum(1 for graph in graphs if graph.number_of_nodes() == 0)
            return graphs, stats

        filtered_graphs = []
        for graph in graphs:
            filtered = graph.copy()
            to_remove = [
                node for node, data in graph.nodes(data=True)
                if any(cls.label_matches_activity(data.get("label", ""), activity)
                       for activity in excluded_activities)
            ]
            for node in to_remove:
                predecessors = list(filtered.predecessors(node))
                successors = list(filtered.successors(node))
                filtered.remove_node(node)
                for predecessor in predecessors:
                    for successor in successors:
                        if not filtered.has_edge(predecessor, successor):
                            label = (f"{filtered.nodes[predecessor].get('label', '')}__"
                                     f"{filtered.nodes[successor].get('label', '')}")
                            filtered.add_edge(predecessor, successor, label=label)
                            stats["bridging_edges_added"] += 1
            stats["removed_nodes"] += len(to_remove)
            if filtered.number_of_nodes() == 0:
                stats["empty_graphs_after_filter"] += 1
            filtered_graphs.append(filtered)
        return filtered_graphs, stats

    # ----------------------------------------------------------------------
    # SUBDUE
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # Hierarchical patterns (iterations > 1)
    # ----------------------------------------------------------------------

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
    def flatten_pattern_records(cls, iteration_patterns, union_graph, min_instances=DEFAULT_MIN_INSTANCES):
        """Return core patterns first, then hierarchy-expanded patterns.

        Patterns with fewer than ``min_instances`` instances are left out
        (see module docstring). Compressed nodes always refer to the best
        pattern of an iteration, which SUBDUE only compresses when it has
        instances, so dropping others cannot break an expansion.
        """
        records = []
        dropped = 0
        for iteration_index, patterns in enumerate(iteration_patterns, start=1):
            for subdue_rank, pattern in enumerate(patterns):
                if len(pattern) < min_instances:
                    dropped += 1
                    continue
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
        return records, dropped

    # ----------------------------------------------------------------------
    # Support and trace-pattern matrix
    # ----------------------------------------------------------------------

    @staticmethod
    def pattern_graph(pattern, union_graph):
        """The pattern as a small labelled DiGraph, taken from its first instance."""
        representative = pattern[0] if pattern else {"nodes": [], "edges": []}
        graph = nx.DiGraph()
        for node in representative["nodes"]:
            if node in union_graph:
                graph.add_node(node, label=union_graph.nodes[node].get("label", str(node)))
        for source, target in representative["edges"]:
            if source in graph and target in graph:
                graph.add_edge(source, target)
        return graph

    @staticmethod
    def traces_containing(pattern_graph, graphs, label_counters):
        """Indices of the instance graphs that contain ``pattern_graph``.

        Containment = there is a mapping of pattern nodes to distinct trace
        nodes with equal labels such that every pattern edge is an edge of
        the trace graph (a subgraph monomorphism, i.e. extra edges between
        the matched trace nodes are allowed, exactly as in a SUBDUE
        instance). A cheap label-count test first rules out most traces.
        """
        needed = Counter(data["label"] for _, data in pattern_graph.nodes(data=True))
        node_match = isomorphism.categorical_node_match("label", None)
        matches = []
        for index, graph in enumerate(graphs):
            available = label_counters[index]
            if any(available[label] < count for label, count in needed.items()):
                continue
            matcher = isomorphism.DiGraphMatcher(graph, pattern_graph, node_match=node_match)
            if matcher.subgraph_is_monomorphic():
                matches.append(index)
        return matches

    @classmethod
    def pattern_stats(cls, patterns, graphs, node_to_trace, union_graph, records=None, total_traces=None):
        """Support table and trace-pattern matrix (rows = cases, columns = patterns)."""
        case_ids = cls.case_ids(graphs)
        total_traces = total_traces or len(graphs)
        matrix = pd.DataFrame(0, index=pd.Index(case_ids, name="case_id"),
                              columns=[f"pattern_{i}" for i in range(len(patterns))])
        label_counters = [
            Counter(data.get("label") for _, data in graph.nodes(data=True)) for graph in graphs
        ]
        rows = []
        for i, pattern in enumerate(patterns):
            definition = cls.pattern_graph(pattern, union_graph)
            traces = cls.traces_containing(definition, graphs, label_counters)
            matrix.iloc[traces, i] = 1

            # Traces in which SUBDUE itself recorded an instance. Every one of
            # them must also be found by the matcher; the opposite need not hold.
            subdue_traces = {
                node_to_trace[node]
                for instance in pattern
                for node in instance["nodes"]
                if node in node_to_trace
            }
            record = records[i] if records else {}
            rows.append({
                "pattern_id": i,
                "category": record.get("category", "core"),
                "iteration": record.get("iteration", 1),
                "subdue_rank": record.get("subdue_rank", i),
                "contains_inner_patterns": record.get("contains_inner_patterns", False),
                "num_nodes": definition.number_of_nodes(),
                "num_edges": definition.number_of_edges(),
                "num_instances": len(pattern),
                "support_count": len(traces),
                "support_fraction": len(traces) / total_traces if total_traces else 0.0,
                "traces_with_subdue_instance": len(subdue_traces),
                "subdue_traces_confirmed": subdue_traces.issubset(traces),
            })
        return pd.DataFrame(rows), matrix

    # ----------------------------------------------------------------------
    # Output for people
    # ----------------------------------------------------------------------

    @staticmethod
    def describe(pattern_id, pattern, union_graph, record=None, support=None):
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
        support_text = f", support {support}" if support is not None else ""
        print(f"Pattern {pattern_id} [{category}, iteration={iteration}]: "
              f"{len(pattern)} instance(s){support_text}")
        for edge in edges:
            print(f"    {edge}")

    def render(self, pattern_id, pattern, union_graph, support_count):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        subgraph = self.pattern_graph(pattern, union_graph)
        labels = {node: subgraph.nodes[node].get("label", str(node)) for node in subgraph.nodes}

        plt.figure(figsize=(6, 6))
        pos = nx.spring_layout(subgraph, seed=42) if subgraph.number_of_nodes() else {}
        nx.draw(subgraph, pos, labels=labels, with_labels=True, node_color="#a7c7e7",
                node_size=1200, font_size=7, arrows=True, arrowsize=15)
        plt.title(f"Pattern {pattern_id} (support={support_count})")
        plt.savefig(self.output_dir / "patterns" / f"pattern_{pattern_id}.png", bbox_inches="tight")
        plt.close()

    # ----------------------------------------------------------------------
    # Whole step
    # ----------------------------------------------------------------------

    def run(self, graphs_path, exclude_activities=None, min_instances=DEFAULT_MIN_INSTANCES,
            **subdue_kwargs):
        kwargs = default_subdue_kwargs(**subdue_kwargs)
        with open(graphs_path, "rb") as f:
            graphs = pickle.load(f)
        print(f"Loaded {len(graphs)} instance graphs from '{graphs_path}'")

        graphs, mining_filter_stats = self.filter_graphs_by_activity(
            graphs,
            exclude_activities or [],
        )
        if mining_filter_stats["enabled"]:
            print("Mining activity filter: removed "
                  f"{mining_filter_stats['removed_nodes']} nodes, added "
                  f"{mining_filter_stats['bridging_edges_added']} bridging edges, using "
                  f"{mining_filter_stats['excluded_activities']}")
        with open(self.output_dir / "mining_filter_stats.json", "w", encoding="utf-8") as f:
            json.dump(mining_filter_stats, f, indent=2)

        union_graph, node_to_trace = self.build_union_graph(graphs)
        edge_type_counts = Counter(data.get("label") for _, _, data in union_graph.edges(data=True))
        repeated_edge_types = sum(1 for count in edge_type_counts.values() if count >= 2)
        print(f"Union graph: {union_graph.number_of_nodes()} nodes, "
              f"{union_graph.number_of_edges()} edges, {repeated_edge_types} edge types that occur "
              "at least twice (SUBDUE's single-edge starting patterns)")
        effective_limit = kwargs["limit"] or union_graph.number_of_edges() // 2
        if effective_limit < repeated_edge_types:
            print(f"Warning: --limit {effective_limit} is below the number of starting patterns "
                  f"({repeated_edge_types}); the search will stop before patterns can grow. "
                  "Use --limit 0.")
        print("SUBDUE parameters: "
              + ", ".join(f"{key}={value}" for key, value in sorted(kwargs.items())), flush=True)

        iteration_patterns = self.mine(union_graph, **kwargs)
        records, dropped = self.flatten_pattern_records(iteration_patterns, union_graph, min_instances)
        patterns = [record["expanded_pattern"] for record in records]
        print(f"Discovered {len(patterns)} pattern(s)"
              + (f" ({dropped} with fewer than {min_instances} instances dropped)" if dropped else ""))

        stats, matrix = self.pattern_stats(patterns, graphs, node_to_trace, union_graph, records)
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
        pd.DataFrame(hierarchy_rows, columns=["pattern_id", "category", "iteration", "subdue_rank",
                                              "contains_inner_patterns"]).to_csv(
            self.output_dir / "pattern_hierarchy.csv", index=False)
        print(f"Saved patterns, hierarchy, stats, and trace-pattern matrix to '{self.output_dir}/'")

        for i, pattern in enumerate(patterns):
            support = int(stats.loc[i, "support_count"])
            self.describe(i, pattern, union_graph, records[i],
                          support=f"{support}/{len(graphs)} traces")
            self.render(i, pattern, union_graph, support)
        if patterns:
            print(f"Pattern visualizations saved to '{self.output_dir}/patterns/'")

        return patterns, stats, matrix, union_graph


def main():
    parser = argparse.ArgumentParser(description="Step 3: mine behavioral patterns with SUBDUE.")
    parser.add_argument("--graphs-path", default="output/instance_graphs.pkl")
    parser.add_argument("--output-dir", default="output")
    add_subdue_arguments(parser)
    args = parser.parse_args()
    PatternMiner(args.output_dir).run(
        args.graphs_path,
        exclude_activities=excluded_activities_from_args(args),
        min_instances=args.min_instances,
        **subdue_kwargs_from_args(args),
    )


if __name__ == "__main__":
    main()

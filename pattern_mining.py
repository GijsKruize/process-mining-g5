"""Step 3 of the organizational process mining pipeline: pattern mining.

Takes the instance graphs produced by ``instance_graphs.py`` (step 2) and
mines recurring behavioral patterns from them using the SUBDUE subgraph
mining algorithm (vendored under ``subdue/``, from
https://github.com/holderlb/Subdue -- MIT licensed; see that directory's
LICENSE and the comments in ``subdue/Graph.py`` for the one bug fix applied
when vendoring it).

Since each instance graph already has globally unique node ids (step 2's
guarantee), all instance graphs are merged into a single disjoint-union
graph before mining: SUBDUE finds patterns by extending matching edges, so
a pattern's occurrences across different, disconnected traces are found
exactly as if each trace were mined separately, but in one pass. Node ids
never collide, so every pattern instance's nodes trace back unambiguously
to a single original trace.

For each discovered pattern, this script computes:
  - its support: the number of distinct traces containing at least one
    instance of it (also reported as a fraction of all traces), plus the
    raw instance count (an instance can recur more than once in one trace);
  - a trace-pattern matrix (rows = traces, columns = patterns, 1 if that
    pattern occurs at least once in that trace, else 0);
and can render one representative instance of each pattern as a PNG for
visual inspection.

Run ``python pattern_mining.py --help`` for the command line options.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent / "subdue"))
from Subdue import nx_subdue  # noqa: E402  (path must be set up first)

from instance_graphs import InstanceGraphParser  # noqa: E402

DEFAULT_CONFIG_PATH = Path("config_pattern_mining.yaml")

# One occurrence of a pattern: the node ids and (source, target) edge id
# pairs of a single instance, as returned by SUBDUE's nx_subdue().
Instance = Dict[str, List[Any]]
# A pattern is the list of its instances (all isomorphic to each other).
Pattern = List[Instance]


@dataclass
class PatternMiningConfig:
    """Adjustable parameters for this pipeline step, loaded from YAML."""

    instance_graphs_path: Path = field(
        default_factory=lambda: Path("output/instance_graphs.pkl")
    )
    output_dir: Path = field(default_factory=lambda: Path("output"))
    node_attributes: List[str] = field(default_factory=lambda: ["label"])
    edge_attributes: List[str] = field(default_factory=lambda: ["label"])
    beam_width: int = 4
    # See config_pattern_mining.yaml for why these default away from SUBDUE's
    # own |E|/2 defaults: that's impractical once many instance graphs are
    # merged into one union graph.
    limit: int = 500
    min_size: int = 1
    max_size: int = 8
    num_best: int = 6
    overlap: str = "none"
    prune: bool = False
    value_based: bool = False
    iterations: int = 1
    render_patterns: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> "PatternMiningConfig":
        """Load a config from a YAML file, falling back to defaults for any missing key."""
        with open(path, "r", encoding="utf-8") as config_file:
            raw = yaml.safe_load(config_file) or {}
        defaults = cls()
        return cls(
            instance_graphs_path=Path(
                raw.get("instance_graphs_path", defaults.instance_graphs_path)
            ),
            output_dir=Path(raw.get("output_dir", defaults.output_dir)),
            node_attributes=raw.get("node_attributes", defaults.node_attributes),
            edge_attributes=raw.get("edge_attributes", defaults.edge_attributes),
            beam_width=raw.get("beam_width", defaults.beam_width),
            limit=raw.get("limit", defaults.limit),
            min_size=raw.get("min_size", defaults.min_size),
            max_size=raw.get("max_size", defaults.max_size),
            num_best=raw.get("num_best", defaults.num_best),
            overlap=raw.get("overlap", defaults.overlap),
            prune=raw.get("prune", defaults.prune),
            value_based=raw.get("value_based", defaults.value_based),
            iterations=raw.get("iterations", defaults.iterations),
            render_patterns=raw.get("render_patterns", defaults.render_patterns),
        )

    @property
    def subdue_kwargs(self) -> Dict[str, Any]:
        """SUBDUE's own (camelCase) keyword arguments, derived from this config."""
        return {
            "beamWidth": self.beam_width,
            "iterations": self.iterations,
            "limit": self.limit,
            "maxSize": self.max_size,
            "minSize": self.min_size,
            "numBest": self.num_best,
            "overlap": self.overlap,
            "prune": self.prune,
            "valueBased": self.value_based,
        }

    @property
    def patterns_path(self) -> Path:
        return self.output_dir / "patterns.pkl"

    @property
    def pattern_stats_path(self) -> Path:
        return self.output_dir / "pattern_stats.csv"

    @property
    def trace_pattern_matrix_path(self) -> Path:
        return self.output_dir / "trace_pattern_matrix.csv"

    @property
    def patterns_dir(self) -> Path:
        return self.output_dir / "patterns"


class UnionGraphBuilder:
    """Merges instance graphs (globally unique node ids) into one graph for SUBDUE."""

    @staticmethod
    def build(graphs: List[nx.DiGraph]) -> Tuple[nx.DiGraph, Dict[int, int]]:
        """Return (union_graph, node_id -> trace_index)."""
        union = nx.DiGraph()
        node_to_trace: Dict[int, int] = {}
        for trace_index, graph in enumerate(graphs):
            union.add_nodes_from(graph.nodes(data=True))
            union.add_edges_from(graph.edges(data=True))
            for node in graph.nodes:
                if node in node_to_trace:
                    raise ValueError(
                        f"Node id {node} appears in more than one instance graph "
                        "(step 2's globally-unique-id guarantee was violated)."
                    )
                node_to_trace[node] = trace_index
        return union, node_to_trace


class PatternMiner:
    """Thin wrapper around SUBDUE's nx_subdue()."""

    @staticmethod
    def _normalize_ids(patterns: List[Pattern]) -> List[Pattern]:
        """Cast node/edge ids back from SUBDUE's internal strings to our own int ids."""
        normalized: List[Pattern] = []
        for pattern in patterns:
            normalized_pattern = []
            for instance in pattern:
                normalized_pattern.append(
                    {
                        "nodes": [int(node) for node in instance["nodes"]],
                        "edges": [(int(src), int(dst)) for src, dst in instance["edges"]],
                    }
                )
            normalized.append(normalized_pattern)
        return normalized

    @classmethod
    def discover(cls, union_graph: nx.DiGraph, config: PatternMiningConfig) -> List[Pattern]:
        result = nx_subdue(
            union_graph,
            node_attributes=config.node_attributes,
            edge_attributes=config.edge_attributes,
            verbose=False,
            **config.subdue_kwargs,
        )
        if result is None:
            return []
        if config.iterations > 1:
            print(
                "Note: iterations > 1 configured, but only the first iteration's "
                "patterns are used for statistics/the trace-pattern matrix (see "
                "config_pattern_mining.yaml)."
            )
            result = result[0] if result else []
        return cls._normalize_ids(result)


class PatternStatistics:
    """Support counts and the trace-pattern occurrence matrix."""

    @staticmethod
    def trace_of_instance(instance: Instance, node_to_trace: Dict[int, int]) -> int:
        """The single trace every node of *instance* belongs to."""
        traces = {node_to_trace[node] for node in instance["nodes"]}
        if len(traces) != 1:
            raise ValueError(
                f"Instance spans more than one trace (unexpected): {instance}"
            )
        return traces.pop()

    @classmethod
    def trace_pattern_matrix(
        cls, patterns: List[Pattern], node_to_trace: Dict[int, int], n_traces: int
    ) -> pd.DataFrame:
        """rows = trace index, columns = pattern index, 1 if pattern occurs in trace."""
        matrix = pd.DataFrame(
            0,
            index=[f"trace_{i}" for i in range(n_traces)],
            columns=[f"pattern_{i}" for i in range(len(patterns))],
            dtype=int,
        )
        for pattern_id, pattern in enumerate(patterns):
            trace_indices = {cls.trace_of_instance(inst, node_to_trace) for inst in pattern}
            for trace_index in trace_indices:
                matrix.iloc[trace_index, pattern_id] = 1
        return matrix

    @staticmethod
    def pattern_stats(patterns: List[Pattern], matrix: pd.DataFrame) -> pd.DataFrame:
        n_traces = len(matrix)
        rows = []
        for pattern_id, pattern in enumerate(patterns):
            representative = pattern[0]
            support_count = int(matrix[f"pattern_{pattern_id}"].sum())
            rows.append(
                {
                    "pattern_id": pattern_id,
                    "num_nodes": len(representative["nodes"]),
                    "num_edges": len(representative["edges"]),
                    "num_instances": len(pattern),
                    "support_count": support_count,
                    "support_fraction": support_count / n_traces if n_traces else 0.0,
                }
            )
        return pd.DataFrame(rows)


class PatternVisualizer:
    """Text and PNG rendering to inspect discovered patterns."""

    @staticmethod
    def describe(pattern_id: int, pattern: Pattern, union_graph: nx.DiGraph) -> str:
        representative = pattern[0]
        node_labels = {
            node: union_graph.nodes[node].get("label", str(node))
            for node in representative["nodes"]
        }
        edge_strs = [
            f"{node_labels[src]} -> {node_labels[dst]}" for src, dst in representative["edges"]
        ]
        distinct_labels = sorted(set(node_labels.values()))
        node_summary = f"{len(node_labels)} nodes, distinct activities: {distinct_labels}"
        if len(node_labels) != len(distinct_labels):
            node_summary += " (a repeated activity means this pattern spans a loop)"
        lines = [
            f"Pattern {pattern_id}: {len(pattern)} instance(s)",
            f"  {node_summary}",
            f"  edges: {edge_strs if edge_strs else '(none)'}",
        ]
        return "\n".join(lines)

    @staticmethod
    def render(
        pattern_id: int,
        pattern: Pattern,
        union_graph: nx.DiGraph,
        output_path: Path,
        support_count: int,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        representative = pattern[0]
        subgraph = nx.DiGraph()
        labels = {}
        for node in representative["nodes"]:
            label = union_graph.nodes[node].get("label", str(node))
            subgraph.add_node(node)
            labels[node] = label
        for src, dst in representative["edges"]:
            subgraph.add_edge(src, dst)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pos = nx.spring_layout(subgraph, seed=42, k=1.2)
        plt.figure(figsize=(6, 6))
        nx.draw(
            subgraph,
            pos,
            labels=labels,
            with_labels=True,
            node_color="#a7c7e7",
            node_size=1400,
            font_size=7,
            arrows=True,
            arrowsize=15,
        )
        plt.margins(0.25)
        plt.title(f"Pattern {pattern_id} (support={support_count})")
        plt.savefig(output_path, bbox_inches="tight")
        plt.close()


class PatternMiningPipeline:
    """Orchestrates loading, mining, statistics, and visualization."""

    def __init__(self, config: PatternMiningConfig) -> None:
        self.config = config

    def run(self) -> Dict[str, Any]:
        graphs = InstanceGraphParser.load(self.config.instance_graphs_path)
        print(f"Loaded {len(graphs)} instance graphs from '{self.config.instance_graphs_path}'")

        union_graph, node_to_trace = UnionGraphBuilder.build(graphs)
        print(
            f"Union graph: {union_graph.number_of_nodes()} nodes, "
            f"{union_graph.number_of_edges()} edges"
        )

        patterns = PatternMiner.discover(union_graph, self.config)
        print(f"Discovered {len(patterns)} pattern(s)")

        matrix = PatternStatistics.trace_pattern_matrix(patterns, node_to_trace, len(graphs))
        stats = PatternStatistics.pattern_stats(patterns, matrix)

        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config.patterns_path, "wb") as pickle_file:
            pickle.dump(patterns, pickle_file)
        stats.to_csv(self.config.pattern_stats_path, index=False)
        matrix.to_csv(self.config.trace_pattern_matrix_path)
        print(f"Patterns saved to '{self.config.patterns_path}'")
        print(f"Pattern statistics saved to '{self.config.pattern_stats_path}'")
        print(f"Trace-pattern matrix saved to '{self.config.trace_pattern_matrix_path}'")

        for pattern_id, pattern in enumerate(patterns):
            print(PatternVisualizer.describe(pattern_id, pattern, union_graph))
            if self.config.render_patterns:
                support_count = int(stats.loc[pattern_id, "support_count"])
                PatternVisualizer.render(
                    pattern_id,
                    pattern,
                    union_graph,
                    self.config.patterns_dir / f"pattern_{pattern_id}.png",
                    support_count,
                )
        if self.config.render_patterns and patterns:
            print(f"Pattern visualizations saved under '{self.config.patterns_dir}'")

        return {
            "patterns": patterns,
            "stats": stats,
            "matrix": matrix,
            "union_graph": union_graph,
        }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments; unset flags fall back to the YAML config."""
    parser = argparse.ArgumentParser(
        description="Mine recurring behavioral patterns from instance graphs using SUBDUE."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to the YAML config file (default: '{DEFAULT_CONFIG_PATH}').",
    )
    parser.add_argument(
        "--instance-graphs-path",
        default=None,
        help="Path to the instance graphs pickle from step 2. Overrides the config file.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write patterns/statistics/visualizations to. "
        "Overrides the config file.",
    )
    parser.add_argument(
        "--num-best",
        type=int,
        default=None,
        help="Number of best patterns to report. Overrides the config file.",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=None,
        help="Minimum pattern size (#edges). Overrides the config file.",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=None,
        help="Maximum pattern size (#edges); 0 means |E|/2. Overrides the config file.",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Skip rendering pattern PNGs, even if the config enables it.",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> PatternMiningConfig:
    """Build a PatternMiningConfig from the YAML config file, overridden by any CLI flags."""
    config_path = Path(args.config)
    config = (
        PatternMiningConfig.from_yaml(config_path)
        if config_path.exists()
        else PatternMiningConfig()
    )

    if args.instance_graphs_path is not None:
        config.instance_graphs_path = Path(args.instance_graphs_path)
    if args.output_dir is not None:
        config.output_dir = Path(args.output_dir)
    if args.num_best is not None:
        config.num_best = args.num_best
    if args.min_size is not None:
        config.min_size = args.min_size
    if args.max_size is not None:
        config.max_size = args.max_size
    if args.no_render:
        config.render_patterns = False
    return config


def main(argv: Optional[List[str]] = None) -> None:
    """Single entry point: parse arguments, build the pipeline, and run it."""
    args = parse_args(argv)
    config = build_config(args)

    try:
        PatternMiningPipeline(config).run()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

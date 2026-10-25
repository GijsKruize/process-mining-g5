"""Step 3 - Behavioral pattern mining with SUBDUE.

Assignment: apply the SUBDUE algorithm (https://github.com/holderlb/Subdue) to
the instance graphs, and report for the patterns their support and a
trace x pattern matrix (1 if the pattern occurs in the trace).

All instance graphs are given to SUBDUE together, as one disconnected graph.
SUBDUE then finds the subgraphs that best *compress* this graph: a pattern
with more non-overlapping instances and more edges scores higher
(value = (instances - 1) * edges / edges in the graph). Every node keeps the
id it got in step 2, so every instance can be traced back to its trace.

Performance
-----------
SUBDUE (``subdue/``, unchanged) compares candidates pairwise. Three of its
helper functions are quadratic in the number of edges or instances, which
makes it run for days on the 121,781 edges of the BPI 2017 graphs.
``SubdueAccelerator`` replaces them at run time by versions that give
*exactly* the same result, only faster:

1. ``GetInitialPatterns`` compared every edge with every other edge. Two
   one-edge graphs can only match if their labels (source, target, edge) are
   equal, so edges are first grouped by those labels.
2. ``ExtendPattern`` compared every extended instance with every other one and
   rebuilt the same graphs over and over. Two graphs can only be isomorphic if
   they have the same "fingerprint" (multiset of vertex labels with degree and
   of edge labels), so instances are grouped by fingerprint first, the graphs
   are built once, and SUBDUE's own ``GraphMatch`` decides within a group.
3. The overlap test compared a new instance with every accepted instance; a
   set of the vertices (or edges) already used gives the same answer at once.

Patterns are processed in the same order as in the original, so the output is
identical; ``tests/test_pattern_mining.py`` checks this against the original
functions.
"""
import contextlib
import json
import pickle
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import networkx as nx
import pandas as pd

from . import config

SUBDUE_DIR = config.PROJECT_ROOT / "subdue"
if str(SUBDUE_DIR) not in sys.path:
    sys.path.insert(0, str(SUBDUE_DIR))
import Graph as subdue_graph  # noqa: E402  (SUBDUE's module names)
import Parameters as subdue_parameters  # noqa: E402
import Pattern as subdue_pattern  # noqa: E402
import Subdue as subdue  # noqa: E402

from .instance_graphs import GFileConverter  # noqa: E402

EDGE_LABEL = "next"   # one label for all edges: "the target follows the source"
PATTERN_PREFIX = "P"

# Defaults chosen for the BPI 2017 graphs; all can be changed on the command line.
DEFAULT_BEAM_WIDTH = 4     # as in the paper (it tried 4, 10 and 20)
# Number of patterns SUBDUE extends. 0 = "auto": every one-edge pattern once,
# plus beam_width per level up to max_size (see SubdueSettings.resolve_limit).
DEFAULT_LIMIT = 0
DEFAULT_MIN_SIZE = 2       # edges; one-edge patterns are just "A follows B"
DEFAULT_MAX_SIZE = 10      # edges
DEFAULT_NUM_BEST = 20      # patterns reported per iteration
DEFAULT_ITERATIONS = 1     # >1 compresses the graph with the best pattern and repeats


# ---------------------------------------------------------------------------
# 1. Faster, result-identical replacements for SUBDUE's slow helpers
# ---------------------------------------------------------------------------

_attribute_keys = {}


def _attributes_key(attributes):
    """Hashable version of an attribute dict.

    SUBDUE's pattern graphs share the attribute dicts of the input graph, so
    the key is cached per dict object (the dicts live as long as the graph).
    """
    key = _attribute_keys.get(id(attributes))
    if key is None or key[0] is not attributes:
        key = (attributes, tuple(sorted((k, str(v)) for k, v in attributes.items())))
        _attribute_keys[id(attributes)] = key
    return key[1]


class _OverlapTracker:
    """Answers SUBDUE's ``InstancesOverlap`` for a growing list of accepted instances."""

    def __init__(self, overlap):
        self.overlap = overlap
        self.used = set()

    def _keys(self, instance):
        if self.overlap == "none":        # no shared vertices allowed
            return instance.vertices.set_container
        if self.overlap == "vertex":      # shared vertices allowed, no shared edges
            return instance.edges.set_container
        # "edge": only an identical instance counts as overlap
        return {(frozenset(instance.vertices.set_container),
                 frozenset(instance.edges.set_container))}

    def overlaps(self, instance):
        return not self.used.isdisjoint(self._keys(instance))

    def add(self, instance):
        self.used.update(self._keys(instance))


def _group_matching(parameters, items):
    """SUBDUE's grouping loop, run within one bucket of possibly-matching items.

    ``items`` are (index, graph, instance) in original order. Returns
    (index of first item, graph of first item, matching instances) per group,
    exactly as the original loop over all items would form them.
    """
    groups = []
    remaining = items
    while remaining:
        first_index, first_graph, first_instance = remaining[0]
        matching = [first_instance]
        tracker = _OverlapTracker(parameters.overlap)
        tracker.add(first_instance)
        not_matching = []
        for item in remaining[1:]:
            _, graph, instance = item
            if subdue_graph.GraphMatch(first_graph, graph) and not tracker.overlaps(instance):
                matching.append(instance)
                tracker.add(instance)
            else:
                not_matching.append(item)
        groups.append((first_index, first_graph, matching))
        remaining = not_matching
    return groups


def _graph_fingerprint(graph):
    """Isomorphism invariant: equal for every pair of graphs GraphMatch can match."""
    vertices = sorted((_attributes_key(v.attributes), len(v.edges), v.temporal)
                      for v in graph.vertices.values())
    edges = []
    for edge in graph.edges.values():
        ends = (_attributes_key(edge.source.attributes), _attributes_key(edge.target.attributes))
        if not edge.directed:
            ends = tuple(sorted(ends))
        edges.append((ends, _attributes_key(edge.attributes), edge.directed, edge.temporal))
    return tuple(vertices), tuple(sorted(edges))


def fast_get_initial_patterns(parameters, graph):
    """Same result as ``Subdue.GetInitialPatterns``, with edges grouped by labels first."""
    buckets = {}
    for index, edge in enumerate(graph.edges.values()):
        edge_graph = subdue_graph.CreateGraphFromEdge(edge)
        if parameters.temporal:
            edge_graph.TemporalOrder()
        instance = subdue_pattern.CreateInstanceFromEdge(edge)
        buckets.setdefault(_graph_fingerprint(edge_graph), []).append((index, edge_graph, instance))

    patterns = []
    for items in buckets.values():
        for first_index, definition, instances in _group_matching(parameters, items):
            if len(instances) > 1:
                pattern = subdue_pattern.Pattern()
                pattern.definition = definition
                pattern.instances = instances
                pattern.evaluate(graph)
                patterns.append((first_index, pattern))
    patterns.sort(key=lambda item: item[0])     # the order the original produces
    return [pattern for _, pattern in patterns]


def fast_extend_pattern(parameters, pattern):
    """Same result as ``Pattern.ExtendPattern``, with instances grouped by fingerprint."""
    # Unique extended instances, in order of first appearance (= InsertNewInstance).
    extended, seen = [], set()
    for instance in pattern.instances:
        for new_instance in subdue_pattern.ExtendInstance(instance):
            key = (frozenset(new_instance.vertices.set_container),
                   frozenset(new_instance.edges.set_container))
            if key not in seen:
                seen.add(key)
                extended.append(new_instance)

    buckets = {}
    for index, instance in enumerate(extended):
        instance_graph = subdue_graph.CreateGraphFromInstance(instance)
        if parameters.temporal:
            instance_graph.TemporalOrder()
        buckets.setdefault(_graph_fingerprint(instance_graph), []).append(
            (index, instance_graph, instance))

    new_patterns = []
    for items in buckets.values():
        for first_index, definition, instances in _group_matching(parameters, items):
            new_patterns.append((first_index, subdue_pattern.CreatePatternFromInstances(
                definition, instances)))
    new_patterns.sort(key=lambda item: item[0])
    return [new_pattern for _, new_pattern in new_patterns]


class SubdueAccelerator:
    """Context manager that swaps the fast helpers into SUBDUE and restores the originals."""

    def __enter__(self):
        self._originals = (subdue.GetInitialPatterns, subdue_pattern.ExtendPattern)
        subdue.GetInitialPatterns = fast_get_initial_patterns
        subdue_pattern.ExtendPattern = fast_extend_pattern
        return self

    def __exit__(self, *exc_info):
        subdue.GetInitialPatterns, subdue_pattern.ExtendPattern = self._originals
        return False


# ---------------------------------------------------------------------------
# 2. Instance graphs -> SUBDUE input, and back
# ---------------------------------------------------------------------------

def build_subdue_graph(graphs):
    """One SUBDUE graph containing all instance graphs, plus vertex id -> graph position.

    Only the node ``label`` (activity_role) is given to SUBDUE, so patterns are
    matched on labels; all edges get the same label. Edges are explicitly
    directed (SUBDUE's own networkx loader drops the direction because of a
    bug: it uses ``graph.is_directed`` without calling it).
    """
    entries, vertex_to_graph = [], {}
    for position, graph in enumerate(graphs):
        for node, data in graph.nodes(data=True):
            vertex_id = str(node)
            vertex_to_graph[vertex_id] = position
            entries.append({"vertex": {"id": vertex_id, "attributes": {"label": data["label"]}}})
        for source, target in graph.edges:
            entries.append({"edge": {"id": f"{source}-{target}", "source": str(source),
                                     "target": str(target), "directed": "true",
                                     "attributes": {"label": EDGE_LABEL}}})
    subdue_input = subdue_graph.Graph()
    subdue_input.load_from_json(entries)
    return subdue_input, vertex_to_graph


@dataclass
class MinedPattern:
    """A discovered pattern with its statistics."""
    pattern_id: str
    iteration: int
    rank: int
    value: float
    definition: nx.DiGraph
    instance_graphs: list = field(default_factory=list)   # graph position of every instance

    @property
    def n_instances(self):
        return len(self.instance_graphs)

    @property
    def graph_positions(self):
        return sorted(set(self.instance_graphs))

    @property
    def roles(self):
        return sorted({d.get("value") for _, d in self.definition.nodes(data=True)
                       if d.get("value") is not None})


def definition_to_networkx(definition, label_parts):
    """SUBDUE pattern definition -> networkx.DiGraph with the same node attributes as step 2."""
    graph = nx.DiGraph()
    for vertex_id, vertex in definition.vertices.items():
        label = vertex.attributes.get("label")
        attributes = {"label": label, "local_id": int(vertex_id)}
        if label in label_parts:
            attributes["activity"], attributes["value"] = label_parts[label]
        else:   # e.g. 'PATTERN-1' after compression
            attributes["activity"] = label
        graph.add_node(int(vertex_id), **attributes)
    for edge in definition.edges.values():
        graph.add_edge(int(edge.source.id), int(edge.target.id))
    return graph


def describe_pattern(definition):
    """Readable one-line description: 'A_R1 -> B_R2; A_R1 -> C_R2'."""
    labels = nx.get_node_attributes(definition, "label")
    order = list(nx.topological_sort(definition)) if nx.is_directed_acyclic_graph(definition) \
        else list(definition.nodes)
    rank = {node: i for i, node in enumerate(order)}
    edges = sorted(definition.edges, key=lambda e: (rank[e[0]], rank[e[1]]))
    return "; ".join(f"{labels[u]} -> {labels[v]}" for u, v in edges)


# ---------------------------------------------------------------------------
# 3. Put it together
# ---------------------------------------------------------------------------

@dataclass
class SubdueSettings:
    beam_width: int = DEFAULT_BEAM_WIDTH
    limit: int = DEFAULT_LIMIT
    min_size: int = DEFAULT_MIN_SIZE
    max_size: int = DEFAULT_MAX_SIZE
    num_best: int = DEFAULT_NUM_BEST
    iterations: int = DEFAULT_ITERATIONS
    overlap: str = "none"

    def resolve_limit(self, n_initial_patterns):
        """The limit SUBDUE will use.

        SUBDUE starts from *all* one-edge patterns, in the order of the edges
        (not by value), and stops after extending ``limit`` patterns. A limit
        below the number of one-edge patterns would therefore make the result
        depend on the arbitrary edge order. 'auto' (0) extends every one-edge
        pattern once and then lets the beam search go max_size levels deep.
        """
        if self.limit:
            return self.limit
        return n_initial_patterns + self.beam_width * self.max_size

    def to_parameters(self, n_initial_patterns=0):
        parameters = subdue_parameters.Parameters()
        parameters.beamWidth = self.beam_width
        parameters.limit = self.resolve_limit(n_initial_patterns)
        parameters.minSize = self.min_size
        parameters.maxSize = self.max_size
        parameters.numBest = self.num_best
        parameters.iterations = self.iterations
        parameters.overlap = self.overlap
        return parameters


class PatternMiner:
    """Runs SUBDUE on the instance graphs of step 2 and computes the statistics.

    Outputs in ``<output_root>/<step 2 folder>[_first<N>]/``:
        patterns.csv              one row per pattern: support, size, roles, description
        trace_pattern_matrix.csv  traces x patterns, 1 if the pattern occurs in the trace
        patterns.pkl              the patterns as networkx graphs (for plots and evaluation)
        subdue.log                SUBDUE's own output
        summary.json              settings, timings and totals
    """

    def __init__(self, graphs_path, label_counts_csv=None, output_root=config.STEP3_OUTPUT_DIR,
                 settings=None, max_graphs=None, fast=True):
        self.graphs_path = Path(graphs_path)
        suffix = f"_first{max_graphs}" if max_graphs else ""
        self.output_dir = Path(output_root) / f"{self.graphs_path.parent.name}{suffix}"
        self.label_parts = (GFileConverter.from_label_counts(label_counts_csv).label_parts
                            if label_counts_csv else {})
        self.settings = settings or SubdueSettings()
        self.max_graphs = max_graphs
        self.fast = fast

    def run_subdue(self, subdue_input, log_path):
        """Run SUBDUE (accelerated unless ``fast`` is False); returns its pattern lists."""
        n_initial = len(fast_get_initial_patterns(self.settings.to_parameters(), subdue_input))
        parameters = self.settings.to_parameters(n_initial)
        parameters.set_defaults_for_graph(subdue_input)
        self.used_limit = parameters.limit
        print(f"  {n_initial:,} one-edge patterns with 2 or more instances; "
              f"SUBDUE limit = {parameters.limit:,}", flush=True)
        accelerator = SubdueAccelerator() if self.fast else contextlib.nullcontext()
        with open(log_path, "w", encoding="utf-8", buffering=1) as log, \
                contextlib.redirect_stdout(log), accelerator:
            return subdue.Subdue(parameters, subdue_input)

    @staticmethod
    def resolve_graph(vertex_id, vertex_to_graph, iterations):
        """Graph position of a vertex; follows 'PATTERN-i-j' vertices made by compression."""
        while vertex_id not in vertex_to_graph:
            _, iteration, instance = vertex_id.split("-")
            best = iterations[int(iteration) - 1][0]
            vertex_id = next(iter(best.instances[int(instance) - 1].vertices.list_container)).id
        return vertex_to_graph[vertex_id]

    def collect(self, iterations, vertex_to_graph):
        """SUBDUE's output -> list of MinedPattern."""
        patterns = []
        for iteration_number, pattern_list in enumerate(iterations, start=1):
            for rank, pattern in enumerate(pattern_list, start=1):
                pattern_id = (f"{PATTERN_PREFIX}{rank}" if len(iterations) == 1
                              else f"{PATTERN_PREFIX}{iteration_number}.{rank}")
                positions = [self.resolve_graph(instance.vertices.list_container[0].id,
                                                vertex_to_graph, iterations)
                             for instance in pattern.instances]
                patterns.append(MinedPattern(
                    pattern_id, iteration_number, rank, pattern.value,
                    definition_to_networkx(pattern.definition, self.label_parts), positions))
        return patterns

    @staticmethod
    def pattern_table(patterns, graphs):
        n_graphs = len(graphs)
        rows = []
        for pattern in patterns:
            rows.append({
                "pattern": pattern.pattern_id,
                "iteration": pattern.iteration,
                "subdue_value": round(pattern.value, 5),
                "nodes": pattern.definition.number_of_nodes(),
                "edges": pattern.definition.number_of_edges(),
                "instances": pattern.n_instances,                    # occurrence-based support
                "traces": len(pattern.graph_positions),              # transaction-based support
                "trace_support_pct": round(100 * len(pattern.graph_positions) / n_graphs, 2),
                "roles": ", ".join(pattern.roles),
                "n_roles": len(pattern.roles),
                "description": describe_pattern(pattern.definition),
            })
        return pd.DataFrame(rows)

    @staticmethod
    def trace_pattern_matrix(patterns, graphs):
        case_ids = [graph.graph.get("case_id", graph.graph.get("graph_index")) for graph in graphs]
        matrix = pd.DataFrame(0, index=pd.Index(case_ids, name="case_id"),
                              columns=[pattern.pattern_id for pattern in patterns], dtype=int)
        for pattern in patterns:
            matrix.iloc[pattern.graph_positions, matrix.columns.get_loc(pattern.pattern_id)] = 1
        return matrix

    def run(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        graphs = GFileConverter.load(self.graphs_path)
        if self.max_graphs:
            graphs = graphs[:self.max_graphs]
        subdue_input, vertex_to_graph = build_subdue_graph(graphs)
        print(f"SUBDUE input: {len(graphs):,} instance graphs, {len(subdue_input.vertices):,} "
              f"vertices, {len(subdue_input.edges):,} edges")
        print(f"Settings: {self.settings}; accelerated: {self.fast}")

        log_path = self.output_dir / "subdue.log"
        print(f"Running SUBDUE; progress in {config.display_path(log_path)} ...", flush=True)
        started = time.time()
        iterations = self.run_subdue(subdue_input, log_path)
        seconds = round(time.time() - started, 1)
        print(f"  done in {seconds} s")

        patterns = self.collect(iterations, vertex_to_graph)
        table = self.pattern_table(patterns, graphs)
        matrix = self.trace_pattern_matrix(patterns, graphs)
        table.to_csv(self.output_dir / "patterns.csv", index=False)
        matrix.to_csv(self.output_dir / "trace_pattern_matrix.csv")
        with open(self.output_dir / "patterns.pkl", "wb") as file:
            pickle.dump(patterns, file)

        summary = {
            "step": "3 - pattern mining",
            "created": datetime.now().isoformat(timespec="seconds"),
            "instance_graphs": config.display_path(self.graphs_path),
            "graphs_used": len(graphs),
            "vertices": len(vertex_to_graph),
            "settings": vars(self.settings),
            "subdue_limit_used": self.used_limit,
            "accelerated": self.fast,
            "subdue_seconds": seconds,
            "patterns": len(patterns),
            "traces_with_at_least_one_pattern": int((matrix.sum(axis=1) > 0).sum()),
        }
        (self.output_dir / "summary.json").write_text(json.dumps(summary, indent=2),
                                                      encoding="utf-8")
        if not table.empty:
            print(table[["pattern", "instances", "traces", "trace_support_pct", "edges",
                         "n_roles"]].head(10).to_string(index=False))
        print(f"Step 3 outputs written to: {config.display_path(self.output_dir)}")
        return patterns, table, matrix

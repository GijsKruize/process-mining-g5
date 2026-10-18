"""BIG text/NetworkX conversion, persistence and integrity validation."""
import pickle
import networkx as nx
import pandas as pd
from . import config

class GFileConverter:
    """Parses BIG's .g output into one ``networkx.DiGraph`` per trace.

    Node ids in a .g file are local (every graph starts at 1). Each node gets a
    unique global integer id instead; the local id is kept as attribute
    ``local_id``, and edges are translated through the same mapping, so all
    relations are preserved.

    Node attributes: ``label`` (as in the .g file), ``local_id``, and, when the
    step 1 label table is given, ``activity`` and ``value`` (e.g. the role).
    Graph attributes: ``graph_index`` (0-based position in the file) and
    ``case_id`` (when the case ids are given).
    """

    def __init__(self, label_parts=None):
        """``label_parts``: optional {label: (activity, value)} from step 1."""
        self.label_parts = label_parts or {}

    @classmethod
    def from_label_counts(cls, label_counts_csv):
        """Build the label lookup from step 1's ``label_counts.csv``."""
        table = pd.read_csv(label_counts_csv)
        parts = {row.label: (row.original_activity, row.selected_attribute_value)
                 for row in table.itertuples()}
        return cls(parts)

    def convert(self, g_path, case_ids=None):
        """Read ``g_path`` and return the list of instance graphs."""
        graphs = []
        graph, local_to_global = None, {}
        next_node_id = 0
        with open(g_path, encoding="utf-8") as g_file:
            for line_number, line in enumerate(g_file, start=1):
                parts = line.split()
                if not parts:
                    continue
                kind = parts[0]
                if kind == "XP":                                   # a new graph starts
                    graph = nx.DiGraph(graph_index=len(graphs))
                    local_to_global = {}
                    graphs.append(graph)
                elif kind == "v" and graph is not None and len(parts) == 3:
                    local_id, label = int(parts[1]), parts[2]
                    if local_id in local_to_global:
                        raise ValueError(f"{g_path}:{line_number}: node {local_id} defined twice")
                    local_to_global[local_id] = next_node_id
                    graph.add_node(next_node_id, **self._node_attributes(local_id, label))
                    next_node_id += 1
                elif kind == "e" and graph is not None and len(parts) == 4:
                    source, target = int(parts[1]), int(parts[2])
                    if source not in local_to_global or target not in local_to_global:
                        raise ValueError(f"{g_path}:{line_number}: edge uses an unknown node")
                    # BIG's repair step occasionally writes the same edge twice
                    # (69 times in the example BPI2017Denied.g). An instance
                    # graph is a set of edges, so DiGraph keeps it once.
                    graph.add_edge(local_to_global[source], local_to_global[target], label=parts[3])
                else:
                    raise ValueError(f"{g_path}:{line_number}: cannot read line '{line.strip()}'")

        if case_ids is not None:
            if len(case_ids) != len(graphs):
                raise ValueError(f"{len(graphs)} graphs in {g_path} but {len(case_ids)} traces "
                                 "in the log; they must match one to one.")
            for graph, case_id in zip(graphs, case_ids):
                graph.graph["case_id"] = case_id
        return graphs

    @staticmethod
    def validate_against_log(graphs, log):
        """Reject incomplete or misassigned BIG output before handing it to step 3.

        These checks establish event integrity, not the causal meaning of edges.
        """
        if len(graphs) != len(log):
            raise ValueError("Graph count differs from trace count.")
        seen = set()
        for graph, trace in zip(graphs, log):
            case_id = trace.attributes.get("concept:name")
            prefix = f"Invalid instance graph for {case_id}: "
            if graph.graph.get("case_id") != case_id:
                raise ValueError(prefix + "case id differs from the log")
            if seen.intersection(graph.nodes):
                raise ValueError(prefix + "global node ids are reused")
            seen.update(graph.nodes)
            nodes = sorted(graph.nodes(data=True), key=lambda item: item[1]["local_id"])
            if [d["local_id"] for _, d in nodes] != list(range(1, len(trace) + 1)):
                raise ValueError(prefix + "local ids differ from event positions")
            if [d["label"] for _, d in nodes] != [e[config.ACTIVITY_KEY] for e in trace]:
                raise ValueError(prefix + "labels differ from the log")
            if not graph or not nx.is_weakly_connected(graph):
                raise ValueError(prefix + "graph is empty or disconnected")
            if not nx.is_directed_acyclic_graph(graph):
                raise ValueError(prefix + "graph contains a cycle")
            for u, v, data in graph.edges(data=True):
                if graph.nodes[u]["local_id"] >= graph.nodes[v]["local_id"]:
                    raise ValueError(prefix + "edge contradicts event order")
                if data.get("label") != graph.nodes[u]["label"] + "__" + graph.nodes[v]["label"]:
                    raise ValueError(prefix + "edge label differs from its endpoints")

    def _node_attributes(self, local_id, label):
        attributes = {"label": label, "local_id": local_id}
        if label in self.label_parts:
            attributes["activity"], attributes["value"] = self.label_parts[label]
        return attributes

    @staticmethod
    def summarise(graphs):
        """One row per graph: size and shape, useful to inspect BIG's output."""
        rows = []
        for graph in graphs:
            rows.append({
                "graph_index": graph.graph["graph_index"],
                "case_id": graph.graph.get("case_id"),
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                # Branching is a structural measure, not proof of concurrency.
                "has_branching": any(degree > 1 for _, degree in graph.out_degree()),
                "connected": graph.number_of_nodes() > 0 and nx.is_weakly_connected(graph),
                "acyclic": nx.is_directed_acyclic_graph(graph),
            })
        return pd.DataFrame(rows)

    @staticmethod
    def save(graphs, path):
        with open(path, "wb") as file:
            pickle.dump(graphs, file)
        return path

    @staticmethod
    def load(path):
        """Load the graphs saved by ``save`` (used by step 3)."""
        with open(path, "rb") as file:
            return pickle.load(file)

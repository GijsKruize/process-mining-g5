"""Validation of one instance graph against the raw trace it was built from.

``TraceValidator`` puts the events of a case (from the step 1 output) next to
its instance graph (step 2) and checks:

1. the graph has one node per event, with the same labels (as a multiset);
2. the role in every label is the role of the employee who performed the
   event (step 1 role assignment);
3. no edge goes backwards in the recorded order (BIG's repair may reorder
   irregular events, which is then reported);
4. which edges connect events that directly follow each other in the trace,
   and which skip events (parallel branches or repairs).
"""
from collections import Counter
from pathlib import Path

import pandas as pd

from . import config
from .instance_graphs import GFileConverter
from .log_io import read_xes_as_dataframe


class TraceValidator:
    def __init__(self, step1_dir, graphs_path):
        self.step1_dir = Path(step1_dir)
        self.graphs = {g.graph.get("case_id"): g for g in GFileConverter.load(graphs_path)}
        self._log = None

    @property
    def log(self):
        if self._log is None:   # the relabelled log is large: read it only once, when needed
            self._log = read_xes_as_dataframe(self.step1_dir / "relabeled_log.xes")
        return self._log

    def trace_table(self, case_id):
        events = self.log[self.log[config.CASE_ID_KEY] == case_id].reset_index(drop=True)
        roles = pd.read_csv(self.step1_dir / "resource_roles.csv").set_index("resource")["role"]
        return pd.DataFrame({
            "position": range(1, len(events) + 1),
            "timestamp": events[config.TIMESTAMP_KEY].astype(str).str[:19],
            "activity": events[config.ORIGINAL_ACTIVITY_KEY],
            "employee": events[config.ORIGINAL_VALUE_KEY],
            "role_of_employee": events[config.ORIGINAL_VALUE_KEY].map(roles),
            "label": events[config.ACTIVITY_KEY],
        })

    def validate(self, case_id):
        """Return (trace table with graph columns, list of check results as text)."""
        trace = self.trace_table(case_id)
        graph = self.graphs[case_id]
        local = {node: data["local_id"] for node, data in graph.nodes(data=True)}
        labels = {data["local_id"]: data["label"] for _, data in graph.nodes(data=True)}

        # BIG numbers the nodes in trace order, so local id i is event i.
        trace["graph_node"] = trace["position"].where(trace["position"].isin(labels))
        trace["graph_label"] = trace["position"].map(labels)
        successors = {}
        for source, target in graph.edges:
            successors.setdefault(local[source], []).append(local[target])
        trace["graph_successors"] = trace["position"].map(
            lambda p: ", ".join(map(str, sorted(successors.get(p, [])))) or "(end)")

        edges = [(local[s], local[t]) for s, t in graph.edges]
        consecutive = sum(1 for s, t in edges if t == s + 1)
        backwards = [(s, t) for s, t in edges if t < s]
        skipping = sorted((s, t) for s, t in edges if t > s + 1)
        same_labels = Counter(trace["label"]) == Counter(labels.values())
        role_ok = pd.Series([label.endswith("_" + str(role)) for label, role
                             in zip(trace["label"], trace["role_of_employee"])])
        checks = [
            f"events in trace: {len(trace)}, nodes in graph: {graph.number_of_nodes()}, "
            f"edges: {graph.number_of_edges()}",
            f"same labels in trace and graph: {'yes' if same_labels else 'NO'}",
            f"role in label = role of the employee: {int(role_ok.sum())}/{len(trace)} events",
            f"edges between consecutive events: {consecutive}/{len(edges)}",
            f"edges that skip events (parallel branch or repair): "
            f"{', '.join(f'{s}->{t}' for s, t in skipping) or 'none'}",
            f"edges backwards in time: {', '.join(f'{s}->{t}' for s, t in backwards) or 'none'}",
        ]
        return trace, checks

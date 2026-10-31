"""Single entry point for the BPI 2017 organizational pattern mining pipeline.

Run with::

    python main.py

A numbered menu lets you pick which step to (re)run. Each step asks for its
own parameters (press Enter to accept the suggested default) and then runs
straight through - no further questions.

The four steps are:
    1. Instance graph generation  - pick the attribute to analyse, relabel
       the log (activity_attribute, optional roles + lifecycle), discover a
       Petri net, run BIG, save the instance graphs.
    2. Pattern mining             - run SUBDUE on the saved instance graphs;
       support, trace x pattern matrix and pattern figures.
    3. Evaluation                 - alignment fitness of the Petri net and
       the instance graphs against a sample of the log.
    4. Synthetic validation       - steps 1 and 2 on a small hand-made log
       (data/synthetic/), scored against its gold standard with precision
       and recall.

Figures of one chosen case (its trace, instance graph and patterns, like
Figure 1 of the assignment) are made by the separate ``figures.py``.
"""
import contextlib
import copy
import csv
import json
import os
import pickle
import re
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import networkx as nx
import pandas as pd
import pm4py
from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments
from pm4py.algo.organizational_mining.roles import algorithm as role_discovery
from pm4py.algo.organizational_mining.roles.variants.pandas import Parameters as RoleParameters
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import EventLog
from pm4py.objects.petri_net.importer import importer as pnml_importer

import BIG

# All paths are derived from this file's own location, never hard-coded, so
# the project runs unchanged on any machine (as the assignment requires).
PROJECT_ROOT = Path(__file__).resolve().parent
DATASET_PATH = PROJECT_ROOT / "data" / "BPI2017Denied(3).xes"
INSTANCE_GRAPH_DIR = PROJECT_ROOT / "output" / "instance graphs"
PATTERN_OUTPUT_DIR = PROJECT_ROOT / "output" / "patterns"
EVALUATION_OUTPUT_DIR = PROJECT_ROOT / "output" / "evaluation"
PATTERN_EVALUATION_DIR = EVALUATION_OUTPUT_DIR / "pattern_evaluation"
SUBDUE_DIR = PROJECT_ROOT / "subdue"
SYNTHETIC_DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
SYNTHETIC_OUTPUT_DIR = PROJECT_ROOT / "output" / "synthetic validation"

# Columns of the event log that identify the case, the event or its time:
# shown to the user, but not selectable as the attribute to analyse.
NON_SELECTABLE_ATTRIBUTES = ("concept:name", "case:concept:name", "time:timestamp")


def split_label(label):
    """'Check-credit_Credit' -> ('Check-credit', 'Credit').

    Labels are built as <activity>_<value> with every '_' in the activity
    replaced by '-' (see ``InstanceGraphStep.relabel_events``), so the first
    '_' always separates the two - also for values such as 'Role_4'."""
    activity, _, value = str(label).partition("_")
    return activity, value


def label_matcher(left, right):
    """networkx node_match: two nodes match when their labels are equal."""
    return left.get("label") == right.get("label")


def contains_pattern(graph, pattern):
    """Whether ``pattern`` occurs in ``graph``: an injective mapping of the
    pattern's nodes onto equally labeled nodes of the graph that keeps every
    pattern edge (subgraph monomorphism). Used for the trace x pattern
    matrix and for checking gold-standard patterns, independently of which
    (non-overlapping) instances SUBDUE itself happened to report."""
    return next(pattern_occurrences(graph, pattern), None) is not None


def pattern_occurrences(graph, pattern):
    """Iterate over the occurrences (graph node -> pattern node mappings) of
    ``pattern`` in ``graph``; see ``contains_pattern``."""
    graph_labels = Counter(nx.get_node_attributes(graph, "label").values())
    pattern_labels = Counter(nx.get_node_attributes(pattern, "label").values())
    if any(graph_labels[label] < count for label, count in pattern_labels.items()):
        return iter(())  # cheap pre-check: a needed label is missing
    matcher = nx.algorithms.isomorphism.DiGraphMatcher(graph, pattern, node_match=label_matcher)
    return matcher.subgraph_monomorphisms_iter()


def edges_text(graph):
    """A pattern as readable text, 'A -> B; B -> C', in the same format as
    the gold standard's ``edges`` column."""
    labels = nx.get_node_attributes(graph, "label")
    return "; ".join(sorted(f"{labels[source]} -> {labels[target]}" for source, target in graph.edges))


def run_canvas_big_chunk(chunk):
    """Fallback for a BIG.py without ``run_big_chunk`` (the unchanged Canvas
    version): run ``BIG.big`` on traces [start, end) of the log.

    ``BIG.big`` reads a whole log and appends to ``graph.g`` in the current
    directory, so the chunk is written to its own XES file and BIG runs in
    its own empty folder (one per chunk, so parallel chunks never share it).
    """
    import shutil
    import tempfile

    start, end, chunk_output, initial_marking, final_marking, net, log_path = chunk
    log = xes_importer.apply(str(log_path))
    chunk_log = EventLog(list(log)[start:end], attributes=log.attributes)
    work_dir = Path(tempfile.mkdtemp(prefix="big_chunk_", dir=Path(chunk_output).parent))
    chunk_log_path = work_dir / "chunk.xes"
    xes_exporter.apply(chunk_log, str(chunk_log_path))
    previous_dir = os.getcwd()
    os.chdir(work_dir)
    try:
        BIG.big(net=net, initial_marking=initial_marking, final_marking=final_marking,
                log=str(chunk_log_path))
    finally:
        os.chdir(previous_dir)
    shutil.move(str(work_dir / "graph.g"), str(chunk_output))
    shutil.rmtree(work_dir, ignore_errors=True)


class Parameter:
    """One adjustable value of a pipeline step: asked on the terminal, with an
    explanation and a suggested default so the user does not need to read the
    code to know what to type."""

    def __init__(self, key, question, help_text, default, cast=str):
        self.key = key
        self.question = question
        self.help_text = help_text
        self.default = default
        self.cast = cast

    def ask(self):
        print(f"\n- {self.question}")
        print(f"  {self.help_text}")
        raw = input(f"  Suggested: {self.default}. Your choice (Enter to accept): ").strip()
        if raw == "":
            return self.default
        if self.cast is bool:
            return raw.lower() in ("y", "yes", "true", "1")
        return self.cast(raw)


class PipelineStep:
    """Common interface for one step of the pipeline, selectable from the menu."""

    key = ""
    title = ""
    parameters = []

    def output_exists(self):
        """Whether this step's final output of a previous run is on disk."""
        raise NotImplementedError

    def ask_parameters(self):
        print(f"\n=== {self.title}: parameters ===")
        return {parameter.key: parameter.ask() for parameter in self.parameters}

    def run(self, params):
        raise NotImplementedError


class InstanceGraphStep(PipelineStep):
    """Step 1: let the user pick the attribute to analyse, relabel the log,
    discover a Petri net, run BIG, save the graphs."""

    key = "1"
    title = "Instance graph generation"
    # Suggest grouping into roles only for attributes with more distinct
    # values than this (e.g. org:resource with 134 users, not a department).
    ROLE_GROUPING_SUGGESTED_ABOVE = 20
    parameters = [
        Parameter(
            "group_roles", "Group the attribute's values into roles before relabeling?",
            "Replaces each value of the selected attribute (e.g. each user of "
            "org:resource) by its discovered role (pm4py role mining) instead "
            "of using the raw value. Only useful for attributes with many "
            "values: org:resource alone has 134, which makes both the Petri "
            "net and BIG slow; grouping into roles cuts that down a lot.",
            default=True, cast=bool,
        ),
        Parameter(
            "roles_threshold", "Role similarity threshold (0-1)?",
            "Two roles are merged if their resource profiles are at least this "
            "similar. Only used when roles are grouped. pm4py's own default is 0.65.",
            default=0.65, cast=float,
        ),
        Parameter(
            "collapse_lifecycle", "Collapse repeated lifecycle events?",
            "BPI 2017 work items (activities starting with 'W-') record every "
            "lifecycle step (schedule/start/suspend/resume/complete/...) as its "
            "own event. Merging directly repeated same-label events shortens "
            "every trace, which is the single biggest factor in how long BIG "
            "takes per trace.",
            default=True, cast=bool,
        ),
        Parameter(
            "noise_threshold", "Inductive Miner noise threshold (0-1)?",
            "Higher values give a more general Petri net that fits more "
            "deviating behaviour; lower values give a stricter model. 0.2 is "
            "ProM's default and the value the team chose for the paper.",
            default=0.2, cast=float,
        ),
        Parameter(
            "workers", "Worker processes for the BIG run?",
            "BIG processes traces independently, so the log is split into this "
            "many chunks, each run in its own process. More workers finish "
            "faster up to the number of CPU cores you have.",
            default=min(10, os.cpu_count() or 1), cast=int,
        ),
    ]

    WORK_ITEM_PREFIX = "W-"
    LIFECYCLE_SUFFIX = re.compile(r"-(schedule|start|suspend|resume|complete|ate-abort|withdraw)$")

    def __init__(self, dataset_path=DATASET_PATH, output_dir=INSTANCE_GRAPH_DIR):
        self.dataset_path = Path(dataset_path)
        self.output_dir = Path(output_dir)
        self.log_path = self.output_dir / "BPI2017Denied_pm4py.xes"
        self.petri_net_path = self.output_dir / "petri_net_pm4py.pnml"
        self.big_output_path = self.output_dir / "graph_pm4py.g"
        self.graphs_path = self.output_dir / "instance_graphs_pm4py.pkl"
        self.resource_roles_path = self.output_dir / "resource_roles.csv"
        self.settings_path = self.output_dir / "generation_settings.json"
        self._event_log = None  # loaded once, by ask_parameters or run

    def output_exists(self):
        return self.graphs_path.exists()

    # -- choosing the attribute to analyse -------------------------------

    def event_log_frame(self):
        """The input log as a DataFrame (one row per event, trace attributes
        prefixed with 'case:'), loaded once and reused."""
        if self._event_log is None:
            print(f"Loading event log {self.dataset_path.name}...", flush=True)
            self._event_log = log_converter.apply(
                xes_importer.apply(str(self.dataset_path)),
                variant=log_converter.Variants.TO_DATA_FRAME,
            )
        return self._event_log

    @staticmethod
    def describe_attributes(event_log):
        """One row per attribute of the log: level, distinct values, how many
        events have a value, and a few examples."""
        rows = []
        for column in event_log.columns:
            values = event_log[column].dropna()
            rows.append({
                "attribute": column,
                "level": "trace" if column.startswith("case:") else "event",
                "distinct": values.nunique(),
                "filled_pct": round(100 * len(values) / len(event_log), 1),
                "examples": ", ".join(str(value) for value in values.unique()[:3]),
                "selectable": column not in NON_SELECTABLE_ATTRIBUTES,
            })
        return rows

    def ask_attribute(self, default="org:resource"):
        """Show every attribute of the log and let the user pick the one to
        analyse, by number or name (asked again until the answer is valid)."""
        rows = self.describe_attributes(self.event_log_frame())
        selectable = [row for row in rows if row["selectable"]]
        print(f"\nAttributes in {self.dataset_path.name} "
              f"({len(self.event_log_frame())} events):")
        print(f"  {'#':>3}  {'attribute':<28} {'level':<6} {'distinct':>8} {'filled':>7}  examples")
        for number, row in enumerate(selectable, start=1):
            warning = "  (many values)" if row["distinct"] > 1000 else ""
            print(f"  {number:>3}  {row['attribute']:<28} {row['level']:<6} {row['distinct']:>8} "
                  f"{row['filled_pct']:>6}%  {row['examples'][:50]}{warning}")
        fixed = ", ".join(row["attribute"] for row in rows if not row["selectable"])
        print(f"  (not selectable: {fixed} - they identify the case, the activity and the time)")

        names = [row["attribute"] for row in selectable]
        if default not in names:
            default = names[0]
        print("\n- Which attribute do you want to analyse?")
        print("  Every event gets the label <activity>_<value of this attribute>.")
        while True:
            raw = input(f"  Suggested: {default}. Number or name (Enter to accept): ").strip()
            if raw == "":
                return default
            if raw.isdigit() and 1 <= int(raw) <= len(names):
                return names[int(raw) - 1]
            if raw in names:
                return raw
            print(f"  '{raw}' is not one of the attributes above; try again.")

    def ask_parameters(self):
        print(f"\n=== {self.title}: parameters ===")
        attribute = self.ask_attribute()
        distinct = self.event_log_frame()[attribute].nunique()
        params = {"attribute": attribute}
        for parameter in self.parameters:
            if parameter.key == "group_roles":
                parameter = copy.copy(parameter)
                parameter.default = distinct > self.ROLE_GROUPING_SUGGESTED_ABOVE
            params[parameter.key] = parameter.ask()
        return params

    # -- relabeling -----------------------------------------------------

    def strip_lifecycle(self, activity):
        """'W-Validate-application-start' -> 'W-Validate-application'.

        Other activities are returned unchanged."""
        if not activity.startswith(self.WORK_ITEM_PREFIX):
            return activity
        return self.LIFECYCLE_SUFFIX.sub("", activity)

    def discover_roles(self, event_log, attribute, roles_threshold):
        """Map every value of ``attribute`` (e.g. every resource) to its
        dominant role: the discovered role in which it performs most of its
        events. Role_1 is the role with the most events overall."""
        frame = pd.DataFrame({
            "resource": event_log[attribute].fillna("UNKNOWN").astype(str),
            "activity": event_log["concept:name"].astype(str),
        })
        roles = role_discovery.apply(frame, parameters={
            RoleParameters.RESOURCE_KEY: "resource",
            RoleParameters.ACTIVITY_KEY: "activity",
            RoleParameters.ROLES_THRESHOLD_PARAMETER: roles_threshold,
        })
        dominant = {}  # resource -> (role index, events in that role); first role wins a tie
        for role_index, (_, resource_counts) in enumerate(roles):
            for resource, events in resource_counts.items():
                if resource not in dominant or events > dominant[resource][1]:
                    dominant[resource] = (role_index, events)

        events_per_resource = Counter(frame["resource"])
        events_per_role = Counter()
        for resource, (role_index, _) in dominant.items():
            events_per_role[role_index] += events_per_resource[resource]
        ranked = sorted(events_per_role, key=lambda index: (-events_per_role[index], index))
        role_names = {index: f"Role_{rank}" for rank, index in enumerate(ranked, start=1)}
        return {resource: role_names[role_index] for resource, (role_index, _) in dominant.items()}

    def relabel_events(self, event_log, attribute, role_mapping, collapse_lifecycle):
        """Add the 'activity_selectedAttribute' label: roles first (if given),
        then the lifecycle collapse. A role change inside a work item is a
        handover and stays two events.

        Whitespace becomes '-' (BIG's .g output is space separated) and so
        does '_' inside the activity, so the first '_' of a label always
        separates activity and value (see ``split_label``)."""
        event_log = event_log.copy()
        activity = (event_log["concept:name"].fillna("UNKNOWN").astype(str)
                    .str.replace(r"[\s_]+", "-", regex=True))
        value = event_log[attribute].fillna("UNKNOWN").astype(str)
        if role_mapping is not None:
            value = value.map(role_mapping).fillna("UNKNOWN")
        value = value.str.replace(r"\s+", "-", regex=True)
        if collapse_lifecycle:
            is_work_item = activity.str.startswith(self.WORK_ITEM_PREFIX)
            activity = activity.where(~is_work_item, activity.str.replace(
                self.LIFECYCLE_SUFFIX, "", regex=True))
        event_log["activity_selectedAttribute"] = activity + "_" + value

        if collapse_lifecycle:
            case = event_log["case:concept:name"]
            label = event_log["activity_selectedAttribute"]
            repeated = (label == label.shift()) & (case == case.shift())
            event_log = event_log[~repeated].reset_index(drop=True)
        return event_log

    def load_big_event_log(self, params):
        """(Re)build the attribute-relabeled event log needed for discovery/BIG."""
        event_log = self.event_log_frame()
        attribute = params["attribute"]

        role_mapping = None
        if params["group_roles"]:
            role_mapping = self.discover_roles(event_log, attribute, params["roles_threshold"])
            pd.DataFrame(sorted(role_mapping.items()), columns=[attribute, "role"]).to_csv(
                self.resource_roles_path, index=False
            )
            print(f"Grouped {len(role_mapping)} values of {attribute} into "
                  f"{len(set(role_mapping.values()))} roles (saved to {self.resource_roles_path})",
                  flush=True)

        events_before = len(event_log)
        event_log = self.relabel_events(event_log, attribute, role_mapping, params["collapse_lifecycle"])
        print(f"{event_log['activity_selectedAttribute'].nunique()} distinct labels, "
              f"{len(event_log)} of {events_before} events kept", flush=True)

        big_log = event_log.copy()
        big_log["concept:name"] = big_log["activity_selectedAttribute"]
        return log_converter.apply(big_log, variant=log_converter.Variants.TO_EVENT_LOG)

    # -- BIG's .g output -> networkx -------------------------------------

    @staticmethod
    def read_big_graphs(path):
        """Convert BIG's XP/v/e text blocks into uniquely identified graphs."""
        graphs = []
        graph = None
        for line in Path(path).read_text().splitlines():
            parts = line.split(maxsplit=3)
            if not parts:
                continue
            if parts[0] == "XP":
                graph = nx.DiGraph()
                graphs.append(graph)
            elif graph is not None and parts[0] == "v":
                node_id, label = parts[1], parts[2]
                graph.add_node(f"g{len(graphs) - 1}_n{node_id}", label=label)
            elif graph is not None and parts[0] == "e":
                source = f"g{len(graphs) - 1}_n{parts[1]}"
                target = f"g{len(graphs) - 1}_n{parts[2]}"
                label = parts[3] if len(parts) > 3 else ""
                graph.add_edge(source, target, label=label)
        return graphs

    # -- Petri net discovery ---------------------------------------------

    @staticmethod
    def discover_petri_net(big_event_log, noise_threshold):
        """Inductive Miner on an already-relabeled event log."""
        print("Discovering the PM4Py Inductive Miner model...", flush=True)
        net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(
            big_event_log, noise_threshold=noise_threshold
        )
        print("Petri-net discovery complete.", flush=True)
        return net, initial_marking, final_marking

    # -- the four checkpointed sub-steps ---------------------------------

    def run(self, params):
        """Relabel the log, discover a Petri net, run BIG, and save the
        instance graphs - unconditionally, every time this step is run."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.settings_path, "w") as file:
            json.dump(params, file, indent=2)

        big_event_log = self.load_big_event_log(params)
        xes_exporter.apply(big_event_log, str(self.log_path))
        print(f"Saved relabeled log to {self.log_path}", flush=True)

        net, initial_marking, final_marking = self.discover_petri_net(
            big_event_log, params["noise_threshold"])
        pm4py.write_pnml(net, initial_marking, final_marking, str(self.petri_net_path))

        self.run_big(big_event_log, net, initial_marking, final_marking, params["workers"])

        graphs = self.read_big_graphs(self.big_output_path)
        # BIG writes one graph per trace, in log order: graph i is trace i.
        for index, (graph, trace) in enumerate(zip(graphs, big_event_log)):
            graph.graph["graph_index"] = index
            graph.graph["case_id"] = trace.attributes.get("concept:name", str(index))
        with open(self.graphs_path, "wb") as file:
            pickle.dump(graphs, file)

        print(f"Saved {len(graphs)} instance graphs in {self.output_dir}")

    def run_big(self, big_event_log, net, initial_marking, final_marking, workers):
        """Run BIG on the log in parallel, chunked across worker processes.

        BIG's result for a trace depends only on its sequence of labels, so
        BIG runs once per *variant* (on a log of one trace per variant) and
        each variant's graph is then written once for every trace that has
        it, in log order. The variant log is cut into consecutive chunks and
        each chunk runs in its own process (``BIG.run_big_chunk`` if this
        BIG.py has it, else ``run_canvas_big_chunk``); the chunks' outputs
        are joined back in their original order, giving the same result a
        single BIG run on the whole log would.
        """
        first_trace_of_variant = {}  # dicts keep insertion order: variants in log order
        trace_variants = []
        for trace in big_event_log:
            variant = tuple(event["concept:name"] for event in trace)
            first_trace_of_variant.setdefault(variant, trace)
            trace_variants.append(variant)
        variants = list(first_trace_of_variant)
        variant_index = {variant: index for index, variant in enumerate(variants)}
        variant_of_trace = [variant_index[variant] for variant in trace_variants]
        variant_log = EventLog([first_trace_of_variant[variant] for variant in variants],
                               attributes=big_event_log.attributes)
        log_path = self.output_dir / "big_input_variants.xes"
        xes_exporter.apply(variant_log, str(log_path))
        print(f"{len(big_event_log)} traces, {len(variants)} distinct variants: "
              "BIG runs once per variant", flush=True)

        output_path = self.big_output_path
        chunk_dir = self.output_dir
        run_chunk = getattr(BIG, "run_big_chunk", run_canvas_big_chunk)

        trace_count = len(variant_log)
        workers = min(max(1, workers), trace_count) or 1
        chunk_size = (trace_count + workers - 1) // workers
        chunks = []
        for start in range(0, trace_count, chunk_size):
            chunk_output = chunk_dir / f"{output_path.stem}_chunk_{start}.g"
            chunk_output.unlink(missing_ok=True)
            chunks.append((
                start, min(start + chunk_size, trace_count), str(chunk_output),
                initial_marking, final_marking, net, str(log_path)
            ))

        print(f"Running BIG with {workers} worker process(es)", flush=True)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            # list(): wait for every chunk and surface a worker exception
            # immediately, instead of silently discarding it.
            list(pool.map(run_chunk, chunks))

        variant_output = "\n".join(Path(chunk[2]).read_text() for chunk in chunks)
        for chunk in chunks:
            Path(chunk[2]).unlink()
        # One "XP" block per variant; write variant i's block for every trace of it.
        blocks = re.split(r"^XP$", variant_output, flags=re.MULTILINE)[1:]
        if len(blocks) != len(variants):
            raise RuntimeError(f"BIG wrote {len(blocks)} graphs for {len(variants)} variants")
        output_path.write_text("".join("XP" + blocks[index] for index in variant_of_trace))


class PatternMiningStep(PipelineStep):
    """Step 2: run SUBDUE on the saved instance graphs."""

    key = "2"
    title = "Pattern mining"
    parameters = [
        Parameter(
            "beam_width", "SUBDUE beam width?",
            "How many candidate patterns are kept at every extension step. "
            "Higher can find better patterns but is slower. 10 is the value "
            "the team chose for the paper (beam_table.py compares 4, 10 and 20).",
            default=10, cast=int,
        ),
        Parameter(
            "iterations", "SUBDUE iterations?",
            "After each iteration the graph is compressed with the best "
            "pattern found so far and searched again, building a hierarchy "
            "of patterns instead of just refining the same region.",
            default=3, cast=int,
        ),
        Parameter(
            "min_pattern_edges", "Minimum pattern size (edges)?",
            "Patterns smaller than this are not reported; a 1-edge pattern "
            "is just a single handover and rarely informative.",
            default=2, cast=int,
        ),
        Parameter(
            "max_pattern_edges", "Maximum pattern size (edges)?",
            "Patterns larger than this are not reported. 0 means SUBDUE's "
            "own default (half the number of edges in the graph).",
            default=0, cast=int,
        ),
        Parameter(
            "num_best", "Best patterns kept per iteration?",
            "How many top-ranked patterns are reported per iteration.",
            default=20, cast=int,
        ),
    ]

    def __init__(self, graphs_path=INSTANCE_GRAPH_DIR / "instance_graphs_pm4py.pkl",
                 output_dir=PATTERN_OUTPUT_DIR):
        self.graphs_path = Path(graphs_path)
        self.output_dir = Path(output_dir)
        self.patterns_csv_path = self.output_dir / "patterns.csv"
        self.patterns_pkl_path = self.output_dir / "patterns.pkl"

    def output_exists(self):
        return self.patterns_csv_path.exists()

    @staticmethod
    def build_subdue_graph(graphs, subdue_graph_module):
        """Combine all trace graphs into one disconnected SUBDUE graph."""
        combined = subdue_graph_module.Graph()
        entries = []
        for graph in graphs:
            for node, data in graph.nodes(data=True):
                entries.append({
                    "vertex": {
                        "id": str(node),
                        "attributes": {"label": str(data["label"])},
                    }
                })
            for source, target in graph.edges:
                entries.append({
                    "edge": {
                        "id": f"{source}-{target}",
                        "source": str(source),
                        "target": str(target),
                        "directed": "true",
                        "attributes": {"label": "next"},
                    }
                })
        combined.load_from_json(entries)
        return combined

    @staticmethod
    def pattern_to_networkx(definition):
        """Convert a native SUBDUE pattern definition to NetworkX."""
        graph = nx.DiGraph()
        for node_id, vertex in definition.vertices.items():
            graph.add_node(node_id, label=vertex.attributes.get("label", str(node_id)))
        for edge in definition.edges.values():
            graph.add_edge(edge.source.id, edge.target.id)
        return graph

    @staticmethod
    def ensure_subdue_importable():
        """subdue/'s modules must be on sys.path both to run SUBDUE and to
        unpickle a previously-saved ``patterns.pkl`` (whose Pattern/Graph
        objects are instances of those same modules' classes)."""
        import sys
        sys.path.insert(0, str(SUBDUE_DIR))

    def load_patterns(self):
        """Load the patterns step 2 already discovered and pickled."""
        self.ensure_subdue_importable()
        with open(self.patterns_pkl_path, "rb") as file:
            return pickle.load(file)

    def run_subdue(self, graphs, params):
        """Run the provided paper implementation of SUBDUE and return every
        pattern it found in the first iteration, best first ("Subs"); the
        top ``num_best`` of them are the reported patterns.

        SUBDUE only uses ``numBest`` to trim the list it reports, never in
        the search itself, so asking it to report everything finds exactly
        the same patterns, and the first ``num_best`` are the same top list."""
        self.ensure_subdue_importable()
        import Graph
        import Parameters
        import Subdue

        parameters = Parameters.Parameters()
        parameters.beamWidth = params["beam_width"]
        parameters.iterations = params["iterations"]
        parameters.minSize = params["min_pattern_edges"]
        parameters.maxSize = params["max_pattern_edges"]
        parameters.numBest = 10 ** 9  # report all; trimmed to num_best by the caller
        parameters.overlap = "vertex"
        subdue_graph = self.build_subdue_graph(graphs, Graph)
        parameters.limit = min(len(subdue_graph.edges) // 2, 1000)
        parameters.set_defaults_for_graph(subdue_graph)
        print("Running the provided SUBDUE implementation...", flush=True)
        # SUBDUE prints its whole search and every reported pattern with all
        # its instances: millions of lines on BPI 2017, so it is discarded.
        with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
            iterations = Subdue.Subdue(parameters, subdue_graph)
        return iterations[0] if iterations else []

    @staticmethod
    def search_summary(all_patterns, params, seconds):
        """'Subs' (every pattern SUBDUE found) and '% top subs' (the share
        of them that is reported), as in Table 6 of the reference paper."""
        top = min(params["num_best"], len(all_patterns))
        return {
            "beam_width": params["beam_width"],
            "subs": len(all_patterns),
            "top_subs": top,
            "top_subs_pct": round(100 * top / len(all_patterns), 2) if all_patterns else 0.0,
            "seconds": round(seconds, 1),
        }

    WRAP_LAYERS = 10  # draw_graph: layers per row before a long graph wraps

    @staticmethod
    def draw_graph(graph, title, output_path=None, highlight=None, ax=None, all_values=None):
        """Plot a directed graph left to right, like Figure 1 of the
        assignment: nodes in layers by their position in the graph (parallel
        branches above each other), each node showing its activity and its
        attribute value (role), coloured by that value. Used for individual
        instance graphs, discovered SUBDUE patterns and gold patterns.

        ``highlight``: optional set of nodes to emphasise (e.g. one pattern
        occurrence); the other nodes and edges are drawn faded.
        ``ax``: draw into this matplotlib axis instead of saving a file.
        ``all_values``: every value (role) of the whole log, so a value gets
        the same colour in every figure, not just within one.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch

        labels = nx.get_node_attributes(graph, "label")
        if nx.is_directed_acyclic_graph(graph) and graph.number_of_nodes():
            # Layer = position in the graph; long graphs wrap onto a new row
            # every WRAP_LAYERS layers, so a 25-event trace stays readable.
            generations = list(nx.topological_generations(graph))
            widest = max(len(nodes) for nodes in generations)
            row_height = widest + 1.2
            layout = {}
            for layer, nodes in enumerate(generations):
                row, column = divmod(layer, PatternMiningStep.WRAP_LAYERS)
                for position, node in enumerate(nodes):
                    layout[node] = (column, -row * row_height + position - (len(nodes) - 1) / 2)
            layers = min(len(generations), PatternMiningStep.WRAP_LAYERS)
            rows = -(-len(generations) // PatternMiningStep.WRAP_LAYERS)
        else:
            layout = nx.spring_layout(graph, seed=0)  # fixed seed: same layout on every run
            layers, widest, rows, row_height = 4, 3, 1, 3

        values = sorted({split_label(label)[1] for label in labels.values()})
        all_values = sorted(set(all_values or ()) | set(values))
        palette = plt.get_cmap("tab10" if len(all_values) <= 10 else "tab20")
        colour = {value: palette(index % palette.N) for index, value in enumerate(all_values)}

        own_figure = ax is None
        if own_figure:
            width = max(4.0, 1.8 * layers)
            figure, ax = plt.subplots(figsize=(width, max(2.5, 0.9 * rows * row_height + 0.6)))
        faded = (lambda node: highlight is not None and node not in highlight)
        nx.draw_networkx_edges(
            graph, pos=layout, ax=ax, arrows=True, arrowstyle="-|>", arrowsize=14,
            node_size=2600, width=1.4, min_source_margin=28, min_target_margin=28,
            edge_color=["#cccccc" if faded(source) or faded(target) else "#333333"
                        for source, target in graph.edges],
        )
        for node, (x, y) in layout.items():
            activity, value = split_label(labels.get(node, node))
            ax.text(x, y, f"{activity}\n{value}", ha="center", va="center", fontsize=7,
                    alpha=0.35 if faded(node) else 1.0,
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=colour.get(value, "white"),
                              alpha=0.25 if faded(node) else 0.55, edgecolor="#333333"))
        ax.legend(handles=[Patch(facecolor=colour[value], alpha=0.55, label=value) for value in values],
                  loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=7, frameon=False)
        ax.set_title(title, fontsize=9)
        ax.margins(x=0.08, y=0.25)
        ax.axis("off")
        if own_figure:
            figure.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close(figure)

    @staticmethod
    def all_values(graphs):
        """Every attribute value (role) occurring in the instance graphs."""
        return sorted({split_label(label)[1] for graph in graphs
                       for label in nx.get_node_attributes(graph, "label").values()})

    @staticmethod
    def case_ids(graphs):
        """The case id of every instance graph (set by step 1); graphs saved
        before case ids were stored fall back to their index."""
        return [str(graph.graph.get("case_id", index)) for index, graph in enumerate(graphs)]

    @staticmethod
    def subdue_traces(pattern):
        """Indices of the instance graphs in which SUBDUE reported an
        instance of ``pattern`` (node ids are 'g<graph index>_n<node>')."""
        return {
            int(str(vertex.id).split("_", 1)[0][1:])
            for instance in pattern.instances
            for vertex in instance.vertices
            if str(vertex.id).startswith("g")
        }

    def pattern_statistics(self, patterns, graphs):
        """Statistics of every discovered pattern, and the trace x pattern matrix.

        Two notions of "pattern P occurs in trace T":
        - SUBDUE's own instances (FREQ, traces, REP): SUBDUE reports
          non-overlapping instances only, so it can miss occurrences.
        - exact occurrence (support, support_pct, and the matrix): a
          subgraph check of P in T's instance graph (``contains_pattern``).
        """
        case_ids = self.case_ids(graphs)
        rows, matrix, subdue_matrix = [], {}, {}
        for rank, pattern in enumerate(patterns, start=1):
            name = f"P{rank}"
            pattern_graph = self.pattern_to_networkx(pattern.definition)
            subdue_traces = self.subdue_traces(pattern)
            occurs = [int(contains_pattern(graph, pattern_graph)) for graph in graphs]
            matrix[name] = occurs
            subdue_matrix[name] = [int(index in subdue_traces) for index in range(len(graphs))]
            rows.append({
                "pattern": name,
                "edges": pattern_graph.number_of_edges(),
                "FREQ": len(pattern.instances),
                "traces": len(subdue_traces),
                "REP": round(100 * len(subdue_traces) / len(graphs), 2),
                "support": sum(occurs),
                "support_pct": round(100 * sum(occurs) / len(graphs), 2),
                "subdue_value": pattern.value,
                "values": ", ".join(sorted({split_label(label)[1] for label in
                                            nx.get_node_attributes(pattern_graph, "label").values()})),
                "description": edges_text(pattern_graph),
            })
        matrix = pd.DataFrame(matrix, index=pd.Index(case_ids, name="case_id"))
        subdue_matrix = pd.DataFrame(subdue_matrix, index=pd.Index(case_ids, name="case_id"))
        return rows, matrix, subdue_matrix

    @staticmethod
    def plot_trace_pattern_heatmap(matrix, output_path, top=25):
        """Which cases contain which patterns: one row per distinct
        combination of patterns (the most common ``top``), with the number
        of cases that have exactly that combination."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if matrix.empty:
            return
        combinations = matrix.value_counts().head(top)
        grid = [list(combination) for combination in combinations.index]
        figure, ax = plt.subplots(figsize=(max(5, 0.45 * matrix.shape[1] + 2),
                                           max(3, 0.32 * len(grid) + 1.5)))
        ax.imshow(grid, cmap="Blues", vmin=0, vmax=1.4, aspect="auto")
        ax.set_xticks(range(matrix.shape[1]))
        ax.set_xticklabels(matrix.columns, rotation=90, fontsize=8)
        ax.set_yticks(range(len(grid)))
        ax.set_yticklabels([f"{count} cases ({100 * count / len(matrix):.1f}%)"
                            for count in combinations.values], fontsize=8)
        ax.set_xlabel("pattern")
        ax.set_title(f"Trace x pattern matrix: the {len(grid)} most common pattern combinations "
                     f"({combinations.sum()} of {len(matrix)} cases)", fontsize=9)
        figure.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(figure)

    def export_subdue_patterns(self, patterns, graphs, output_dir=None):
        """Save pattern statistics (FREQ/REP and exact support), the trace x
        pattern matrices (rows: case ids), a heatmap of the matrix and a PNG
        per pattern (activity/role labels, directed edges, support in the
        title) - into ``output_dir``."""
        output_dir = Path(output_dir or self.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        rows, matrix, subdue_matrix = self.pattern_statistics(patterns, graphs)

        all_values = self.all_values(graphs)
        for row, pattern in zip(rows, patterns):
            pattern_graph = self.pattern_to_networkx(pattern.definition)
            title = (f"{row['pattern']}: support {row['support']} cases ({row['support_pct']}%), "
                     f"FREQ={row['FREQ']} SUBDUE instances, value={pattern.value:.3f}")
            self.draw_graph(pattern_graph, title, output_dir / f"{row['pattern']}.png",
                            all_values=all_values)

        pd.DataFrame(rows).to_csv(output_dir / "patterns.csv", index=False)
        matrix.to_csv(output_dir / "trace_pattern_matrix.csv")
        subdue_matrix.to_csv(output_dir / "trace_pattern_matrix_subdue_instances.csv")
        self.plot_trace_pattern_heatmap(matrix, output_dir / "trace_pattern_heatmap.png")
        return rows

    def run(self, params):
        if not self.graphs_path.exists():
            raise FileNotFoundError(
                f"Run step 1 (instance graph generation) first; missing {self.graphs_path}"
            )

        with open(self.graphs_path, "rb") as file:
            graphs = pickle.load(file)

        started = time.time()
        all_patterns = self.run_subdue(graphs, params)
        search = self.search_summary(all_patterns, params, time.time() - started)
        patterns = all_patterns[:params["num_best"]]
        rows = self.export_subdue_patterns(patterns, graphs, self.output_dir)
        with open(self.patterns_pkl_path, "wb") as file:
            pickle.dump(patterns, file)
        with open(self.output_dir / "subdue_search.json", "w") as file:
            json.dump(search, file, indent=2)
        print(f"SUBDUE found {search['subs']} patterns; the top {len(rows)} "
              f"({search['top_subs_pct']}%) are saved in {self.output_dir}")


class EvaluationStep(PipelineStep):
    """Step 3: two independent checks, both written under ``output/evaluation``,
    both evaluating what steps 1 and 2 actually produced (no synthetic data).

    1. Alignment evaluation: how well the role-relabeled log fits the saved
       Petri net (PM4Py alignments) and the saved instance graphs (edit
       distance against the graph's topological event order, since instance
       graphs have no standard PM4Py alignment implementation).
    2. Pattern evaluation: the FREQ/REP/COV/DIV metrics, a trace-pattern
       matrix, and visualizations (discovered patterns and a few individual
       instance graphs), computed on the real instance graphs (step 1) and
       the real discovered patterns (step 2) - not a synthetic log.
    """

    key = "3"
    title = "Evaluation"
    parameters = []

    def __init__(self):
        self.petri_net_path = INSTANCE_GRAPH_DIR / "petri_net_pm4py.pnml"
        self.graphs_path = INSTANCE_GRAPH_DIR / "instance_graphs_pm4py.pkl"
        self.summary_path = EVALUATION_OUTPUT_DIR / "summary.json"
        self.pattern_evaluation_summary_path = PATTERN_EVALUATION_DIR / "summary.json"

    def output_exists(self):
        return self.summary_path.exists() and self.pattern_evaluation_summary_path.exists()

    @staticmethod
    def enriched_trace(trace):
        """The labels this trace's events were given for the saved model/graphs."""
        return [event.get("concept:name", "UNKNOWN") for event in trace]

    @staticmethod
    def edit_distance(left, right):
        """Return insert/delete/substitute distance and alignment statistics."""
        previous = list(range(len(right) + 1))
        for left_index, left_value in enumerate(left, start=1):
            current = [left_index]
            for right_index, right_value in enumerate(right, start=1):
                current.append(min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_value != right_value),
                ))
            previous = current

        distance = previous[-1]
        matches = sum(value in right for value in left)
        return distance, matches

    @staticmethod
    def graph_sequence(graph):
        """Return the graph's event labels in topological order."""
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError("An instance graph is cyclic; cannot define its order.")
        return [graph.nodes[node]["label"] for node in nx.topological_sort(graph)]

    @staticmethod
    def graph_index_by_case_id(instance_graph_step):
        """Map case id -> index into the saved instance graphs.

        The saved graphs carry no case id of their own, only their position
        in the full relabeled log they were built from (``run_big``'s chunks
        are consecutive slices of that log, in order). Looking the case id up
        in that same full log, rather than assuming ``log`` lines up with
        ``graphs`` index-for-index, is what makes this also work for ``log``
        being a *sample* of the full log (e.g. the 10% evaluation log), not
        just the full log itself.
        """
        full_log = xes_importer.apply(str(instance_graph_step.log_path))
        return {trace.attributes.get("concept:name"): index for index, trace in enumerate(full_log)}

    def evaluate_instance_graphs(self, log, graphs, instance_graph_step):
        """Compare every log trace with its corresponding saved instance graph."""
        index_by_case_id = self.graph_index_by_case_id(instance_graph_step)

        results = []
        skipped = 0
        for trace in log:
            case_id = trace.attributes.get("concept:name")
            index = index_by_case_id.get(case_id)
            if index is None or index >= len(graphs):
                skipped += 1
                continue
            observed = self.enriched_trace(trace)
            generated = self.graph_sequence(graphs[index])
            distance, matches = self.edit_distance(observed, generated)
            results.append({
                "trace": case_id,
                "events": len(observed),
                "graph_nodes": len(generated),
                "edit_distance": distance,
                "matching_labels": matches,
                "fitness": round(1 - distance / max(len(observed), len(generated)), 6),
            })
        if skipped:
            print(f"Skipped {skipped} trace(s) with no matching saved instance graph "
                  "(not in the full log the graphs were built from).", flush=True)
        return results

    def evaluate_petri_net(self, log):
        """Calculate PM4Py alignment fitness for role/lifecycle-relabeled traces."""
        net, initial_marking, final_marking = pnml_importer.apply(str(self.petri_net_path))
        enriched_log = copy.deepcopy(log)
        for trace in enriched_log:
            for event, label in zip(trace, self.enriched_trace(trace)):
                event["concept:name"] = label
        alignments_result = alignments.apply(enriched_log, net, initial_marking, final_marking)
        results = []
        for index, alignment in enumerate(alignments_result):
            results.append({
                "trace": index,
                "cost": alignment.get("cost"),
                "fitness": alignment.get("fitness"),
                "queued_states": alignment.get("visited_states"),
            })
        return results

    @staticmethod
    def summary(results, name):
        fitness = [row["fitness"] for row in results]
        return {
            "model": name,
            "traces": len(results),
            "mean_fitness": round(sum(fitness) / len(fitness), 6),
            "perfect_fitness": sum(value == 1 for value in fitness),
            "min_fitness": min(fitness),
            "max_fitness": max(fitness),
        }

    def run_alignment_evaluation(self, params):
        """Alignment of the role-based log against the Petri net, and
        against the instance graphs; written to ``output/evaluation``.

        Uses the exact log the Petri net and instance graphs were built from
        (step 1's relabeled log) - not a separate sample - so there is
        nothing to ask and no relabeling mismatch to worry about.
        """
        EVALUATION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        instance_graph_step = InstanceGraphStep()
        log = xes_importer.apply(str(instance_graph_step.log_path))
        print(f"Loaded {len(log)} traces from {instance_graph_step.log_path}")

        print("Calculating Petri-net alignments...", flush=True)
        petri_results = self.evaluate_petri_net(log)
        print("Calculating instance-graph alignments...", flush=True)
        with open(self.graphs_path, "rb") as file:
            graphs = pickle.load(file)
        graph_results = self.evaluate_instance_graphs(log, graphs, instance_graph_step)

        summaries = [
            self.summary(petri_results, "Petri net"),
            self.summary(graph_results, "Instance graphs"),
        ]
        with open(self.summary_path, "w") as file:
            json.dump(summaries, file, indent=2)
        for name, rows in [
            ("petri_net_alignments.csv", petri_results),
            ("instance_graph_alignments.csv", graph_results),
        ]:
            with open(EVALUATION_OUTPUT_DIR / name, "w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        print(json.dumps(summaries, indent=2))
        print(f"Saved alignment results in {EVALUATION_OUTPUT_DIR}")

    # -- Pattern evaluation: FREQ/REP/COV/DIV on the real step 1/2 output --

    def pattern_metrics(self, patterns, graphs):
        """COV: share of all edges across every instance graph that are
        covered by at least one pattern instance. DIV: average pairwise
        dissimilarity (1 - Jaccard) between patterns' activity sets - 0 if
        all patterns use the same activities, 1 if none overlap at all.
        """
        total_edges = sum(graph.number_of_edges() for graph in graphs)
        covered_edges = {
            (edge.source.id, edge.target.id)
            for pattern in patterns
            for instance in pattern.instances
            for edge in instance.edges
        }
        coverage = round(len(covered_edges) / total_edges, 4) if total_edges else 0.0

        label_sets = [
            frozenset(vertex.attributes.get("label") for vertex in pattern.definition.vertices.values())
            for pattern in patterns
        ]
        dissimilarities = []
        for i in range(len(label_sets)):
            for j in range(i + 1, len(label_sets)):
                union = label_sets[i] | label_sets[j]
                if union:
                    dissimilarities.append(1 - len(label_sets[i] & label_sets[j]) / len(union))
        diversity = round(sum(dissimilarities) / len(dissimilarities), 4) if dissimilarities else 0.0
        return {"COV": coverage, "DIV": diversity}

    def run_pattern_evaluation(self, params):
        """FREQ/REP/COV/DIV, a trace-pattern matrix, and visualizations
        (discovered patterns + a few individual instance graphs) - all
        computed on the real instance graphs (step 1) and the real
        discovered patterns (step 2), under ``output/evaluation/pattern_evaluation``.

        Petri-net alignment/fitness of these same traces is covered by
        ``run_alignment_evaluation`` already, so it is not repeated here.
        """
        pattern_mining_step = PatternMiningStep()
        if not pattern_mining_step.patterns_pkl_path.exists():
            raise FileNotFoundError(
                "Run step 2 (pattern mining) first; missing "
                f"{pattern_mining_step.patterns_pkl_path}"
            )

        PATTERN_EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.graphs_path, "rb") as file:
            graphs = pickle.load(file)
        patterns = pattern_mining_step.load_patterns()

        rows = pattern_mining_step.export_subdue_patterns(patterns, graphs, PATTERN_EVALUATION_DIR)
        for index in range(min(3, len(graphs))):
            pattern_mining_step.draw_graph(
                graphs[index], f"Instance graph {index}",
                PATTERN_EVALUATION_DIR / f"instance_graph_{index}.png",
                all_values=pattern_mining_step.all_values(graphs))

        summary = {
            "instance_graphs": len(graphs),
            "discovered_patterns": len(patterns),
            **self.pattern_metrics(patterns, graphs),
        }
        with open(self.pattern_evaluation_summary_path, "w") as file:
            json.dump(summary, file, indent=2)
        print(json.dumps(summary, indent=2))
        print(f"Mined-pattern evaluation of {len(rows)} patterns saved in {PATTERN_EVALUATION_DIR}")

    def run(self, params):
        if not self.petri_net_path.exists() or not self.graphs_path.exists():
            raise FileNotFoundError(
                "Run step 1 (instance graph generation) first; missing the "
                f"Petri net or {self.graphs_path}"
            )
        self.run_alignment_evaluation(params)
        self.run_pattern_evaluation(params)


class SyntheticValidationStep(PipelineStep):
    """Step 4: run steps 1 and 2 on the small hand-made log in
    ``data/synthetic/`` and score SUBDUE's patterns against that log's gold
    standard (the organizational patterns put into it by design, see
    ``data/synthetic/README.md``). Everything is written to
    ``output/synthetic validation/``, never over the BPI 2017 results.

    Two evaluations, so a missing pattern can be traced to its cause:
    1. ``eval1_known_roles``: events labeled with the known ``department``
       (the roles are given), so only the Petri net, BIG and SUBDUE are tested.
    2. ``eval2_full_pipeline``: events labeled with the employee
       (``org:resource``), grouped into roles by pm4py role discovery as on
       BPI 2017. Each discovered role is mapped to the department most of its
       events come from, and then scored the same way. A gold pattern found
       in 1 but not in 2 was lost by the role discovery.
    ``comparison/`` puts both side by side, per gold pattern.

    Three levels per evaluation:
    a. gold patterns in the instance graphs (Petri net + BIG, not SUBDUE),
    b. SUBDUE's patterns against the gold patterns (exact and containment),
    c. per gold pattern, the cases of its best-matching SUBDUE pattern.
    """

    key = "4"
    title = "Synthetic validation (gold standard)"
    parameters = [
        Parameter(
            "noise_threshold", "Inductive Miner noise threshold (0-1)?",
            "The same value as for BPI 2017 (step 1). The deviating cases "
            "(C25-C30, 2 cases per deviation) are rare, so a higher value can "
            "leave them out of the Petri net; level a shows whether it did.",
            default=0.2, cast=float,
        ),
        Parameter(
            "beam_width", "SUBDUE beam width?",
            "Same meaning as in step 2.",
            default=10, cast=int,
        ),
        Parameter(
            "roles_threshold", "Role similarity threshold for evaluation 2 (0-1)?",
            "Same meaning as in step 1; pm4py's own default is 0.65.",
            default=0.65, cast=float,
        ),
        Parameter(
            "min_pattern_edges", "Minimum pattern size (edges)?",
            "1 so that the one-edge gold pattern (G1) can also be found exactly.",
            default=1, cast=int,
        ),
        Parameter(
            "max_pattern_edges", "Maximum pattern size (edges)?",
            "0 means SUBDUE's own default (half the number of edges in the graph).",
            default=0, cast=int,
        ),
        Parameter(
            "num_best", "Best patterns kept?",
            "How many top-ranked SUBDUE patterns are scored against the gold standard.",
            default=20, cast=int,
        ),
    ]
    PRECISION_AT = (5, 10, 20)
    # evaluation folder -> (attribute that labels the events, group it into roles?)
    EVALUATIONS = {
        "eval1_known_roles": ("department", False),
        "eval2_full_pipeline": ("org:resource", True),
    }

    def __init__(self):
        self.log_csv_path = SYNTHETIC_DATA_DIR / "synthetic_log.csv"
        self.gold_csv_path = SYNTHETIC_DATA_DIR / "synthetic_gold_standard.csv"
        self.output_dir = SYNTHETIC_OUTPUT_DIR
        self.xes_path = self.output_dir / "synthetic_log.xes"
        self.comparison_dir = self.output_dir / "comparison"

    def output_exists(self):
        return (self.comparison_dir / "comparison.csv").exists()

    def steps(self, evaluation):
        """Steps 1 and 2, writing into this evaluation's own folder."""
        instance_graph_step = InstanceGraphStep(
            self.xes_path, self.output_dir / evaluation / "instance graphs")
        pattern_mining_step = PatternMiningStep(
            instance_graph_step.graphs_path, self.output_dir / evaluation / "patterns")
        return instance_graph_step, pattern_mining_step

    # -- input ------------------------------------------------------------

    def write_xes(self):
        """synthetic_log.csv -> XES with the standard keys, plus 'department'."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        frame = pd.read_csv(self.log_csv_path, dtype=str).rename(columns={
            "case_id": "case:concept:name", "activity": "concept:name",
            "resource": "org:resource", "timestamp": "time:timestamp",
        })
        frame["time:timestamp"] = pd.to_datetime(frame["time:timestamp"])
        xes_exporter.apply(log_converter.apply(frame, variant=log_converter.Variants.TO_EVENT_LOG),
                           str(self.xes_path))

    @staticmethod
    def expand_cases(text):
        """'C01-C03;C07' -> ['C01', 'C02', 'C03', 'C07']."""
        cases = []
        for part in str(text).split(";"):
            part = part.strip()
            match = re.fullmatch(r"([A-Za-z]*)(\d+)-([A-Za-z]*)(\d+)", part)
            if match:
                prefix, first, _, last = match.groups()
                cases += [f"{prefix}{number:0{len(first)}d}"
                          for number in range(int(first), int(last) + 1)]
            elif part:
                cases.append(part)
        return cases

    @staticmethod
    def edges_to_graph(text):
        """'A -> B; B -> C' -> a DiGraph with one node per label."""
        graph = nx.DiGraph()
        for edge in str(text).split(";"):
            source, target = (label.strip() for label in edge.split("->"))
            graph.add_node(source, label=source)
            graph.add_node(target, label=target)
            graph.add_edge(source, target)
        return graph

    def load_gold(self):
        gold = pd.read_csv(self.gold_csv_path, dtype=str)
        return [{
            "id": row["id"], "name": row["name"],
            "graph": self.edges_to_graph(row["edges"]),
            "expected": set(self.expand_cases(row["expected_cases"])),
        } for _, row in gold.iterrows()]

    # -- evaluation 2: discovered roles -> departments ----------------------

    def role_discovery_table(self, resource_roles_path):
        """One row per employee: their department (from the log), the role
        pm4py gave them, and the department that role is mapped to - the
        department most of the role's events come from."""
        log = pd.read_csv(self.log_csv_path, dtype=str)
        events = log.groupby(["resource", "department"]).size().rename("events").reset_index()
        # an employee's department: the one most of their events are in
        department_of = (events.sort_values("events", ascending=False)
                         .drop_duplicates("resource").set_index("resource")["department"])
        roles = pd.read_csv(resource_roles_path, dtype=str).rename(columns={"org:resource": "employee"})
        roles["department"] = roles["employee"].map(department_of)
        roles["events"] = roles["employee"].map(log["resource"].value_counts())
        per_role = roles.groupby(["role", "department"])["events"].sum().reset_index()
        role_department = (per_role.sort_values("events", ascending=False)
                           .drop_duplicates("role").set_index("role")["department"])
        roles["role_department"] = roles["role"].map(role_department)
        roles["correct"] = roles["department"] == roles["role_department"]
        return roles.sort_values(["department", "employee"])

    @staticmethod
    def role_mapping(role_table):
        """discovered role -> department, from ``role_discovery_table``."""
        return dict(zip(role_table["role"], role_table["role_department"]))

    @staticmethod
    def role_discovery_scores(role_table):
        roles_per_department = role_table.groupby("department")["role"].nunique()
        departments_per_role = role_table.groupby("role")["department"].nunique()
        return {
            "employees": len(role_table),
            "departments": int(role_table["department"].nunique()),
            "roles_discovered": int(role_table["role"].nunique()),
            "employees_in_role_of_own_department_pct": round(100 * role_table["correct"].mean(), 2),
            "departments_split_over_roles": sorted(roles_per_department[roles_per_department > 1].index),
            "roles_mixing_departments": sorted(departments_per_role[departments_per_role > 1].index),
        }

    @staticmethod
    def map_labels(graph, mapping):
        """A copy of ``graph`` with every label's value translated by
        ``mapping`` ('Decide_Role_2' -> 'Decide_Credit'); values not in
        ``mapping`` stay as they are."""
        mapped = graph.copy()
        for node, label in graph.nodes(data="label"):
            activity, value = split_label(label)
            mapped.nodes[node]["label"] = f"{activity}_{mapping.get(value, value)}"
        return mapped

    # -- metrics ------------------------------------------------------------

    @staticmethod
    def precision_recall(found, expected):
        """Precision, recall and F1 of a found set against an expected set."""
        true_positives = len(found & expected)
        precision = true_positives / len(found) if found else 0.0
        recall = true_positives / len(expected) if expected else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return round(precision, 4), round(recall, 4), round(f1, 4)

    @staticmethod
    def same_pattern(discovered, gold):
        """Exact match: the same graph with the same labels."""
        return nx.is_isomorphic(discovered, gold, node_match=label_matcher)

    @staticmethod
    def contains_match(discovered, gold):
        """Containment match: the discovered pattern contains the gold
        pattern, or is contained in it with at least 2 edges."""
        return (contains_pattern(discovered, gold)
                or (discovered.number_of_edges() >= 2 and contains_pattern(gold, discovered)))

    def score_patterns(self, pattern_graphs, gold, criterion):
        """Level b for one match criterion: which gold patterns each
        discovered pattern matches, precision, recall, F1 and precision@k."""
        matches = [{entry["id"] for entry in gold if criterion(graph, entry["graph"])}
                   for graph in pattern_graphs]
        matched_patterns = sum(bool(found) for found in matches)
        matched_gold = {gold_id for found in matches for gold_id in found}
        precision = matched_patterns / len(pattern_graphs) if pattern_graphs else 0.0
        recall = len(matched_gold) / len(gold)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        scores = {
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "gold_found": sorted(matched_gold),
            "gold_missed": sorted({entry["id"] for entry in gold} - matched_gold),
        }
        for k in self.PRECISION_AT:
            if k <= len(pattern_graphs):
                scores[f"precision@{k}"] = round(sum(bool(found) for found in matches[:k]) / k, 4)
        return matches, scores

    def score(self, graphs, case_ids, pattern_graphs, gold):
        """Levels a, b and c for one set of instance graphs and patterns,
        both already labeled with departments."""
        # a. are the gold patterns in the instance graphs at all?
        gold_rows = []
        for entry in gold:
            found = {case for case, graph in zip(case_ids, graphs)
                     if contains_pattern(graph, entry["graph"])}
            precision, recall, f1 = self.precision_recall(found, entry["expected"])
            gold_rows.append({
                "gold": entry["id"], "name": entry["name"], "expected_cases": len(entry["expected"]),
                "found_cases": len(found), "precision": precision, "recall": recall, "f1": f1,
                "missing": ";".join(sorted(entry["expected"] - found)),
                "unexpected": ";".join(sorted(found - entry["expected"])),
            })

        # b. SUBDUE's patterns against the gold standard
        exact_matches, exact_scores = self.score_patterns(pattern_graphs, gold, self.same_pattern)
        contain_matches, contain_scores = self.score_patterns(pattern_graphs, gold, self.contains_match)
        discovered_labels = {(graph.nodes[source]["label"], graph.nodes[target]["label"])
                             for graph in pattern_graphs for source, target in graph.edges}
        gold_labels = {(source, target) for entry in gold for source, target in entry["graph"].edges}
        edge_precision, edge_recall, edge_f1 = self.precision_recall(discovered_labels, gold_labels)

        pattern_rows = []
        for rank, (graph, exact, contained) in enumerate(
                zip(pattern_graphs, exact_matches, contain_matches), start=1):
            pattern_rows.append({
                "pattern": f"P{rank}", "edges": graph.number_of_edges(),
                "exact_match": ";".join(sorted(exact)), "containment_match": ";".join(sorted(contained)),
                "description": edges_text(graph),
            })

        # c. per gold pattern: the cases of its best-matching SUBDUE pattern
        case_rows = []
        for entry in gold:
            best = None
            for rank, (graph, contained) in enumerate(zip(pattern_graphs, contain_matches), start=1):
                if entry["id"] not in contained:
                    continue
                found = {case for case, instance in zip(case_ids, graphs)
                         if contains_pattern(instance, graph)}
                scores = self.precision_recall(found, entry["expected"])
                if best is None or scores[2] > best[1][2]:
                    best = (f"P{rank}", scores)
            pattern_name, (precision, recall, f1) = best or ("", (0.0, 0.0, 0.0))
            case_rows.append({"gold": entry["id"], "best_pattern": pattern_name,
                              "precision": precision, "recall": recall, "f1": f1})

        def mean(rows, key):
            return round(sum(row[key] for row in rows) / len(rows), 4) if rows else 0.0

        summary = {
            "a_gold_in_instance_graphs": {"mean_precision": mean(gold_rows, "precision"),
                                          "mean_recall": mean(gold_rows, "recall")},
            "b_patterns_containment": contain_scores,
            "b_patterns_exact": exact_scores,
            "b_edges": {"precision": edge_precision, "recall": edge_recall, "f1": edge_f1},
            "c_cases_of_best_match": {"mean_precision": mean(case_rows, "precision"),
                                      "mean_recall": mean(case_rows, "recall"),
                                      "mean_f1": mean(case_rows, "f1")},
        }
        return gold_rows, pattern_rows, case_rows, summary

    def evaluate(self, evaluation, params, gold):
        """Run steps 1 and 2 for one evaluation and score the result."""
        attribute, group_roles = self.EVALUATIONS[evaluation]
        output_dir = self.output_dir / evaluation
        instance_graph_step, pattern_mining_step = self.steps(evaluation)
        print(f"\n===== {evaluation}: events labeled with {attribute}"
              f"{' grouped into discovered roles' if group_roles else ''} =====", flush=True)
        instance_graph_step.run({
            "attribute": attribute, "group_roles": group_roles,
            "roles_threshold": params["roles_threshold"], "collapse_lifecycle": False,
            "noise_threshold": params["noise_threshold"], "workers": 1,
        })
        pattern_mining_step.run({
            "beam_width": params["beam_width"], "iterations": 1,
            "min_pattern_edges": params["min_pattern_edges"],
            "max_pattern_edges": params["max_pattern_edges"], "num_best": params["num_best"],
        })

        with open(instance_graph_step.graphs_path, "rb") as file:
            graphs = pickle.load(file)
        patterns = pattern_mining_step.load_patterns()
        with open(pattern_mining_step.output_dir / "subdue_search.json") as file:
            search = json.load(file)

        mapping, roles = {}, {}
        if group_roles:
            role_table = self.role_discovery_table(instance_graph_step.resource_roles_path)
            role_table.to_csv(output_dir / "role_discovery.csv", index=False)
            mapping = self.role_mapping(role_table)
            roles = self.role_discovery_scores(role_table)
            print("\n--- role discovery: employee -> discovered role -> department ---")
            print(role_table.to_string(index=False))

        mapped_graphs = [self.map_labels(graph, mapping) for graph in graphs]
        pattern_graphs = [self.map_labels(pattern_mining_step.pattern_to_networkx(pattern.definition),
                                          mapping) for pattern in patterns]
        gold_rows, pattern_rows, case_rows, scores = self.score(
            mapped_graphs, PatternMiningStep.case_ids(graphs), pattern_graphs, gold)

        pd.DataFrame(gold_rows).to_csv(output_dir / "gold_in_graphs.csv", index=False)
        pd.DataFrame(pattern_rows).to_csv(output_dir / "pattern_matching.csv", index=False)
        pd.DataFrame(case_rows).to_csv(output_dir / "gold_cases.csv", index=False)
        summary = {
            "settings": {**params, "attribute": attribute, "group_roles": group_roles},
            "traces": len(graphs), "discovered_patterns": len(patterns), "gold_patterns": len(gold),
            "subdue_search": search,
            **({"role_discovery": roles, "role_to_department": mapping} if group_roles else {}),
            **scores,
            **EvaluationStep().pattern_metrics(patterns, graphs),
        }
        with open(output_dir / "summary.json", "w") as file:
            json.dump(summary, file, indent=2)

        print("\n--- a. gold patterns in the instance graphs ---")
        print(pd.DataFrame(gold_rows).drop(columns=["missing", "unexpected"]).to_string(index=False))
        print("\n--- b. SUBDUE patterns against the gold standard ---")
        print(pd.DataFrame(pattern_rows).drop(columns=["description"]).to_string(index=False))
        print("\n--- c. cases of the best-matching pattern per gold pattern ---")
        print(pd.DataFrame(case_rows).to_string(index=False))
        print(f"{evaluation} saved in {output_dir}")
        return {"summary": summary, "gold": gold_rows, "cases": case_rows,
                "values": PatternMiningStep.all_values(mapped_graphs)}

    # -- comparison -----------------------------------------------------------

    @staticmethod
    def diagnosis(in_graphs_1, found_1, found_2):
        """Where a gold pattern got lost, from the two evaluations."""
        if found_1 and found_2:
            return "found in both"
        if found_1:
            return "lost by role discovery"
        if found_2:
            return "found only with discovered roles"
        if in_graphs_1 < 1:
            return "not (fully) in the instance graphs: Petri net / BIG"
        return "missed by SUBDUE"

    def compare(self, results, gold):
        """Both evaluations side by side: per gold pattern, and overall."""
        self.comparison_dir.mkdir(parents=True, exist_ok=True)
        (name_1, result_1), (name_2, result_2) = results.items()
        found = {name: set(result["summary"]["b_patterns_containment"]["gold_found"])
                 for name, result in results.items()}
        rows = []
        for index, entry in enumerate(gold):
            row = {"gold": entry["id"], "name": entry["name"], "expected_cases": len(entry["expected"])}
            for label, (name, result) in zip(("eval1", "eval2"), results.items()):
                row[f"{label}_a_recall"] = result["gold"][index]["recall"]
                row[f"{label}_b_found"] = entry["id"] in found[name]
                row[f"{label}_c_best_pattern"] = result["cases"][index]["best_pattern"]
                row[f"{label}_c_f1"] = result["cases"][index]["f1"]
            row["diagnosis"] = self.diagnosis(row["eval1_a_recall"], row["eval1_b_found"],
                                              row["eval2_b_found"])
            rows.append(row)
        comparison = pd.DataFrame(rows)
        comparison.to_csv(self.comparison_dir / "comparison.csv", index=False)

        overall = []
        for name, result in results.items():
            summary = result["summary"]
            overall.append({
                "evaluation": name,
                "a_mean_recall": summary["a_gold_in_instance_graphs"]["mean_recall"],
                "b_containment_precision": summary["b_patterns_containment"]["precision"],
                "b_containment_recall": summary["b_patterns_containment"]["recall"],
                "b_containment_f1": summary["b_patterns_containment"]["f1"],
                "b_exact_recall": summary["b_patterns_exact"]["recall"],
                "b_edge_precision": summary["b_edges"]["precision"],
                "b_edge_recall": summary["b_edges"]["recall"],
                "c_mean_f1": summary["c_cases_of_best_match"]["mean_f1"],
                "COV": summary["COV"], "DIV": summary["DIV"],
                "subs": summary["subdue_search"]["subs"],
                "top_subs_pct": summary["subdue_search"]["top_subs_pct"],
                "employees_in_role_of_own_department_pct": summary.get("role_discovery", {}).get(
                    "employees_in_role_of_own_department_pct", ""),
            })
        pd.DataFrame(overall).to_csv(self.comparison_dir / "summary_comparison.csv", index=False)
        self.plot_comparison(comparison, self.comparison_dir / "comparison.png")

        print("\n===== comparison: known roles (eval1) vs discovered roles (eval2) =====")
        print(comparison.drop(columns=["name"]).to_string(index=False))
        print()
        print(pd.DataFrame(overall).set_index("evaluation").T.to_string())
        print(f"Comparison saved in {self.comparison_dir}")

    @staticmethod
    def plot_comparison(comparison, output_path):
        """Per gold pattern: F1 of the cases of its best-matching SUBDUE
        pattern (level c; 0 = not found), known vs discovered roles."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        positions = range(len(comparison))
        figure, ax = plt.subplots(figsize=(6, 3))
        for offset, (column, label, colour) in zip((-0.2, 0.2), (
                ("eval1_c_f1", "1: known roles", "#2a6f97"),
                ("eval2_c_f1", "2: discovered roles", "#e07a1f"))):
            ax.bar([position + offset for position in positions], comparison[column],
                   width=0.38, label=label, color=colour)
        ax.set_xticks(list(positions))
        ax.set_xticklabels(comparison["gold"])
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("F1 (cases), 0 = not found")
        ax.set_title("Gold patterns recovered by SUBDUE (level c)", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
        figure.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(figure)

    def run(self, params):
        self.write_xes()
        gold = self.load_gold()
        results = {evaluation: self.evaluate(evaluation, params, gold)
                   for evaluation in self.EVALUATIONS}

        gold_dir = self.output_dir / "gold"
        gold_dir.mkdir(parents=True, exist_ok=True)
        for entry in gold:
            PatternMiningStep.draw_graph(
                entry["graph"], f"{entry['id']}: {entry['name']} "
                f"(expected in {len(entry['expected'])} cases)", gold_dir / f"{entry['id']}.png",
                all_values=results["eval1_known_roles"]["values"])
        self.compare(results, gold)


class Pipeline:
    """Terminal menu that lets the user pick which step to (re)run."""

    ALL_STEPS_KEY = "A"

    def __init__(self):
        self.steps = [InstanceGraphStep(), PatternMiningStep(), EvaluationStep(),
                      SyntheticValidationStep()]

    def print_menu(self):
        print("\n" + "=" * 60)
        print("BPI 2017 organizational pattern mining pipeline")
        print("=" * 60)
        for step in self.steps:
            status = "done" if step.output_exists() else "not run yet"
            print(f"  {step.key}. {step.title}  [{status}]")
        print(f"  {self.ALL_STEPS_KEY}. Run all steps, in order (1, 2, 3, then 4)")
        print("  0. Exit")

    def run(self):
        while True:
            self.print_menu()
            choice = input("\nSelect a step to run: ").strip()
            if choice == "0":
                return
            if choice.upper() == self.ALL_STEPS_KEY:
                for step in self.steps:
                    self.run_step(step)
                continue
            step = next((s for s in self.steps if s.key == choice), None)
            if step is None:
                print(f"'{choice}' is not a valid choice.")
                continue
            self.run_step(step)

    @staticmethod
    def run_step(step):
        params = step.ask_parameters()
        step.run(params)


def main():
    Pipeline().run()


if __name__ == "__main__":
    main()

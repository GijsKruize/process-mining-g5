"""Single entry point for the BPI 2017 organizational pattern mining pipeline.

Run with::

    python main.py

A numbered menu lets you pick which step to (re)run. Each step asks for its
own parameters (press Enter to accept the suggested default) and then runs
straight through - no further questions.

The three steps are:
    1. Instance graph generation  - relabel the log (roles + lifecycle),
       discover a Petri net, run BIG, save the instance graphs.
    2. Pattern mining             - run SUBDUE on the saved instance graphs.
    3. Evaluation                 - alignment fitness of the Petri net and
       the instance graphs against a sample of the log.
"""
import copy
import csv
import json
import os
import pickle
import re
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
    """Step 1: relabel the log, discover a Petri net, run BIG, save the graphs."""

    key = "1"
    title = "Instance graph generation"
    parameters = [
        Parameter(
            "group_roles", "Group resources into roles before relabeling?",
            "Replaces each resource (org:resource) by its discovered role "
            "(pm4py role mining) instead of using the raw resource name. "
            "org:resource alone has 134 distinct values, which makes both the "
            "Petri net and BIG slow; grouping into roles cuts that down a lot.",
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
            "deviating behaviour; lower values give a stricter model. 0.4 is "
            "the value this project was tuned and evaluated with.",
            default=0.4, cast=float,
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

    def __init__(self):
        self.log_path = INSTANCE_GRAPH_DIR / "BPI2017Denied_pm4py.xes"
        self.petri_net_path = INSTANCE_GRAPH_DIR / "petri_net_pm4py.pnml"
        self.big_output_path = INSTANCE_GRAPH_DIR / "graph_pm4py.g"
        self.graphs_path = INSTANCE_GRAPH_DIR / "instance_graphs_pm4py.pkl"
        self.resource_roles_path = INSTANCE_GRAPH_DIR / "resource_roles.csv"
        self.settings_path = INSTANCE_GRAPH_DIR / "generation_settings.json"

    def output_exists(self):
        return self.graphs_path.exists()

    # -- relabeling -----------------------------------------------------

    def strip_lifecycle(self, activity):
        """'W-Validate-application-start' -> 'W-Validate-application'.

        Other activities are returned unchanged."""
        if not activity.startswith(self.WORK_ITEM_PREFIX):
            return activity
        return self.LIFECYCLE_SUFFIX.sub("", activity)

    def discover_roles(self, event_log, roles_threshold):
        """Map every resource to its dominant role: the discovered role in
        which it performs most of its events. Role_1 is the role with the
        most events overall."""
        frame = pd.DataFrame({
            "resource": event_log["org:resource"].fillna("UNKNOWN").astype(str),
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

    def relabel_events(self, event_log, role_mapping, collapse_lifecycle):
        """Add the 'activity_selectedAttribute' label: roles first (if given),
        then the lifecycle collapse. A role change inside a work item is a
        handover and stays two events."""
        event_log = event_log.copy()
        activity = event_log["concept:name"].fillna("UNKNOWN").astype(str)
        value = event_log["org:resource"].fillna("UNKNOWN").astype(str)
        if role_mapping is not None:
            value = value.map(role_mapping).fillna("UNKNOWN")
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
        print("Loading event log...", flush=True)
        event_log = log_converter.apply(
            xes_importer.apply(str(DATASET_PATH)),
            variant=log_converter.Variants.TO_DATA_FRAME,
        )

        role_mapping = None
        if params["group_roles"]:
            role_mapping = self.discover_roles(event_log, params["roles_threshold"])
            pd.DataFrame(sorted(role_mapping.items()), columns=["resource", "role"]).to_csv(
                self.resource_roles_path, index=False
            )
            print(f"Grouped {len(role_mapping)} resources into {len(set(role_mapping.values()))} "
                  f"roles (saved to {self.resource_roles_path})", flush=True)

        events_before = len(event_log)
        event_log = self.relabel_events(event_log, role_mapping, params["collapse_lifecycle"])
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
        INSTANCE_GRAPH_DIR.mkdir(parents=True, exist_ok=True)
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
        for index, graph in enumerate(graphs):
            graph.graph["graph_index"] = index
        with open(self.graphs_path, "wb") as file:
            pickle.dump(graphs, file)

        print(f"Saved {len(graphs)} instance graphs in {INSTANCE_GRAPH_DIR}")

    def run_big(self, big_event_log, net, initial_marking, final_marking, workers):
        """Run BIG on the log in parallel, chunked across worker processes.

        BIG treats every trace independently, so the log is cut into
        consecutive chunks and each chunk runs BIG.run_big_chunk in its own
        process; the chunks' outputs are joined back in their original order,
        giving the same result a single BIG run on the whole log would.
        """
        log_path = self.log_path
        output_path = self.big_output_path
        chunk_dir = INSTANCE_GRAPH_DIR

        trace_count = len(big_event_log)
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
            list(pool.map(BIG.run_big_chunk, chunks))

        output_path.write_text(
            "\n".join(Path(chunk[2]).read_text() for chunk in chunks)
        )
        for chunk in chunks:
            Path(chunk[2]).unlink()


class PatternMiningStep(PipelineStep):
    """Step 2: run SUBDUE on the saved instance graphs."""

    key = "2"
    title = "Pattern mining"
    parameters = [
        Parameter(
            "beam_width", "SUBDUE beam width?",
            "How many candidate patterns are kept at every extension step. "
            "Higher can find better patterns but is slower.",
            default=4, cast=int,
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

    def __init__(self):
        self.graphs_path = INSTANCE_GRAPH_DIR / "instance_graphs_pm4py.pkl"
        self.patterns_csv_path = PATTERN_OUTPUT_DIR / "patterns.csv"
        self.patterns_pkl_path = PATTERN_OUTPUT_DIR / "patterns.pkl"

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
        """Run the provided paper implementation of SUBDUE."""
        self.ensure_subdue_importable()
        import Graph
        import Parameters
        import Subdue

        parameters = Parameters.Parameters()
        parameters.beamWidth = params["beam_width"]
        parameters.iterations = params["iterations"]
        parameters.minSize = params["min_pattern_edges"]
        parameters.maxSize = params["max_pattern_edges"]
        parameters.numBest = params["num_best"]
        parameters.overlap = "vertex"
        subdue_graph = self.build_subdue_graph(graphs, Graph)
        parameters.limit = min(len(subdue_graph.edges) // 2, 1000)
        parameters.set_defaults_for_graph(subdue_graph)
        print("Running the provided SUBDUE implementation...", flush=True)
        iterations = Subdue.Subdue(parameters, subdue_graph)
        return iterations[0] if iterations else []

    @staticmethod
    def draw_graph(graph, title, output_path):
        """Plot a directed graph with its node labels (activity/role), used for
        both individual instance graphs and discovered SUBDUE patterns."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(8, 5))
        node_labels = nx.get_node_attributes(graph, "label")
        layout = nx.spring_layout(graph, seed=0)  # fixed seed: same layout on every run
        nx.draw_networkx(
            graph, pos=layout, node_size=900, font_size=7,
            labels=node_labels, arrows=True, with_labels=True,
        )
        plt.title(title)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

    def pattern_statistics(self, patterns, graphs):
        """FREQ (instance count) and REP (% of traces containing the pattern)
        for every discovered pattern, plus which traces contain it - the basis
        of both patterns.csv and the trace-pattern matrix."""
        rows = []
        trace_sets = []
        for rank, pattern in enumerate(patterns, start=1):
            pattern_graph = self.pattern_to_networkx(pattern.definition)
            traces = sorted({
                int(str(vertex.id).split("_", 1)[0][1:])
                for instance in pattern.instances
                for vertex in instance.vertices
                if str(vertex.id).startswith("g")
            })
            trace_sets.append(traces)
            rows.append({
                "pattern": f"P{rank}",
                "edges": pattern_graph.number_of_edges(),
                "FREQ": len(pattern.instances),
                "traces": len(traces),
                "REP": round(100 * len(traces) / len(graphs), 2),
                "subdue_value": pattern.value,
            })
        return rows, trace_sets

    def export_subdue_patterns(self, patterns, graphs, output_dir=PATTERN_OUTPUT_DIR):
        """Save pattern statistics (FREQ/REP), the trace-pattern matrix, and a
        PNG per pattern (activity/role labels, directed edges, support in the
        title) - into ``output_dir``."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        rows, trace_sets = self.pattern_statistics(patterns, graphs)

        matrix = {
            row["pattern"]: {index: int(index in traces) for index in range(len(graphs))}
            for row, traces in zip(rows, trace_sets)
        }
        for row, pattern in zip(rows, patterns):
            pattern_graph = self.pattern_to_networkx(pattern.definition)
            title = (f"{row['pattern']}: FREQ={row['FREQ']} instances, "
                     f"REP={row['REP']}% of traces, value={pattern.value:.3f}")
            self.draw_graph(pattern_graph, title, output_dir / f"{row['pattern']}.png")

        pd.DataFrame(rows).to_csv(output_dir / "patterns.csv", index=False)
        pd.DataFrame(matrix).fillna(0).astype(int).to_csv(
            output_dir / "trace_pattern_matrix.csv", index_label="trace"
        )
        return rows

    def run(self, params):
        if not self.graphs_path.exists():
            raise FileNotFoundError(
                f"Run step 1 (instance graph generation) first; missing {self.graphs_path}"
            )

        with open(self.graphs_path, "rb") as file:
            graphs = pickle.load(file)

        patterns = self.run_subdue(graphs, params)
        rows = self.export_subdue_patterns(patterns, graphs, PATTERN_OUTPUT_DIR)
        with open(self.patterns_pkl_path, "wb") as file:
            pickle.dump(patterns, file)
        print(f"Mined {len(rows)} patterns in {PATTERN_OUTPUT_DIR}")


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
                PATTERN_EVALUATION_DIR / f"instance_graph_{index}.png")

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


class Pipeline:
    """Terminal menu that lets the user pick which step to (re)run."""

    ALL_STEPS_KEY = "A"

    def __init__(self):
        self.steps = [InstanceGraphStep(), PatternMiningStep(), EvaluationStep()]

    def print_menu(self):
        print("\n" + "=" * 60)
        print("BPI 2017 organizational pattern mining pipeline")
        print("=" * 60)
        for step in self.steps:
            status = "done" if step.output_exists() else "not run yet"
            print(f"  {step.key}. {step.title}  [{status}]")
        print(f"  {self.ALL_STEPS_KEY}. Run all steps, in order (1, 2, then 3)")
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

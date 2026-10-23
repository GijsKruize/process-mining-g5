"""Step 2: instance graph generation.

Discovers a Petri net from the relabelled log of step 1 with the Inductive
Miner, runs BIG (``big_engine.py``) on every trace to build one instance graph
per trace, writes BIG's textual ``.g`` output and converts it into a list of
``networkx.DiGraph`` objects with globally unique node ids for step 3.

Design decisions (and the reasons for them)
-------------------------------------------
1. **The Petri net is discovered on the labels made in step 1**
   (``<activity>_<attribute group>``), not on the bare activity. The
   assignment asks for exactly this ("once you preprocessed the event log ...
   use the Inductive Miner algorithm to generate the Petri net to give to
   BIG"), and the paper defines the causal relation on activity-resource
   pairs (Definition 5). It is what lets the organisational attribute shape
   the *structure* of the instance graphs instead of only their node labels.
   It is affordable because step 1 now reduces the number of distinct
   resources (roles or frequency grouping), which keeps the number of labels
   in the hundreds instead of the thousands.
   ``--model-activity-attribute original_activity`` restores the previous
   behaviour (model on the bare activity) as a fallback.

2. **The Inductive Miner runs with a noise threshold (default 0.2).**
   This is the "version with log filter (to preserve 80% of behaviour)" the
   teacher refers to and the infrequent Inductive Miner the paper uses
   (section 5.1.1): infrequent directly-follows relations are ignored while
   cutting, so rare behaviour does not force the model into flower-like
   constructs. Without it, the model fits every trace but declares most
   events concurrent, and the instance graphs lose their order.
   The earlier variant filter (keep the most frequent trace variants up to a
   coverage) is still available but off by default: in the BPI 2017 log
   1,770 of the 2,038 activity-level variants occur exactly once, so beyond
   about 43% of the traces "the most frequent variants" are simply the
   one-off variants that come first in the file.

3. **BIG runs on all traces**, also on those the noise filter left out of
   the model. That is the point of the method: traces that do not fit are
   aligned and their graphs are repaired (Algorithm 1 in the paper). Dropping
   them would shrink the trace-pattern matrix and overstate support.

4. **Each distinct label sequence is aligned once.** The graph structure
   depends only on the sequence of labels, so traces with the same sequence
   share the result. Alignments can also run in several processes
   (``--workers``); every process loads the same exported ``petri_net.pnml``,
   and ``determinism.py`` guarantees that serial and parallel runs give the
   same graphs.

5. **A Petri net mined elsewhere can be loaded** with ``--petri-net`` (the
   teacher's first suggestion: mine it in ProM from ``relabeled_log.xes`` and
   export it as PNML).

6. **Alignments use Dijkstra search by default** (``--alignment-variant``).
   Both available searches return an optimal alignment; on the loop-heavy
   nets found for this log Dijkstra was about 16 times faster than pm4py's
   default A* (see ``big_engine.ALIGNMENT_VARIANTS``). Together with points 1
   and 4 this is what brings step 2 from hours to minutes.
"""
import argparse
import copy
import csv
import json
import pickle
import shutil
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import networkx as nx

import determinism
import big_engine
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.algo.discovery.inductive.variants.im_clean.algorithm import Parameters as InductiveParameters
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import EventLog, Trace
from pm4py.objects.petri_net.exporter import exporter as pnml_exporter
from pm4py.objects.petri_net.importer import importer as pnml_importer

ACTIVITY_KEY = "concept:name"

# Above this many distinct labels the Inductive Miner and the alignments get
# slow (minutes become hours). Step 1's grouping options exist to stay below.
MANY_LABELS_WARNING = 400

DEFAULT_NOISE_THRESHOLD = 0.2


def load_petri_net(path):
    """Load a PNML file in a repeatable way.

    The hash counter is reset first so that the net's places and transitions
    get the same hash values in every process that loads the file (the main
    process and each alignment worker). See ``determinism.py``.
    """
    determinism.reset_counter(determinism.NET_BASE)
    return pnml_importer.apply(str(path))


# --------------------------------------------------------------------------
# Alignment workers. The same two functions serve the serial and the parallel
# path, so both produce the same alignments by construction.
# --------------------------------------------------------------------------

_WORKER = {}


def _init_alignment_worker(pnml_path, max_align_seconds, alignment_variant):
    net, initial_marking, final_marking = load_petri_net(pnml_path)
    _WORKER["net"] = net
    _WORKER["initial_marking"] = initial_marking
    _WORKER["final_marking"] = final_marking
    _WORKER["max_align_seconds"] = max_align_seconds
    _WORKER["alignment_variant"] = alignment_variant


def _align_sequence(labels):
    return big_engine.align_labels(
        labels,
        _WORKER["net"],
        _WORKER["initial_marking"],
        _WORKER["final_marking"],
        max_seconds=_WORKER["max_align_seconds"],
        variant=_WORKER["alignment_variant"],
    )


class InstanceGraphBuilder:
    """Builds the instance graphs of a relabelled log."""

    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pnml_path = self.output_dir / "petri_net.pnml"

    # ----------------------------------------------------------------------
    # Petri net
    # ----------------------------------------------------------------------

    def discover_petri_net(self, log, noise_threshold=DEFAULT_NOISE_THRESHOLD):
        """Inductive Miner with noise filtering; writes ``petri_net.pnml``.

        ``IM_CLEAN`` is pm4py 2.2.16's default Inductive Miner. With
        ``noise_threshold=0`` it is the basic miner from the lecture (perfect
        fitness); with a positive threshold it filters infrequent
        directly-follows relations before each cut (IMf).

        The net is not returned: callers reload it from the exported file
        with ``load_petri_net`` so that every consumer sees the same objects
        in the same order.
        """
        parameters = {InductiveParameters.NOISE_THRESHOLD: noise_threshold}
        net, initial_marking, final_marking = inductive_miner.apply(
            log,
            variant=inductive_miner.Variants.IM_CLEAN,
            parameters=parameters,
        )
        determinism.canonical_transition_names(net)
        pnml_exporter.apply(net, initial_marking, str(self.pnml_path), final_marking=final_marking)
        return self.pnml_path

    def use_external_petri_net(self, path):
        """Copy a PNML file mined elsewhere (e.g. in ProM) into the output folder."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Petri net file '{path}' not found")
        if path.resolve() != self.pnml_path.resolve():
            shutil.copyfile(path, self.pnml_path)
        return self.pnml_path

    # ----------------------------------------------------------------------
    # Log helpers
    # ----------------------------------------------------------------------

    @staticmethod
    def clone_log_metadata(log):
        return {
            "attributes": copy.copy(log.attributes),
            "extensions": copy.copy(log.extensions),
            "omni_present": copy.copy(log.omni_present),
            "classifiers": copy.copy(log.classifiers),
            "properties": copy.copy(log.properties),
        }

    @staticmethod
    def label_sequence(trace, attribute=ACTIVITY_KEY):
        """The trace as a tuple of labels taken from ``attribute``."""
        return tuple(
            str(event.get(attribute, event.get(ACTIVITY_KEY, "UNKNOWN")))
            for event in trace
        )

    @classmethod
    def log_with_activity_from(cls, log, attribute):
        """Copy of ``log`` whose activity is the value of ``attribute``.

        Only needed when the model is discovered on something other than the
        step 1 label (``--model-activity-attribute original_activity``).
        """
        if attribute == ACTIVITY_KEY:
            return log
        relabelled = EventLog(**cls.clone_log_metadata(log))
        for trace in log:
            new_trace = Trace(attributes=copy.copy(trace.attributes))
            for event in trace:
                new_event = copy.copy(event)
                new_event[ACTIVITY_KEY] = event.get(attribute, event.get(ACTIVITY_KEY, "UNKNOWN"))
                new_trace.append(new_event)
            relabelled.append(new_trace)
        return relabelled

    @classmethod
    def filter_by_variant_coverage(cls, log, coverage=1.0, variant_attribute=ACTIVITY_KEY):
        """Optionally keep only the most frequent trace variants for *discovery*.

        Off by default (``coverage=1.0``); the noise threshold of the
        Inductive Miner is the default filter (see module docstring, point 2).
        The filtered log is used to discover the Petri net only. BIG still
        runs on every trace.

        Variants with the same frequency are kept in order of first
        appearance, so with many one-off variants the selection is partly
        arbitrary. The statistics returned here make that visible
        (``kept_single_trace_variants``).
        """
        variant_counts = Counter(cls.label_sequence(trace, variant_attribute) for trace in log)
        total_traces = len(log)
        stats = {
            "enabled": False,
            "requested_coverage": coverage,
            "coverage": 1.0,
            "kept_traces": total_traces,
            "total_traces": total_traces,
            "kept_variants": len(variant_counts),
            "total_variants": len(variant_counts),
            "single_trace_variants": sum(1 for count in variant_counts.values() if count == 1),
            "variant_attribute": variant_attribute,
        }
        if coverage is None or coverage >= 1.0:
            return log, stats
        if coverage <= 0:
            raise ValueError("--variant-coverage must be greater than 0")

        target_traces = total_traces * coverage
        kept_variants = set()
        kept_trace_count = 0
        kept_singletons = 0
        for variant, count in variant_counts.most_common():
            kept_variants.add(variant)
            kept_trace_count += count
            kept_singletons += count == 1
            if kept_trace_count >= target_traces:
                break

        filtered_log = EventLog(**cls.clone_log_metadata(log))
        for trace in log:
            if cls.label_sequence(trace, variant_attribute) in kept_variants:
                filtered_log.append(trace)

        stats.update({
            "enabled": True,
            "coverage": len(filtered_log) / total_traces if total_traces else 0.0,
            "kept_traces": len(filtered_log),
            "kept_variants": len(kept_variants),
            "kept_single_trace_variants": kept_singletons,
        })
        return filtered_log, stats

    # ----------------------------------------------------------------------
    # BIG
    # ----------------------------------------------------------------------

    def align_sequences(self, sequences, workers=1, max_align_seconds=None,
                        alignment_variant=big_engine.DEFAULT_ALIGNMENT_VARIANT):
        """Align each distinct label sequence once. Returns ``{sequence: alignment}``.

        An alignment is ``None`` if it hit ``max_align_seconds``.
        """
        total = len(sequences)
        alignments = {}
        started = time.time()

        def report(done):
            if done % 100 == 0 or done == total:
                elapsed = time.time() - started
                remaining = elapsed / done * (total - done)
                print(f"  aligned {done}/{total} distinct sequences "
                      f"({elapsed:.0f}s elapsed, about {remaining:.0f}s left)", flush=True)

        if workers and workers > 1:
            # Each worker loads the exported PNML itself; Petri net objects are
            # not sent between processes. ``map`` returns results in input
            # order, so the outcome does not depend on scheduling.
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_alignment_worker,
                initargs=(str(self.pnml_path), max_align_seconds, alignment_variant),
            ) as pool:
                results = pool.map(_align_sequence, sequences, chunksize=8)
                for done, (sequence, alignment) in enumerate(zip(sequences, results), start=1):
                    alignments[sequence] = alignment
                    report(done)
        else:
            _init_alignment_worker(str(self.pnml_path), max_align_seconds, alignment_variant)
            for done, sequence in enumerate(sequences, start=1):
                alignments[sequence] = _align_sequence(sequence)
                report(done)
        return alignments

    @staticmethod
    def clean_label(label):
        """Labels must not contain whitespace in the ``.g`` format (as in BIG)."""
        return "".join(str(label).split())

    def run_big(self, log, causal_relations, model_activity_attribute=ACTIVITY_KEY,
                workers=1, max_align_seconds=None, strict_path_check=False,
                alignment_variant=big_engine.DEFAULT_ALIGNMENT_VARIANT):
        """Run BIG on every trace; write ``instance_graphs.g`` and the index file.

        Returns ``(g_path, index_rows, stats)``. ``index_rows`` has one row per
        trace of the log, including traces for which no graph could be built,
        so the link between graphs and cases is never implicit.
        """
        model_sequences = [self.label_sequence(trace, model_activity_attribute) for trace in log]
        distinct_sequences = list(dict.fromkeys(model_sequences))
        print(f"  {len(log)} traces, {len(distinct_sequences)} distinct label sequences to align")

        alignments = self.align_sequences(distinct_sequences, workers, max_align_seconds,
                                          alignment_variant)

        # Graph structure per distinct sequence. Nodes are (event position,
        # model label); the labels are replaced per trace below.
        structures = {}
        for sequence in distinct_sequences:
            alignment = alignments[sequence]
            if alignment is None:
                structures[sequence] = {"status": "timeout"}
                continue
            insertions, deletions = big_engine.count_irregular_moves(alignment)
            try:
                nodes, edges = big_engine.instance_graph_from_alignment(
                    alignment, causal_relations, strict_path_check=strict_path_check)
            except Exception as error:  # keep going; the trace is reported in the index
                structures[sequence] = {"status": f"error: {type(error).__name__}: {error}",
                                        "insertions": insertions, "deletions": deletions}
                continue
            structures[sequence] = {"status": "ok", "nodes": nodes, "edges": edges,
                                    "insertions": insertions, "deletions": deletions}

        g_path = self.output_dir / "instance_graphs.g"
        index_rows = []
        graph_index = 0
        with open(g_path, "w", encoding="utf-8") as g_file:
            for trace_index, (trace, sequence) in enumerate(zip(log, model_sequences)):
                structure = structures[sequence]
                row = {
                    "graph_index": "",
                    "trace_index": trace_index,
                    "case_id": trace.attributes.get(ACTIVITY_KEY, str(trace_index)),
                    "events": len(trace),
                    "insertions": structure.get("insertions", ""),
                    "deletions": structure.get("deletions", ""),
                    "status": structure["status"],
                }
                index_rows.append(row)
                if structure["status"] != "ok":
                    continue

                # Node id = 1-based position of the event in the trace, so the
                # label written to the graph is that event's step 1 label even
                # when the model was discovered on another attribute.
                output_labels = [self.clean_label(event.get(ACTIVITY_KEY, "UNKNOWN")) for event in trace]
                g_file.write("XP\n")
                for node_id, _ in structure["nodes"]:
                    g_file.write(f"v {node_id} {output_labels[node_id - 1]}\n")
                for (source_id, _), (target_id, _) in structure["edges"]:
                    g_file.write(f"e {source_id} {target_id} "
                                 f"{output_labels[source_id - 1]}__{output_labels[target_id - 1]}\n")
                g_file.write("\n")
                row["graph_index"] = graph_index
                graph_index += 1

        index_path = self.output_dir / "instance_graph_index.csv"
        with open(index_path, "w", newline="", encoding="utf-8") as index_file:
            writer = csv.DictWriter(index_file, fieldnames=list(index_rows[0].keys()) if index_rows else
                                    ["graph_index", "trace_index", "case_id", "events",
                                     "insertions", "deletions", "status"])
            writer.writeheader()
            writer.writerows(index_rows)

        ok_rows = [row for row in index_rows if row["status"] == "ok"]
        stats = {
            "traces": len(log),
            "distinct_label_sequences": len(distinct_sequences),
            "graphs_built": len(ok_rows),
            "traces_fitting_the_model": sum(
                1 for row in ok_rows if row["insertions"] == 0 and row["deletions"] == 0),
            "traces_repaired": sum(
                1 for row in ok_rows if row["insertions"] or row["deletions"]),
            "inserted_events_total": sum(row["insertions"] for row in ok_rows),
            "deleted_events_total": sum(row["deletions"] for row in ok_rows),
            "alignment_timeouts": sum(1 for row in index_rows if row["status"] == "timeout"),
            "repair_errors": sum(1 for row in index_rows if row["status"].startswith("error")),
        }
        return g_path, index_rows, stats

    @staticmethod
    def parse_g_file(path, index_rows=None):
        """Parse a BIG ``.g`` file into a list of DiGraphs (one per ``XP`` block).

        BIG's node ids restart at 1 in every graph, so they are replaced by
        ids that are unique across the whole collection (assignment step 2).
        The original id is kept as the node attribute ``position`` and the
        case id, when known, as the graph attribute ``case_id``.
        """
        case_by_graph = {}
        for row in index_rows or []:
            if row["graph_index"] != "":
                case_by_graph[int(row["graph_index"])] = (row["case_id"], row["trace_index"])

        graphs = []
        graph = None
        local_to_global = {}
        next_id = 0
        with open(path, encoding="utf-8") as g_file:
            for raw_line in g_file:
                line = raw_line.strip()
                if not line:
                    continue
                tag, _, rest = line.partition(" ")
                if tag == "XP":
                    graph = nx.DiGraph()
                    case_id, trace_index = case_by_graph.get(len(graphs), (str(len(graphs)), len(graphs)))
                    graph.graph["case_id"] = case_id
                    graph.graph["trace_index"] = trace_index
                    graphs.append(graph)
                    local_to_global = {}
                elif tag == "v":
                    local_id, _, label = rest.partition(" ")
                    local_to_global[local_id] = next_id
                    graph.add_node(next_id, label=label, position=int(local_id))
                    next_id += 1
                elif tag == "e":
                    source, target, label = rest.split(" ", 2)
                    graph.add_edge(local_to_global[source], local_to_global[target], label=label)
        return graphs

    # ----------------------------------------------------------------------
    # Whole step
    # ----------------------------------------------------------------------

    def run(self, log_path, noise_threshold=DEFAULT_NOISE_THRESHOLD, petri_net_path=None,
            variant_coverage=1.0, variant_attribute=None,
            model_activity_attribute=ACTIVITY_KEY, workers=1, max_align_seconds=None,
            strict_path_check=False, alignment_variant=big_engine.DEFAULT_ALIGNMENT_VARIANT):
        started = time.time()
        log = xes_importer.apply(str(log_path))
        variant_attribute = variant_attribute or model_activity_attribute

        output_label_count = len({event[ACTIVITY_KEY] for trace in log for event in trace})
        model_labels = {label for trace in log
                        for label in self.label_sequence(trace, model_activity_attribute)}
        print(f"Labels in the log: {output_label_count}; labels used for the process model "
              f"('{model_activity_attribute}'): {len(model_labels)}.")
        if len(model_labels) > MANY_LABELS_WARNING:
            print(f"Warning: more than {MANY_LABELS_WARNING} model labels. Discovery and alignment "
                  "will be slow; consider a stronger grouping in step 1 (--grouping roles, or "
                  "--grouping frequency with a lower --grouping-coverage).")

        # ---- Petri net -----------------------------------------------------
        discovery_started = time.time()
        if petri_net_path:
            self.use_external_petri_net(petri_net_path)
            filter_stats = {"enabled": False, "note": "external Petri net, no discovery"}
            model_source = f"external file '{petri_net_path}'"
        else:
            discovery_log, filter_stats = self.filter_by_variant_coverage(
                log, variant_coverage, variant_attribute=variant_attribute)
            if filter_stats["enabled"]:
                print("Variant filter for discovery: kept "
                      f"{filter_stats['kept_traces']}/{filter_stats['total_traces']} traces in "
                      f"{filter_stats['kept_variants']}/{filter_stats['total_variants']} variants "
                      f"({filter_stats['kept_single_trace_variants']} of the kept variants occur once).")
            discovery_log = self.log_with_activity_from(discovery_log, model_activity_attribute)
            print(f"Discovering the Petri net (Inductive Miner, noise threshold {noise_threshold}) ...",
                  flush=True)
            self.discover_petri_net(discovery_log, noise_threshold=noise_threshold)
            model_source = f"Inductive Miner (IM_CLEAN), noise threshold {noise_threshold}"
        net, _, _ = load_petri_net(self.pnml_path)
        discovery_seconds = time.time() - discovery_started

        net_labels = {transition.label for transition in net.transitions if transition.label is not None}
        missing_labels = sorted(model_labels - net_labels)
        print(f"Petri net: {len(net.transitions)} transitions ({len(net_labels)} labelled), "
              f"{len(net.places)} places, saved to '{self.pnml_path}' "
              f"({discovery_seconds:.0f}s).")
        if missing_labels:
            # Expected with a noise threshold: rare labels are filtered out of
            # the model. Their events become insertions and are repaired.
            print(f"  {len(missing_labels)} log labels have no transition in the net; their events "
                  "are treated as insertions and repaired by BIG.")
        if not net_labels & model_labels:
            raise ValueError("The Petri net shares no label with the log. If you passed --petri-net, "
                             "it must be mined from this run's relabeled_log.xes.")

        # ---- BIG -----------------------------------------------------------
        causal_relations = big_engine.find_causal_relationships(net)
        print(f"Running BIG ({len(causal_relations)} causal relations, {workers} worker(s), "
              f"'{alignment_variant}' alignments) ...", flush=True)
        big_started = time.time()
        g_path, index_rows, big_stats = self.run_big(
            log,
            causal_relations,
            model_activity_attribute=model_activity_attribute,
            workers=workers,
            max_align_seconds=max_align_seconds,
            strict_path_check=strict_path_check,
            alignment_variant=alignment_variant,
        )
        big_seconds = time.time() - big_started
        print(f"BIG instance graphs written to '{g_path}' ({big_seconds:.0f}s): "
              f"{big_stats['graphs_built']}/{big_stats['traces']} graphs, "
              f"{big_stats['traces_fitting_the_model']} traces fit the model, "
              f"{big_stats['traces_repaired']} repaired "
              f"({big_stats['inserted_events_total']} insertions, "
              f"{big_stats['deleted_events_total']} deletions).")
        if big_stats["alignment_timeouts"] or big_stats["repair_errors"]:
            print(f"  Warning: {big_stats['alignment_timeouts']} alignment timeouts and "
                  f"{big_stats['repair_errors']} repair errors; see instance_graph_index.csv.")

        # ---- networkx ------------------------------------------------------
        graphs = self.parse_g_file(g_path, index_rows)
        node_count = sum(graph.number_of_nodes() for graph in graphs)
        edge_count = sum(graph.number_of_edges() for graph in graphs)
        print(f"Parsed {len(graphs)} instance graphs ({node_count} nodes, {edge_count} edges)")

        pkl_path = self.output_dir / "instance_graphs.pkl"
        with open(pkl_path, "wb") as pkl_file:
            pickle.dump(graphs, pkl_file)
        print(f"Saved parsed instance graphs to '{pkl_path}'")

        stats = {
            "model": {
                "source": model_source,
                "model_activity_attribute": model_activity_attribute,
                "noise_threshold": None if petri_net_path else noise_threshold,
                "transitions": len(net.transitions),
                "labelled_transitions": len(net_labels),
                "places": len(net.places),
                "causal_relations": len(causal_relations),
                "log_labels": len(model_labels),
                "log_labels_without_transition": len(missing_labels),
            },
            "variant_filter": filter_stats,
            "big": big_stats,
            "graphs": {"count": len(graphs), "nodes": node_count, "edges": edge_count},
            "settings": {"workers": workers, "max_align_seconds": max_align_seconds,
                         "strict_path_check": strict_path_check,
                         "alignment_variant": alignment_variant},
            "seconds": {"discovery": round(discovery_seconds, 1), "big": round(big_seconds, 1),
                        "total": round(time.time() - started, 1)},
        }
        with open(self.output_dir / "instance_graph_stats.json", "w", encoding="utf-8") as stats_file:
            json.dump(stats, stats_file, indent=2)
        return graphs


def add_instance_graph_arguments(parser):
    """Step 2 options, shared by this module's CLI and ``main.py``."""
    parser.add_argument("--noise-threshold", type=float, default=DEFAULT_NOISE_THRESHOLD,
                        help="Inductive Miner noise threshold; 0 disables filtering (default 0.2, "
                             "i.e. keep about 80%% of the behaviour)")
    parser.add_argument("--petri-net", default=None,
                        help="Use this PNML file (e.g. mined in ProM from relabeled_log.xes) "
                             "instead of discovering a net")
    parser.add_argument("--variant-coverage", type=float, default=1.0,
                        help="Discover the net on the most frequent trace variants covering this "
                             "fraction of traces; 1.0 (default) uses all traces")
    parser.add_argument("--variant-attribute", default=None,
                        help="Event attribute that defines a trace variant for --variant-coverage "
                             "(default: the model activity attribute)")
    parser.add_argument("--model-activity-attribute", default=ACTIVITY_KEY,
                        help="Event attribute used as activity for discovery and alignment. "
                             "Default 'concept:name' = the step 1 label; 'original_activity' "
                             "ignores the organisational attribute in the model")
    parser.add_argument("--workers", type=int, default=1,
                        help="Processes used for the alignments (results are identical for any value)")
    parser.add_argument("--alignment-variant", choices=sorted(big_engine.ALIGNMENT_VARIANTS),
                        default=big_engine.DEFAULT_ALIGNMENT_VARIANT,
                        help="Search used for the optimal alignments: 'dijkstra' (default, fast on "
                             "loop-heavy nets) or 'astar' (pm4py's default)")
    parser.add_argument("--max-align-seconds", type=float, default=None,
                        help="Give up on a trace after this many seconds. Off by default, because "
                             "a time limit makes the result depend on the machine")
    parser.add_argument("--strict-path-check", action="store_true",
                        help="Use a real reachability test in BIG's insertion repair instead of "
                             "the provided library's behaviour (see big_engine.is_path)")


def instance_graph_kwargs_from_args(args):
    return {
        "noise_threshold": args.noise_threshold,
        "petri_net_path": args.petri_net,
        "variant_coverage": args.variant_coverage,
        "variant_attribute": args.variant_attribute,
        "model_activity_attribute": args.model_activity_attribute,
        "workers": args.workers,
        "max_align_seconds": args.max_align_seconds,
        "strict_path_check": args.strict_path_check,
        "alignment_variant": args.alignment_variant,
    }


def main():
    determinism.ensure_fixed_hash_seed()
    parser = argparse.ArgumentParser(description="Step 2: generate instance graphs with BIG.")
    parser.add_argument("--log-path", default="output/relabeled_log.xes",
                        help="Relabelled log produced by step 1")
    parser.add_argument("--output-dir", default="output")
    add_instance_graph_arguments(parser)
    args = parser.parse_args()
    InstanceGraphBuilder(args.output_dir).run(args.log_path, **instance_graph_kwargs_from_args(args))


if __name__ == "__main__":
    main()

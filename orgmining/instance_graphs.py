"""Step 2 - Instance graph generation.

Assignment: discover a Petri net with the Inductive Miner on the relabelled
log of step 1, give log and net to the provided BIG library, and convert BIG's
textual output into networkx graphs in which every node has a unique id.

An *instance graph* (Diamantini et al. 2016, section 4.2) shows one trace as a
graph: nodes are its events, edges are the causal order derived from the
Petri net. Events that the model allows in any order end up on parallel
branches instead of in an arbitrary sequence. BIG also *repairs* the graphs of
traces that do not fit the model (inserted/deleted events, section 5.1.2).

Classes, in pipeline order:

    PetriNetDiscoverer      Inductive Miner -> Petri net (+ .pnml file)
    BigRunner               runs the provided BIG.py -> .g text file
    GFileConverter          .g text file -> list of networkx.DiGraph
    InstanceGraphBuilder    runs the three above and writes all outputs

Format of a .g file (one block per trace, in the order of the log)::

    XP
    v 1 start_Role_3                      v <local node id> <label>
    v 2 A-Create-Application_Role_3
    e 1 2 start_Role_3__A-Create-Application_Role_3   e <from> <to> <from label>__<to label>
    <empty line>
"""
import contextlib
import json
import math
import os
import pickle
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import networkx as nx
import pandas as pd
import pm4py
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import EventLog
from pm4py.objects.petri_net.exporter import exporter as pnml_exporter
from pm4py.objects.petri_net.importer import importer as pnml_importer

from . import config

# The paper uses the *infrequent* Inductive Miner (iIM) with ProM's default
# settings; 0.2 is ProM's default noise threshold. 0.0 gives the plain
# Inductive Miner, which fits every trace but tends to overgeneralise (many
# activities in parallel), which in turn makes the instance graphs imprecise.
DEFAULT_NOISE_THRESHOLD = 0.2

# BIG handles about 15 traces per minute per CPU core on the role-labelled
# BPI 2017 log (3 to 4 hours in total on one core), so it runs in parallel.
DEFAULT_WORKERS = max(1, (os.cpu_count() or 2) - 1)
CHUNKS_PER_WORKER = 4   # several small chunks per worker spread the work evenly

G_FILE_NAME = "instance_graphs.g"
GRAPHS_FILE_NAME = "instance_graphs.pkl"
PETRI_NET_FILE_NAME = "petri_net.pnml"


@contextlib.contextmanager
def working_directory(path):
    """Temporarily change the current directory (BIG writes to './graph.g')."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


# ---------------------------------------------------------------------------
# 1. Petri net
# ---------------------------------------------------------------------------

class PetriNetDiscoverer:
    """Discovers the process model that BIG uses to derive causal relations."""

    def __init__(self, noise_threshold=DEFAULT_NOISE_THRESHOLD):
        if not 0 <= noise_threshold <= 1:
            raise ValueError("The noise threshold must be between 0 and 1.")
        self.noise_threshold = noise_threshold

    def discover(self, log):
        """Return (net, initial_marking, final_marking) for a pm4py EventLog."""
        return pm4py.discover_petri_net_inductive(log, noise_threshold=self.noise_threshold)

    @staticmethod
    def save(net, initial_marking, final_marking, path):
        pnml_exporter.apply(net, initial_marking, str(path), final_marking=final_marking)
        return path

    @staticmethod
    def describe(net):
        visible = [t for t in net.transitions if t.label is not None]
        return {"places": len(net.places), "transitions": len(net.transitions),
                "visible_transitions": len(visible), "arcs": len(net.arcs)}


# ---------------------------------------------------------------------------
# 2. BIG
# ---------------------------------------------------------------------------

BIG_OUTPUT_NAME = "graph.g"   # fixed by BIG.py


def import_big():
    """Import the course's ``BIG.py`` from the project root."""
    if str(config.PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(config.PROJECT_ROOT))
    try:
        import BIG  # noqa: N811 - module name given by the course
    except ImportError as error:
        raise ImportError("BIG.py not found in the project root. Download it from "
                          "Canvas and place it next to main.py (see README.md).") from error
    return BIG


def run_big_on_chunk(chunk_xes_path, pnml_path, work_dir):
    """Run the unchanged ``BIG.big`` on one chunk of the log, inside ``work_dir``.

    Defined at module level so that it can run in a separate process. BIG
    appends to ``./graph.g`` and prints one line per trace; both end up in
    ``work_dir``. Returns the path of the chunk's ``graph.g``.
    """
    big = import_big()
    # Resolve before changing directory, relative paths would point elsewhere after.
    work_dir = Path(work_dir).resolve()
    chunk_xes_path = Path(chunk_xes_path).resolve()
    net, initial_marking, final_marking = pnml_importer.apply(str(Path(pnml_path).resolve()))
    # buffering=1: write line by line, so the progress can be followed live.
    with open(work_dir / "big.log", "w", encoding="utf-8", buffering=1) as big_log, \
            working_directory(work_dir), contextlib.redirect_stdout(big_log):
        big.big(net=net, initial_marking=initial_marking,
                final_marking=final_marking, log=str(chunk_xes_path))
    return work_dir / BIG_OUTPUT_NAME


class BigRunner:
    """Runs the provided BIG library (``BIG.py`` in the project root) unchanged, in parallel.

    BIG treats every trace independently, so the log is cut into consecutive
    chunks, BIG runs on each chunk in its own process and folder, and the
    chunks' outputs are joined in the original order. The result is the same
    file a single BIG run on the whole log would write, only faster.
    """

    def __init__(self, output_dir, workers=DEFAULT_WORKERS):
        self.output_dir = Path(output_dir)
        self.workers = max(1, int(workers))

    def split_log(self, log, chunks_dir):
        """Write the log as consecutive chunk files; returns their paths in order."""
        n_chunks = min(len(log), self.workers * CHUNKS_PER_WORKER) if self.workers > 1 else 1
        chunk_size = math.ceil(len(log) / n_chunks)
        paths = []
        for index, start in enumerate(range(0, len(log), chunk_size)):
            chunk = EventLog(log[start:start + chunk_size], attributes=log.attributes,
                             extensions=log.extensions, classifiers=log.classifiers,
                             omni_present=log.omni_present)
            chunk_dir = chunks_dir / f"chunk_{index:03d}"
            chunk_dir.mkdir(parents=True, exist_ok=True)
            path = chunk_dir / "log.xes"
            xes_exporter.apply(chunk, str(path))
            paths.append(path)
        return paths

    def run(self, log, pnml_path, g_path):
        """Build the instance graphs of ``log`` (pm4py EventLog) and write them to ``g_path``."""
        chunks_dir = self.output_dir / "big_chunks"
        if chunks_dir.exists():
            shutil.rmtree(chunks_dir)
        chunk_paths = self.split_log(log, chunks_dir)
        print(f"  BIG runs on {len(chunk_paths)} chunks with {self.workers} worker(s); "
              f"progress per chunk in {config.display_path(chunks_dir)}/chunk_*/big.log",
              flush=True)

        outputs = [None] * len(chunk_paths)
        with ProcessPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(run_big_on_chunk, path, pnml_path, path.parent): index
                       for index, path in enumerate(chunk_paths)}
            for done, future in enumerate(as_completed(futures), start=1):
                outputs[futures[future]] = future.result()
                print(f"    chunk {done}/{len(chunk_paths)} done", flush=True)

        # Join in chunk order, so graph i still belongs to trace i of the log.
        g_path = Path(g_path)
        with open(g_path, "w", encoding="utf-8") as joined:
            for chunk_output in outputs:
                joined.write(chunk_output.read_text(encoding="utf-8"))
        shutil.rmtree(chunks_dir)
        return g_path


# ---------------------------------------------------------------------------
# 3. .g text -> networkx
# ---------------------------------------------------------------------------

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
                # A node with more than one successor opens parallel branches.
                "has_parallelism": any(degree > 1 for _, degree in graph.out_degree()),
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


# ---------------------------------------------------------------------------
# 4. Put it together
# ---------------------------------------------------------------------------

@dataclass
class InstanceGraphResult:
    """What step 2 hands over to step 3."""
    output_dir: Path
    graphs_path: Path
    n_graphs: int


class InstanceGraphBuilder:
    """Runs step 2 on the output folder of step 1.

    Outputs in ``<output_root>/<name of the step 1 folder>[_first<N>]/``:
        petri_net.pnml              the discovered model
        instance_graphs.g           BIG's raw output
        instance_graphs.pkl         list of networkx.DiGraph, input for step 3
        instance_graphs_summary.csv one row per graph (size, parallelism, ...)
        summary.json                settings, timings and headline numbers
    """

    def __init__(self, step1_dir, output_root=config.STEP2_OUTPUT_DIR,
                 noise_threshold=DEFAULT_NOISE_THRESHOLD, workers=DEFAULT_WORKERS,
                 max_traces=None):
        """``max_traces``: only use the first N traces, for a quick trial run."""
        self.step1_dir = Path(step1_dir)
        suffix = f"_first{max_traces}" if max_traces else ""
        self.output_dir = Path(output_root) / f"{self.step1_dir.name}{suffix}"
        self.noise_threshold = noise_threshold
        self.workers = workers
        self.max_traces = max_traces

    def load_log(self, xes_path):
        log = xes_importer.apply(str(xes_path))
        if self.max_traces:
            log = EventLog(log[:self.max_traces], attributes=log.attributes,
                           extensions=log.extensions, classifiers=log.classifiers,
                           omni_present=log.omni_present)
        return log

    def run(self):
        xes_path = self.step1_dir / "relabeled_log.xes"
        if not xes_path.is_file():
            raise FileNotFoundError(f"{config.display_path(xes_path)} not found; run step 1 "
                                    "(python main.py preprocess) first.")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timings = {}

        print(f"Reading {config.display_path(xes_path)} ...")
        log = self.load_log(xes_path)
        # The .g file does not name the traces: graph i belongs to trace i.
        case_ids = [trace.attributes.get("concept:name") for trace in log]

        print(f"Discovering Petri net (Inductive Miner, noise threshold "
              f"{self.noise_threshold}) on {len(log):,} traces ...")
        started = time.time()
        discoverer = PetriNetDiscoverer(self.noise_threshold)
        net, initial_marking, final_marking = discoverer.discover(log)
        pnml_path = discoverer.save(net, initial_marking, final_marking,
                                    self.output_dir / PETRI_NET_FILE_NAME)
        net_size = discoverer.describe(net)
        timings["petri_net_seconds"] = round(time.time() - started, 1)
        print(f"  {net_size['visible_transitions']} visible transitions, {net_size['places']} "
              f"places ({timings['petri_net_seconds']} s)")

        print("Building instance graphs with BIG ...")
        started = time.time()
        g_path = BigRunner(self.output_dir, self.workers).run(
            log, pnml_path, self.output_dir / G_FILE_NAME)
        timings["big_seconds"] = round(time.time() - started, 1)
        print(f"  done ({timings['big_seconds']} s)")

        print("Converting BIG output to networkx graphs ...")
        converter = GFileConverter.from_label_counts(self.step1_dir / "label_counts.csv")
        graphs = converter.convert(g_path, case_ids)
        graphs_path = converter.save(graphs, self.output_dir / GRAPHS_FILE_NAME)
        graph_table = converter.summarise(graphs)
        graph_table.to_csv(self.output_dir / "instance_graphs_summary.csv", index=False)

        summary = {
            "step": "2 - instance graphs",
            "created": datetime.now().isoformat(timespec="seconds"),
            "input_log": config.display_path(xes_path),
            "max_traces": self.max_traces,
            "noise_threshold": self.noise_threshold,
            "workers": self.workers,
            "petri_net": net_size,
            "graphs": len(graphs),
            "nodes": int(graph_table["nodes"].sum()),
            "edges": int(graph_table["edges"].sum()),
            "graphs_with_parallelism_pct": round(100 * graph_table["has_parallelism"].mean(), 1),
            "graphs_not_connected": int((~graph_table["connected"]).sum()),
            **timings,
        }
        (self.output_dir / "summary.json").write_text(json.dumps(summary, indent=2),
                                                      encoding="utf-8")
        print(f"  {summary['graphs']:,} graphs, {summary['nodes']:,} nodes, "
              f"{summary['edges']:,} edges; {summary['graphs_with_parallelism_pct']}% "
              "contain parallel branches")
        print(f"Step 2 outputs written to: {config.display_path(self.output_dir)}")
        return InstanceGraphResult(self.output_dir, graphs_path, len(graphs))

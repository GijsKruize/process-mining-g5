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
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pm4py
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import EventLog
from pm4py.objects.petri_net.exporter import exporter as pnml_exporter
from pm4py.objects.petri_net.importer import importer as pnml_importer

from . import config

# The PM4Py 2.2.16 convenience API selects IM_CLEAN. IMf can be selected
# explicitly for comparison; the variants are not interchangeable.
# Keep the existing IM_CLEAN default so prior outputs remain reproducible.
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

    def __init__(self, noise_threshold=DEFAULT_NOISE_THRESHOLD, miner_variant="im_clean"):
        if not 0 <= noise_threshold <= 1:
            raise ValueError("The noise threshold must be between 0 and 1.")
        if miner_variant not in ("im_clean", "imf"):
            raise ValueError("Miner variant must be im_clean or imf.")
        self.noise_threshold = noise_threshold
        self.miner_variant = miner_variant

    def discover(self, log):
        """Return (net, initial_marking, final_marking) for a pm4py EventLog."""
        if self.miner_variant == "imf":
            from pm4py.algo.discovery.inductive import algorithm as inductive
            variant = inductive.Variants.IMf
            return inductive.apply(log, variant=variant, parameters={
                variant.value.Parameters.NOISE_THRESHOLD: self.noise_threshold})
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
    chunks' outputs are joined in the original order. Optimal alignment ties
    can still give different valid graphs; seed and version alone do not
    guarantee byte-for-byte equality in every case.
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

# Public compatibility import; implementation lives in graph_io.py.
from .graph_io import GFileConverter


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
        instance_graphs_summary.csv one row per graph (size, branching, ...)
        summary.json                settings, timings and headline numbers
    """

    def __init__(self, step1_dir, output_root=config.STEP2_OUTPUT_DIR,
                 noise_threshold=DEFAULT_NOISE_THRESHOLD, workers=DEFAULT_WORKERS,
                 max_traces=None, miner_variant="im_clean"):
        """``max_traces``: only use the first N traces, for a quick trial run."""
        self.step1_dir = Path(step1_dir)
        suffix = f"_first{max_traces}" if max_traces else ""
        if miner_variant != "im_clean":
            suffix += f"_{miner_variant}"
        self.output_dir = Path(output_root) / f"{self.step1_dir.name}{suffix}"
        self.noise_threshold = noise_threshold
        self.workers = workers
        if max_traces is not None and max_traces < 1:
            raise ValueError("max_traces must be positive.")
        self.max_traces = max_traces
        self.miner_variant = miner_variant

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
        discoverer = PetriNetDiscoverer(self.noise_threshold, self.miner_variant)
        net, initial_marking, final_marking = discoverer.discover(log)
        pnml_path = discoverer.save(net, initial_marking, final_marking,
                                    self.output_dir / PETRI_NET_FILE_NAME)
        net_size = discoverer.describe(net)
        log_labels = {e[config.ACTIVITY_KEY] for trace in log for e in trace}
        model_labels = {t.label for t in net.transitions if t.label is not None}
        absent_labels = sorted(log_labels - model_labels)
        if absent_labels:
            print(f"  {len(absent_labels)} log labels absent from the model; "
                  "these events require BIG repair (see summary.json)")
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
        converter.validate_against_log(graphs, log)
        graphs_path = converter.save(graphs, self.output_dir / GRAPHS_FILE_NAME)
        graph_table = converter.summarise(graphs)
        graph_table.to_csv(self.output_dir / "instance_graphs_summary.csv", index=False)

        summary = {
            "step": "2 - instance graphs",
            "created": datetime.now().isoformat(timespec="seconds"),
            "input_log": config.display_path(xes_path),
            "max_traces": self.max_traces,
            "noise_threshold": self.noise_threshold,
            "miner_variant": self.miner_variant,
            "pm4py_version": pm4py.__version__,
            "labels_absent_from_model": absent_labels,
            "workers": self.workers,
            "petri_net": net_size,
            "graphs": len(graphs),
            "nodes": int(graph_table["nodes"].sum()),
            "edges": int(graph_table["edges"].sum()),
            "graphs_with_branching_pct": round(100 * graph_table["has_branching"].mean(), 1),
            "graphs_not_connected": int((~graph_table["connected"]).sum()),
            **timings,
        }
        (self.output_dir / "summary.json").write_text(json.dumps(summary, indent=2),
                                                      encoding="utf-8")
        print(f"  {summary['graphs']:,} graphs, {summary['nodes']:,} nodes, "
              f"{summary['edges']:,} edges; {summary['graphs_with_branching_pct']}% "
              "contain branching nodes")
        print(f"Step 2 outputs written to: {config.display_path(self.output_dir)}")
        return InstanceGraphResult(self.output_dir, graphs_path, len(graphs))

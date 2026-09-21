"""Step 2 of the organizational process mining pipeline: instance graph generation.

Takes the relabelled event log produced by ``preprocess.py`` (step 1),
discovers a Petri net with the Inductive Miner, and feeds both into the
external BIG library to build one instance graph per trace. BIG's textual
output is then parsed into a list of ``networkx.DiGraph`` objects (one per
trace) with globally unique node ids, ready for the SUBDUE subgraph mining
step.

Petri net discovery and the log handed to BIG use the plain
``original_activity`` attribute preserved by step 1 (not the resource-fused
``concept:name``): with thousands of distinct fused labels, Inductive Miner
becomes impractically slow, and it matches how the example
``BPI2017Denied.g`` was built. See ``config_instance_graphs.yaml`` for
details and how to override it.

BIG itself is a course-provided tool, not bundled with this project (see
README.md for how to configure it). Until it is available, the parser can
be exercised directly on any pre-generated ``.g`` file, e.g. the example
``BPI2017Denied.g`` provided with the assignment, via ``--parse-only``.

Run ``python instance_graphs.py --help`` for the command line options.
"""
from __future__ import annotations

import argparse
import pickle
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import networkx as nx
import yaml
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.objects.log.obj import EventLog
from pm4py.objects.petri_net.exporter import exporter as pnml_exporter
from pm4py.objects.petri_net.obj import Marking, PetriNet

from preprocess import ACTIVITY_KEY, EventLogRepository

DEFAULT_CONFIG_PATH = Path("config_instance_graphs.yaml")

# SUBDUE-style example separators: BIG emits one such header before every
# instance graph in its textual output (e.g. 'XP' for a positive example).
GRAPH_HEADER_TAGS = ("XP", "XN")


@dataclass
class InstanceGraphConfig:
    """Adjustable parameters for this pipeline step, loaded from YAML."""

    log_path: Path = field(default_factory=lambda: Path("output/relabeled_log.xes"))
    output_dir: Path = field(default_factory=lambda: Path("output"))
    # Which event attribute to use as the activity for Inductive Miner
    # discovery and for the log handed to BIG. Defaults to the plain,
    # un-fused activity that step 1 preserves under 'original_activity':
    # the resource-fused 'concept:name' from step 1 has thousands of
    # distinct values, which makes Inductive Miner impractically slow and
    # would not align against a Petri net at all (transition labels must
    # match the log's activity values). It also matches how the example
    # BPI2017Denied.g was built ("only event activities are used as
    # labels"). Node objects still carry the original event's full set of
    # attributes, so resource-fused labels remain available downstream.
    activity_key: str = "original_activity"
    discovery_log_filename: str = "discovery_log.xes"
    petri_net_filename: str = "petri_net.pnml"
    graphs_filename: str = "instance_graphs.g"
    parsed_graphs_filename: str = "instance_graphs.pkl"
    # Command used to invoke the external BIG tool. Must contain the
    # {log}, {petri_net}, and {output} placeholders, e.g.:
    #   "java -jar tools/BIG.jar {log} {petri_net} {output}"
    big_command: Optional[str] = None

    @classmethod
    def from_yaml(cls, path: Path) -> "InstanceGraphConfig":
        """Load a config from a YAML file, falling back to defaults for any missing key."""
        with open(path, "r", encoding="utf-8") as config_file:
            raw = yaml.safe_load(config_file) or {}
        defaults = cls()
        return cls(
            log_path=Path(raw.get("log_path", defaults.log_path)),
            output_dir=Path(raw.get("output_dir", defaults.output_dir)),
            activity_key=raw.get("activity_key", defaults.activity_key),
            discovery_log_filename=raw.get(
                "discovery_log_filename", defaults.discovery_log_filename
            ),
            petri_net_filename=raw.get("petri_net_filename", defaults.petri_net_filename),
            graphs_filename=raw.get("graphs_filename", defaults.graphs_filename),
            parsed_graphs_filename=raw.get(
                "parsed_graphs_filename", defaults.parsed_graphs_filename
            ),
            big_command=raw.get("big_command", defaults.big_command),
        )

    @property
    def discovery_log_path(self) -> Path:
        return self.output_dir / self.discovery_log_filename

    @property
    def petri_net_path(self) -> Path:
        return self.output_dir / self.petri_net_filename

    @property
    def graphs_path(self) -> Path:
        return self.output_dir / self.graphs_filename

    @property
    def parsed_graphs_path(self) -> Path:
        return self.output_dir / self.parsed_graphs_filename


class PetriNetDiscoverer:
    """Discovers a Petri net from an event log using the Inductive Miner."""

    @staticmethod
    def discover(log: EventLog) -> Tuple[PetriNet, Marking, Marking]:
        """Run the Inductive Miner on *log*, returning (net, initial_marking, final_marking)."""
        return inductive_miner.apply(log)

    @staticmethod
    def export(
        net: PetriNet, initial_marking: Marking, final_marking: Marking, path: Path
    ) -> None:
        """Export a discovered Petri net to PNML at *path*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        pnml_exporter.apply(net, initial_marking, str(path), final_marking=final_marking)


class BigRunner:
    """Invokes the external BIG tool to build instance graphs from a log + Petri net.

    BIG is provided by the course, not by this project, so its invocation is
    a configurable shell command rather than a hard-coded call. The command
    template is read from the trusted local config file, never from
    untrusted input, so running it via the shell is safe here.
    """

    def __init__(self, command_template: Optional[str]) -> None:
        self.command_template = command_template

    def run(self, log_path: Path, petri_net_path: Path, output_path: Path) -> None:
        """Run BIG, writing its textual instance-graph output to *output_path*."""
        if not self.command_template:
            raise RuntimeError(
                "BIG is not configured. Set 'big_command' in "
                f"'{DEFAULT_CONFIG_PATH}' to the command that runs BIG, using "
                "{log}, {petri_net}, and {output} placeholders. See README.md. "
                "Alternatively, run BIG yourself and pass its .g output to "
                "--parse-only."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = self.command_template.format(
            log=str(log_path), petri_net=str(petri_net_path), output=str(output_path)
        )
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"BIG failed (exit code {result.returncode}).\n"
                f"command: {command}\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )


class InstanceGraphParser:
    """Parses BIG's textual .g output into a list of networkx DiGraphs.

    Each instance graph starts with a header line (e.g. 'XP'), followed by
    'v <local_id> <label>' vertex lines and 'e <src> <dst> <label>' edge
    lines. Vertex ids restart at 1 for every graph in the raw file, so each
    node is assigned a new, globally unique id across the whole collection
    (stored as the networkx node id), while its original per-graph id and
    label are kept as node attributes. Edges are remapped through the same
    id translation, so all relations from the source file are preserved.
    """

    def parse(self, path: Path) -> List[nx.DiGraph]:
        """Parse the .g file at *path* into a list of DiGraphs, one per instance."""
        with open(path, "r", encoding="utf-8") as g_file:
            return self.parse_lines(g_file)

    def parse_lines(self, lines: Iterable[str]) -> List[nx.DiGraph]:
        """Parse an iterable of .g-format lines into a list of DiGraphs."""
        graphs: List[nx.DiGraph] = []
        graph: Optional[nx.DiGraph] = None
        local_to_global: Dict[str, int] = {}
        next_id = 0

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            tag, _, rest = line.partition(" ")
            if tag in GRAPH_HEADER_TAGS:
                graph = nx.DiGraph(index=len(graphs))
                graphs.append(graph)
                local_to_global = {}
            elif tag == "v":
                if graph is None:
                    raise ValueError(f"Vertex line found before any graph header: {line!r}")
                local_id, _, label = rest.partition(" ")
                global_id = next_id
                next_id += 1
                local_to_global[local_id] = global_id
                graph.add_node(global_id, label=label, local_id=int(local_id))
            elif tag == "e":
                if graph is None:
                    raise ValueError(f"Edge line found before any graph header: {line!r}")
                src_local, dst_local, label = rest.split(" ", 2)
                graph.add_edge(
                    local_to_global[src_local], local_to_global[dst_local], label=label
                )
            else:
                raise ValueError(f"Unrecognized line in .g file: {line!r}")

        return graphs

    @staticmethod
    def summarize(graphs: List[nx.DiGraph]) -> dict:
        """Compute basic size statistics for a list of instance graphs."""
        n_nodes = sum(graph.number_of_nodes() for graph in graphs)
        n_edges = sum(graph.number_of_edges() for graph in graphs)
        return {
            "n_graphs": len(graphs),
            "n_nodes": n_nodes,
            "n_edges": n_edges,
            "avg_nodes_per_graph": n_nodes / len(graphs) if graphs else 0.0,
            "avg_edges_per_graph": n_edges / len(graphs) if graphs else 0.0,
        }

    def print_summary(self, graphs: List[nx.DiGraph]) -> None:
        """Print instance-graph counts and average size."""
        stats = self.summarize(graphs)
        print("Instance graph summary")
        print(f"  graphs:                {stats['n_graphs']}")
        print(f"  total nodes:           {stats['n_nodes']}")
        print(f"  total edges:           {stats['n_edges']}")
        print(f"  avg nodes per graph:   {stats['avg_nodes_per_graph']:.2f}")
        print(f"  avg edges per graph:   {stats['avg_edges_per_graph']:.2f}")

    @staticmethod
    def save(graphs: List[nx.DiGraph], path: Path) -> None:
        """Pickle *graphs* to *path* for the next (SUBDUE) pipeline step."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as pickle_file:
            pickle.dump(graphs, pickle_file)

    @staticmethod
    def load(path: Path) -> List[nx.DiGraph]:
        """Load a list of DiGraphs previously written by :meth:`save`."""
        with open(path, "rb") as pickle_file:
            return pickle.load(pickle_file)


class InstanceGraphPipeline:
    """Orchestrates Petri net discovery, the BIG call, and .g parsing."""

    def __init__(
        self,
        config: InstanceGraphConfig,
        repository: Optional[EventLogRepository] = None,
        discoverer: Optional[PetriNetDiscoverer] = None,
        big_runner: Optional[BigRunner] = None,
        parser: Optional[InstanceGraphParser] = None,
    ) -> None:
        self.config = config
        self.repository = repository or EventLogRepository()
        self.discoverer = discoverer or PetriNetDiscoverer()
        self.big_runner = big_runner or BigRunner(config.big_command)
        self.parser = parser or InstanceGraphParser()

    def _build_discovery_log(self, log: EventLog) -> EventLog:
        """Return a copy of *log* whose activity key is config.activity_key.

        The result is also exported to config.discovery_log_path, since BIG
        (an external tool) needs an actual file to read, not an in-memory
        EventLog.
        """
        df = self.repository.to_dataframe(log)
        if self.config.activity_key not in df.columns:
            raise ValueError(
                f"activity_key '{self.config.activity_key}' not found in the log "
                f"(available columns: {list(df.columns)})."
            )
        df = df.copy()
        df[ACTIVITY_KEY] = df[self.config.activity_key]
        discovery_log = self.repository.to_event_log(df)
        self.repository.export_xes(discovery_log, self.config.discovery_log_path)
        return discovery_log

    def run(self, force: bool = False) -> List[nx.DiGraph]:
        """Run the full pipeline, returning the parsed instance graphs."""
        if force or not self.config.graphs_path.exists():
            log = self.repository.load(self.config.log_path)
            discovery_log = self._build_discovery_log(log)

            net, initial_marking, final_marking = self.discoverer.discover(discovery_log)
            self.discoverer.export(net, initial_marking, final_marking, self.config.petri_net_path)
            print(f"Discovered Petri net exported to '{self.config.petri_net_path}'")

            self.big_runner.run(
                self.config.discovery_log_path, self.config.petri_net_path, self.config.graphs_path
            )
            print(f"BIG instance graphs written to '{self.config.graphs_path}'")
        else:
            print(f"Reusing existing BIG output at '{self.config.graphs_path}'")

        graphs = self.parser.parse(self.config.graphs_path)
        self.parser.print_summary(graphs)

        self.parser.save(graphs, self.config.parsed_graphs_path)
        print(f"Parsed instance graphs saved to '{self.config.parsed_graphs_path}'")
        return graphs


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments; unset flags fall back to the YAML config."""
    parser = argparse.ArgumentParser(
        description="Generate instance graphs (log + Petri net -> BIG -> networkx) "
        "for organizational pattern mining."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to the YAML config file (default: '{DEFAULT_CONFIG_PATH}').",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        help="Path to the relabelled event log from step 1. Overrides the config file.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write the Petri net, .g file, and parsed graphs to. "
        "Overrides the config file.",
    )
    parser.add_argument(
        "--big-command",
        default=None,
        help="Command used to invoke BIG, with {log}/{petri_net}/{output} "
        "placeholders. Overrides the config file.",
    )
    parser.add_argument(
        "--activity-key",
        default=None,
        help="Event attribute to discover the Petri net from and hand to BIG "
        "(default: 'original_activity'). Overrides the config file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run Petri net discovery and BIG even if a .g file already exists.",
    )
    parser.add_argument(
        "--parse-only",
        default=None,
        metavar="G_FILE",
        help="Skip Petri net discovery and BIG entirely; just parse this existing "
        ".g file (e.g. the example BPI2017Denied.g) and save the result.",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> InstanceGraphConfig:
    """Build an InstanceGraphConfig from the YAML config file, overridden by any CLI flags."""
    config_path = Path(args.config)
    config = (
        InstanceGraphConfig.from_yaml(config_path)
        if config_path.exists()
        else InstanceGraphConfig()
    )

    if args.log_path is not None:
        config.log_path = Path(args.log_path)
    if args.output_dir is not None:
        config.output_dir = Path(args.output_dir)
    if args.big_command is not None:
        config.big_command = args.big_command
    if args.activity_key is not None:
        config.activity_key = args.activity_key
    return config


def main(argv: Optional[List[str]] = None) -> None:
    """Single entry point: parse arguments, build the pipeline, and run it."""
    args = parse_args(argv)
    config = build_config(args)

    try:
        if args.parse_only is not None:
            parser = InstanceGraphParser()
            graphs = parser.parse(Path(args.parse_only))
            parser.print_summary(graphs)
            parser.save(graphs, config.parsed_graphs_path)
            print(f"Parsed instance graphs saved to '{config.parsed_graphs_path}'")
        else:
            InstanceGraphPipeline(config).run(force=args.force)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

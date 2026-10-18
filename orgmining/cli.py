"""Command-line entry point for the organizational pattern mining pipeline.

Run from the project root, with the virtual environment active:

    python main.py preprocess                                   # step 1, asks the questions
    python main.py preprocess --attribute org:resource --grouping roles
    python main.py instance-graphs                              # step 2 on the step 1 output
    python main.py convert-g path/to/file.g                     # only convert a BIG .g file

Every step is a sub-command; ``python main.py <step> --help`` lists its options.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

# Avoid BLAS thread pools multiplying across alignment worker processes.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

from orgmining import config
from orgmining.instance_graphs import (DEFAULT_NOISE_THRESHOLD, DEFAULT_WORKERS, GFileConverter,
                                       InstanceGraphBuilder)
from orgmining.preprocessing import GROUPING_CHOICES, EventLogPreprocessor
from orgmining.roles import DEFAULT_ROLES_THRESHOLD
from orgmining.visualization import DEFAULT_COLUMNS, InstanceGraphViewer

DEFAULT_STEP1_RESULT = config.STEP1_OUTPUT_DIR / "org_resource_roles"
DEFAULT_GRAPHS = config.STEP2_OUTPUT_DIR / "org_resource_roles" / "instance_graphs.pkl"


def build_parser():
    parser = argparse.ArgumentParser(description="Mining organizational patterns (JM0211, group 5)")
    steps = parser.add_subparsers(dest="step", required=True)

    preprocess = steps.add_parser(
        "preprocess", help="Step 1: relabel every event as activity_selectedAttribute")
    preprocess.add_argument("--log", default=config.display_path(config.DEFAULT_LOG_PATH),
                            help="Input .xes or .xes.gz event log (default: %(default)s)")
    preprocess.add_argument("--attribute", default=None,
                            help="Attribute to fuse with the activity; if omitted you are asked")
    preprocess.add_argument("--grouping", choices=GROUPING_CHOICES, default=None,
                            help="'roles': replace each value by its discovered role; "
                                 "'none': use the values as they are; if omitted you are asked")
    preprocess.add_argument("--roles-threshold", type=float, default=DEFAULT_ROLES_THRESHOLD,
                            help="Similarity above which pm4py merges two roles (default: %(default)s)")
    preprocess.add_argument("--output-dir", default=config.display_path(config.STEP1_OUTPUT_DIR),
                            help="Where the step 1 outputs are written (default: %(default)s)")

    graphs = steps.add_parser(
        "instance-graphs", help="Step 2: Inductive Miner + BIG instance graphs -> networkx")
    graphs.add_argument("--step1-dir", default=config.display_path(DEFAULT_STEP1_RESULT),
                        help="Output folder of step 1 to use (default: %(default)s)")
    graphs.add_argument("--noise-threshold", type=float, default=DEFAULT_NOISE_THRESHOLD,
                        help="Noise threshold of the Inductive Miner (default: %(default)s)")
    graphs.add_argument("--miner-variant", choices=("im_clean", "imf"), default="im_clean",
                        help="Explicit PM4Py miner variant (default: %(default)s)")
    graphs.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="CPU cores BIG runs on in parallel (default: %(default)s on this machine)")
    graphs.add_argument("--max-traces", type=int, default=None,
                        help="Only use the first N traces, for a quick trial run")
    graphs.add_argument("--output-dir", default=config.display_path(config.STEP2_OUTPUT_DIR),
                        help="Where the step 2 outputs are written (default: %(default)s)")

    show = steps.add_parser(
        "show-graph", help="Print an instance graph as text and save a plot of it")
    which = show.add_mutually_exclusive_group(required=True)
    which.add_argument("--case", help="Case id, e.g. Application_1691306052")
    which.add_argument("--index", type=int, help="Position of the graph (0 = first trace)")
    show.add_argument("--graphs", default=config.display_path(DEFAULT_GRAPHS),
                      help="instance_graphs.pkl of step 2 (default: %(default)s)")
    show.add_argument("--output", default=None,
                      help="Image file (.png/.svg/.pdf); default: outputs/figures/<case>.png")
    show.add_argument("--columns", type=int, default=DEFAULT_COLUMNS,
                      help="Layers per row before the plot wraps (default: %(default)s)")

    convert = steps.add_parser(
        "convert-g", help="Convert an existing BIG .g file to networkx graphs (no BIG run)")
    convert.add_argument("g_file", help="The .g file to convert")
    convert.add_argument("--output", default=None,
                         help="Output .pkl file (default: next to the .g file)")
    conform = steps.add_parser("conformance", help="Align all cases against the saved full model")
    conform.add_argument("--log", default="outputs/step1_preprocessing/org_resource_roles/relabeled_log.xes")
    conform.add_argument("--net", default="outputs/step2_instance_graphs/org_resource_roles/petri_net.pnml")
    conform.add_argument("--output", default="outputs/conformance")
    conform.add_argument("--workers", type=int, default=3)
    conform.add_argument("--timeout", type=int, default=600)
    mine = steps.add_parser("mine-patterns", help="Run the assignment's upstream SUBDUE on all graphs")
    mine.add_argument("--graphs", default=config.display_path(DEFAULT_GRAPHS))
    mine.add_argument("--output", default="outputs/step3_patterns")
    mine.add_argument("--beam", type=int, default=4)
    mine.add_argument("--limit", type=int, default=5000)
    mine.add_argument("--max-edges", type=int, default=5)
    mine.add_argument("--numbest", type=int, default=20)
    export = steps.add_parser("export-graphs", help="Export every graph to SVG, text and GraphML")
    export.add_argument("--graphs", default=config.display_path(DEFAULT_GRAPHS))
    export.add_argument("--output", default="outputs/instance_graph_exports")
    evaluate = steps.add_parser("evaluate", help="Generate review packets and evaluate proxy/manual labels separately")
    evaluate.add_argument("--spec", default="evaluation/gold_standard_draft.json")
    evaluate.add_argument("--output", default="outputs/evaluation")
    steps.add_parser("inspect-repairs", help="Inspect worst/branching alignments and BIG repair sensitivity")
    steps.add_parser("paper-report", help="Generate paper tables, figures, report and results bundle")
    steps.add_parser("research", help="Resume conformance, mine, export, evaluate and prepare the paper bundle")
    return parser


def convert_g_file(g_file, output=None):
    """Convert a .g file on its own, e.g. the example BPI2017Denied.g of the assignment."""
    converter = GFileConverter()
    graphs = converter.convert(g_file)
    output = Path(output) if output else Path(g_file).with_suffix(".pkl")
    converter.save(graphs, output)
    table = converter.summarise(graphs)
    print(f"{len(graphs):,} graphs, {table['nodes'].sum():,} nodes, {table['edges'].sum():,} "
          f"edges; {100 * table['has_branching'].mean():.1f}% contain branching nodes")
    print(f"Saved to {config.display_path(output)}")


def show_graph(args):
    """Print one instance graph as text and save a plot of it."""
    viewer = InstanceGraphViewer.from_pickle(args.graphs)
    graph = viewer.find(case_id=args.case, index=args.index)
    print(viewer.describe(graph))
    output = args.output or config.OUTPUT_DIR / "figures" / f"{graph.graph.get('case_id')}.png"
    viewer.plot(graph, output, columns=args.columns)
    print(f"\nPlot saved to {config.display_path(output)}")


def ensure_fixed_hash_seed():
    """Restart with PYTHONHASHSEED=0 to reduce set-order variation.

    Python normally randomises the iteration order of sets per run. pm4py's
    Inductive Miner iterates over sets, so without a fixed seed the Petri net
    (and therefore the instance graphs) can differ between two identical runs.
    The seed must be set before Python starts, hence the restart. Worker
    processes inherit it through the environment.
    """
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        sys.exit(subprocess.call([sys.executable] + sys.argv))


def main():
    ensure_fixed_hash_seed()
    args = build_parser().parse_args()
    if args.step == "preprocess":
        preprocessor = EventLogPreprocessor.from_xes(args.log, args.output_dir)
        preprocessor.run(args.attribute, args.grouping, args.roles_threshold)
    elif args.step == "instance-graphs":
        InstanceGraphBuilder(args.step1_dir, args.output_dir, args.noise_threshold,
                             args.workers, args.max_traces, args.miner_variant).run()
    elif args.step == "show-graph":
        show_graph(args)
    elif args.step == "convert-g":
        convert_g_file(args.g_file, args.output)
    elif args.step == "conformance":
        from orgmining.conformance import run
        run(args.log, args.net, args.output, args.workers, args.timeout)
    elif args.step == "mine-patterns":
        from orgmining.patterns import run
        run(args.graphs, args.output, args.beam, args.limit, args.max_edges, args.numbest)
    elif args.step == "export-graphs":
        from orgmining.exports import run
        run(args.graphs, args.output)
    elif args.step == "evaluate":
        from orgmining.evaluation import run
        run(output=args.output,spec_path=args.spec)
    elif args.step == "inspect-repairs":
        from orgmining.repair_diagnostics import run
        run()
    elif args.step == "paper-report":
        from orgmining.reporting import run
        run()
    elif args.step == "research":
        from orgmining.research import run
        run()


if __name__ == "__main__":
    main()

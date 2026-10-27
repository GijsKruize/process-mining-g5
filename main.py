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

from orgmining import config
from orgmining.instance_graphs import (DEFAULT_NOISE_THRESHOLD, DEFAULT_WORKERS, GFileConverter,
                                       InstanceGraphBuilder)
from orgmining.pattern_mining import (DEFAULT_BEAM_WIDTH, DEFAULT_ITERATIONS, DEFAULT_LIMIT,
                                      DEFAULT_MAX_SIZE, DEFAULT_MIN_SIZE, DEFAULT_NUM_BEST,
                                      PatternMiner, SubdueSettings)
from orgmining.evaluation import run_evaluation
from orgmining.pattern_report import PatternReport
from orgmining.preprocessing import GROUPING_CHOICES, EventLogPreprocessor
from orgmining.roles import DEFAULT_ROLES_THRESHOLD
from orgmining.validation import TraceValidator
from orgmining.synthetic_experiment import (DEFAULT_NOISE_LEVELS, DEFAULT_SYNTHETIC_SETTINGS,
                                            SYNTHETIC_OUTPUT_DIR, SyntheticExperiment)
from orgmining.model_views import PetriNetRenderer, RoleActivityMatrix
from orgmining.visualization import DEFAULT_COLUMNS, InstanceGraphViewer

DEFAULT_STEP1_RESULT = config.STEP1_OUTPUT_DIR / "org_resource_roles"
DEFAULT_GRAPHS = config.STEP2_OUTPUT_DIR / "org_resource_roles" / "instance_graphs.pkl"
DEFAULT_NET = config.STEP2_OUTPUT_DIR / "org_resource_roles" / "petri_net.pnml"
FIGURES_DIR = config.OUTPUT_DIR / "figures"
DEFAULT_STEP3_RESULT = config.STEP3_OUTPUT_DIR / "org_resource_roles"
DEFAULT_GOLD = config.PROJECT_ROOT / "gold_standard" / "bpi2017_org_resource_roles.csv"


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
    preprocess.add_argument("--top-roles", type=int, default=None,
                            help="Keep only the k largest roles; the others become 'Other' "
                                 "(default: keep all)")
    preprocess.add_argument("--keep-lifecycle", action="store_true",
                            help="Keep the lifecycle steps in the work item names; by default "
                                 "they are removed and directly repeated equal labels merged")
    preprocess.add_argument("--output-dir", default=config.display_path(config.STEP1_OUTPUT_DIR),
                            help="Where the step 1 outputs are written (default: %(default)s)")

    graphs = steps.add_parser(
        "instance-graphs", help="Step 2: Inductive Miner + BIG instance graphs -> networkx")
    graphs.add_argument("--step1-dir", default=config.display_path(DEFAULT_STEP1_RESULT),
                        help="Output folder of step 1 to use (default: %(default)s)")
    graphs.add_argument("--noise-threshold", type=float, default=DEFAULT_NOISE_THRESHOLD,
                        help="Noise threshold of the Inductive Miner (default: %(default)s)")
    graphs.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="CPU cores BIG runs on in parallel (default: %(default)s on this machine)")
    graphs.add_argument("--max-traces", type=int, default=None,
                        help="Only use the first N traces, for a quick trial run")
    graphs.add_argument("--output-dir", default=config.display_path(config.STEP2_OUTPUT_DIR),
                        help="Where the step 2 outputs are written (default: %(default)s)")

    mine = steps.add_parser(
        "mine-patterns", help="Step 3: SUBDUE patterns, support and trace x pattern matrix")
    mine.add_argument("--graphs", default=config.display_path(DEFAULT_GRAPHS),
                      help="instance_graphs.pkl of step 2 (default: %(default)s)")
    mine.add_argument("--step1-dir", default=config.display_path(DEFAULT_STEP1_RESULT),
                      help="Step 1 folder, for the activity and role of each label "
                           "(default: %(default)s)")
    mine.add_argument("--beam", type=int, default=DEFAULT_BEAM_WIDTH,
                      help="SUBDUE beam width (default: %(default)s, as in the paper)")
    mine.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                      help="Patterns SUBDUE extends; 0 = auto (default: %(default)s)")
    mine.add_argument("--min-size", type=int, default=DEFAULT_MIN_SIZE,
                      help="Minimum pattern size in edges (default: %(default)s)")
    mine.add_argument("--max-size", type=int, default=DEFAULT_MAX_SIZE,
                      help="Maximum pattern size in edges (default: %(default)s)")
    mine.add_argument("--num-best", type=int, default=DEFAULT_NUM_BEST,
                      help="Patterns reported per iteration (default: %(default)s)")
    mine.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS,
                      help="SUBDUE iterations; >1 builds a hierarchy (default: %(default)s)")
    mine.add_argument("--max-graphs", type=int, default=None,
                      help="Only use the first N instance graphs, for a quick trial run")
    mine.add_argument("--original-subdue", action="store_true",
                      help="Run SUBDUE without the speed-ups (same result, much slower)")
    mine.add_argument("--output-dir", default=config.display_path(config.STEP3_OUTPUT_DIR),
                      help="Where the step 3 outputs are written (default: %(default)s)")

    report = steps.add_parser(
        "pattern-report", help="Figures for the report: patterns, support, overlap, handovers")
    report.add_argument("--step3-dir", default=config.display_path(DEFAULT_STEP3_RESULT),
                        help="Step 3 output folder (default: %(default)s)")
    report.add_argument("--graphs", default=config.display_path(DEFAULT_GRAPHS),
                        help="instance_graphs.pkl of step 2 (default: %(default)s)")
    report.add_argument("--top", type=int, default=20, help="Patterns to include (default: %(default)s)")

    evaluation = steps.add_parser(
        "evaluate", help="Precision/recall of step 3 runs and a baseline against the gold standard")
    evaluation.add_argument("--run", action="append", metavar="NAME=FOLDER",
                            help="A step 3 output folder to evaluate, e.g. "
                                 "'SUBDUE beam 4=outputs/step3_patterns/org_resource_roles'"
                                 "; repeat for several runs (default: the step 3 run)")
    evaluation.add_argument("--gold", default=config.display_path(DEFAULT_GOLD),
                            help="Gold standard CSV (default: %(default)s)")
    evaluation.add_argument("--graphs", default=config.display_path(DEFAULT_GRAPHS),
                            help="instance_graphs.pkl, for the baseline (default: %(default)s)")
    evaluation.add_argument("--output-dir", default=config.display_path(config.OUTPUT_DIR / "evaluation"),
                            help="Where the evaluation is written (default: %(default)s)")

    validate = steps.add_parser(
        "validate-trace", help="Compare one raw trace with its instance graph (sanity check)")
    validate.add_argument("--case", default="Application_1691306052",
                          help="Case id (default: %(default)s)")
    validate.add_argument("--step1-dir", default=config.display_path(DEFAULT_STEP1_RESULT),
                          help="Step 1 output folder (default: %(default)s)")
    validate.add_argument("--graphs", default=config.display_path(DEFAULT_GRAPHS),
                          help="instance_graphs.pkl of step 2 (default: %(default)s)")

    synthetic = steps.add_parser(
        "synthetic", help="Evaluation on synthetic logs with injected patterns and noise")
    synthetic.add_argument("--noise", type=float, nargs="+", default=list(DEFAULT_NOISE_LEVELS),
                           help="Noise levels: share of cases with one disturbance "
                                "(default: %(default)s)")
    synthetic.add_argument("--cases", type=int, default=500, help="Cases per log (default: %(default)s)")
    synthetic.add_argument("--seed", type=int, default=42, help="Random seed (default: %(default)s)")
    synthetic.add_argument("--iterations", type=int, default=DEFAULT_SYNTHETIC_SETTINGS.iterations,
                           help="SUBDUE iterations (default: %(default)s)")
    synthetic.add_argument("--num-best", type=int, default=DEFAULT_SYNTHETIC_SETTINGS.num_best,
                           help="SUBDUE patterns per iteration (default: %(default)s)")
    synthetic.add_argument("--beam", type=int, default=DEFAULT_BEAM_WIDTH,
                           help="SUBDUE beam width (default: %(default)s)")
    synthetic.add_argument("--top-roles", type=int, default=None,
                           help="Keep only the k largest roles (default: all)")
    synthetic.add_argument("--workers", type=int, default=4,
                           help="CPU cores for BIG (default: %(default)s)")
    synthetic.add_argument("--sweep", action="store_true",
                           help="Parameter study on the first noise level: top-k roles x beam "
                                "width x iterations, instead of the noise experiment")
    synthetic.add_argument("--output-dir", default=config.display_path(SYNTHETIC_OUTPUT_DIR),
                           help="Where the results are written (default: %(default)s)")

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

    net = steps.add_parser(
        "show-net", help="Describe and draw a Petri net (needs the Graphviz program 'dot')")
    source = net.add_mutually_exclusive_group()
    source.add_argument("--pnml", help="Petri net file to draw "
                                       f"(default: {config.display_path(DEFAULT_NET)})")
    source.add_argument("--log", help="Discover the net from this .xes log instead, with the "
                                      "same Inductive Miner settings as step 2")
    net.add_argument("--noise-threshold", type=float, default=DEFAULT_NOISE_THRESHOLD,
                     help="With --log: noise threshold of the Inductive Miner (default: %(default)s)")
    net.add_argument("--output", default=None,
                     help="Image file, .svg (zoomable, default), .png or .pdf; "
                          "default: outputs/figures/<name>.svg")
    net.add_argument("--describe-only", action="store_true",
                     help="Only print the size and parallel constructs; draw nothing")

    roles = steps.add_parser(
        "show-roles", help="Heatmap of which role performs which share of each activity")
    roles.add_argument("--step1-dir", default=config.display_path(DEFAULT_STEP1_RESULT),
                       help="Step 1 output folder with roles (default: %(default)s)")
    roles.add_argument("--output", default=None,
                       help="Image file; default: outputs/figures/roles_per_activity.png")

    convert = steps.add_parser(
        "convert-g", help="Convert an existing BIG .g file to networkx graphs (no BIG run)")
    convert.add_argument("g_file", help="The .g file to convert")
    convert.add_argument("--output", default=None,
                         help="Output .pkl file (default: next to the .g file)")
    return parser


def convert_g_file(g_file, output=None):
    """Convert a .g file on its own, e.g. the example BPI2017Denied.g of the assignment."""
    converter = GFileConverter()
    graphs = converter.convert(g_file)
    output = Path(output) if output else Path(g_file).with_suffix(".pkl")
    converter.save(graphs, output)
    table = converter.summarise(graphs)
    print(f"{len(graphs):,} graphs, {table['nodes'].sum():,} nodes, {table['edges'].sum():,} "
          f"edges; {100 * table['has_parallelism'].mean():.1f}% contain parallel branches")
    print(f"Saved to {config.display_path(output)}")


def show_graph(args):
    """Print one instance graph as text and save a plot of it."""
    viewer = InstanceGraphViewer.from_pickle(args.graphs)
    graph = viewer.find(case_id=args.case, index=args.index)
    print(viewer.describe(graph))
    output = args.output or config.OUTPUT_DIR / "figures" / f"{graph.graph.get('case_id')}.png"
    viewer.plot(graph, output, columns=args.columns)
    print(f"\nPlot saved to {config.display_path(output)}")


def show_net(args):
    """Describe a Petri net and draw it, from a .pnml file or discovered from a log."""
    if args.log:
        print(f"Discovering the net of {args.log} (noise threshold {args.noise_threshold}) ...")
        net, initial_marking, final_marking = PetriNetRenderer.discover(args.log, args.noise_threshold)
        name = f"net_{Path(args.log).stem}_noise{args.noise_threshold}"
    else:
        pnml = Path(args.pnml) if args.pnml else DEFAULT_NET
        net, initial_marking, final_marking = PetriNetRenderer.load(pnml)
        name = f"net_{pnml.parent.name}" if pnml.name == "petri_net.pnml" else f"net_{pnml.stem}"
    print(PetriNetRenderer.describe(net))
    if not args.describe_only:
        output = Path(args.output) if args.output else FIGURES_DIR / f"{name}.svg"
        PetriNetRenderer.render(net, initial_marking, final_marking, output)
        print(f"Drawing saved to {config.display_path(output)}")


def show_roles(args):
    """Heatmap and table of which role performs which share of every activity."""
    matrix = RoleActivityMatrix.from_step1(args.step1_dir)
    summary = matrix.summary()
    csv_path = Path(args.step1_dir) / "roles_per_activity.csv"
    summary.to_csv(csv_path)
    output = Path(args.output) if args.output else FIGURES_DIR / "roles_per_activity.png"
    matrix.plot(output)
    print(summary.to_string())
    print(f"\nTable saved to {config.display_path(csv_path)}")
    print(f"Heatmap saved to {config.display_path(output)}")


def ensure_fixed_hash_seed():
    """Restart this script once with PYTHONHASHSEED=0, so every run gives the same result.

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
        preprocessor.run(args.attribute, args.grouping, args.roles_threshold, args.top_roles,
                         collapse_lifecycle=not args.keep_lifecycle)
    elif args.step == "instance-graphs":
        InstanceGraphBuilder(args.step1_dir, args.output_dir, args.noise_threshold,
                             args.workers, args.max_traces).run()
    elif args.step == "mine-patterns":
        settings = SubdueSettings(args.beam, args.limit, args.min_size, args.max_size,
                                  args.num_best, args.iterations)
        PatternMiner(args.graphs, Path(args.step1_dir) / "label_counts.csv", args.output_dir,
                     settings, args.max_graphs, fast=not args.original_subdue).run()
    elif args.step == "pattern-report":
        paths = PatternReport(args.step3_dir, args.graphs).build(args.top)
        print(f"{len(paths)} figures saved to {config.display_path(paths[0].parent)}")
    elif args.step == "evaluate":
        runs = dict(run.split("=", 1) for run in args.run) if args.run else {
            "SUBDUE (10 iterations, beam 4)": DEFAULT_STEP3_RESULT}
        table = run_evaluation(runs, args.gold, GFileConverter.load(args.graphs), args.output_dir)
        print(table.to_string(index=False))
        print(f"\nEvaluation written to {args.output_dir}")
    elif args.step == "validate-trace":
        trace, checks = TraceValidator(args.step1_dir, args.graphs).validate(args.case)
        print(trace.to_string(index=False))
        print("\nChecks:\n  " + "\n  ".join(checks))
        path = config.OUTPUT_DIR / "validation" / f"{args.case}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        trace.to_csv(path, index=False)
        print(f"\nTable saved to {config.display_path(path)}")
    elif args.step == "synthetic":
        settings = SubdueSettings(beam_width=args.beam, iterations=args.iterations,
                                  num_best=args.num_best)
        experiment = SyntheticExperiment(args.noise, args.cases, args.seed, settings,
                                         top_k=args.top_roles, workers=args.workers,
                                         output_root=args.output_dir)
        if args.sweep:
            table = experiment.sweep(args.noise[0])
            print(table.drop(columns=["gold_found"]).to_string(index=False))
        else:
            table = experiment.run()
            print(table[["noise", "roles", "role_purity", "parallel_graphs_pct", "precision",
                         "recall", "f1", "baseline_f1"]].to_string(index=False))
        print(f"\nResults written to {args.output_dir}")
    elif args.step == "show-graph":
        show_graph(args)
    elif args.step == "show-net":
        show_net(args)
    elif args.step == "show-roles":
        show_roles(args)
    elif args.step == "convert-g":
        convert_g_file(args.g_file, args.output)


if __name__ == "__main__":
    main()

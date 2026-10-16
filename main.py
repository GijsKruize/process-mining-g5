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
from orgmining.preprocessing import GROUPING_CHOICES, EventLogPreprocessor
from orgmining.roles import DEFAULT_ROLES_THRESHOLD

DEFAULT_STEP1_RESULT = config.STEP1_OUTPUT_DIR / "org_resource_roles"


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
    graphs.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="CPU cores BIG runs on in parallel (default: %(default)s on this machine)")
    graphs.add_argument("--max-traces", type=int, default=None,
                        help="Only use the first N traces, for a quick trial run")
    graphs.add_argument("--output-dir", default=config.display_path(config.STEP2_OUTPUT_DIR),
                        help="Where the step 2 outputs are written (default: %(default)s)")

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
        preprocessor.run(args.attribute, args.grouping, args.roles_threshold)
    elif args.step == "instance-graphs":
        InstanceGraphBuilder(args.step1_dir, args.output_dir, args.noise_threshold,
                             args.workers, args.max_traces).run()
    elif args.step == "convert-g":
        convert_g_file(args.g_file, args.output)


if __name__ == "__main__":
    main()

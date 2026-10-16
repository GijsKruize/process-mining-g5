"""Command-line entry point for the organizational pattern mining pipeline.

Examples (run from the project root, with the virtual environment active):

    python main.py preprocess                          # asks which attribute
    python main.py preprocess --attribute org:resource # no question asked
    python main.py preprocess --log path/to/other.xes

Every step is a sub-command; later steps will be added here as well.
"""
import argparse

from orgmining import config
from orgmining.preprocessing import EventLogPreprocessor


def build_parser():
    parser = argparse.ArgumentParser(description="Mining organizational patterns (JM0211, group 5)")
    steps = parser.add_subparsers(dest="step", required=True)

    preprocess = steps.add_parser(
        "preprocess", help="Step 1: relabel every event as activity_selectedAttribute")
    preprocess.add_argument("--log", default=config.display_path(config.DEFAULT_LOG_PATH),
                            help="Input .xes or .xes.gz event log (default: %(default)s)")
    preprocess.add_argument("--attribute", default=None,
                            help="Attribute to fuse with the activity; if omitted you are asked")
    preprocess.add_argument("--output-dir", default=config.display_path(config.STEP1_OUTPUT_DIR),
                            help="Where the step 1 outputs are written (default: %(default)s)")
    return parser


def main():
    args = build_parser().parse_args()
    if args.step == "preprocess":
        preprocessor = EventLogPreprocessor.from_xes(args.log, args.output_dir)
        preprocessor.run(args.attribute)


if __name__ == "__main__":
    main()

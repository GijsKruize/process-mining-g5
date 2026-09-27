"""Main entry point: runs the whole JM0211 organizational pattern mining pipeline.

    python main.py data/BPI2017Denied(3).xes

Runs preprocessing (step 1, interactive), instance graph generation (step 2),
pattern mining (step 3), and evaluation against gold_standard.csv (step 4).
"""
import argparse

import evaluate
import pattern_mining
from instance_graphs import InstanceGraphBuilder
from preprocess import Preprocessor


def main():
    parser = argparse.ArgumentParser(description="Run the full organizational pattern mining pipeline.")
    parser.add_argument("input_path", help="Path to the input .xes event log")
    parser.add_argument("--attribute", default=None,
                         help="Attribute to fuse into the activity label (skips the interactive prompt)")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--gold-standard", default="gold_standard.csv")
    args = parser.parse_args()

    print("=== Step 1: preprocessing ===")
    log_path = Preprocessor(args.input_path).run(attribute=args.attribute, output_dir=args.output_dir)

    print("\n=== Step 2: instance graphs ===")
    InstanceGraphBuilder(args.output_dir).run(log_path)

    print("\n=== Step 3: pattern mining ===")
    miner = pattern_mining.PatternMiner(args.output_dir)
    patterns, stats, matrix, union_graph = miner.run(f"{args.output_dir}/instance_graphs.pkl")

    print("\n=== Step 4: evaluation ===")
    gold_standard = evaluate.load_gold_standard(args.gold_standard)
    mined_signatures = evaluate.mined_pattern_signatures(patterns, union_graph)
    precision, recall = evaluate.evaluate(mined_signatures, gold_standard)
    print(f"Precision: {precision:.2f}")
    print(f"Recall:    {recall:.2f}")


if __name__ == "__main__":
    main()

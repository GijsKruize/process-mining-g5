"""Main entry point: runs the whole JM0211 organizational pattern mining pipeline.

    python main.py "data/BPI2017Denied(3).xes" --attribute org:resource --workers 4

Step 1  preprocess.py       relabel events as <activity>_<attribute group>
Step 2  instance_graphs.py  Petri net (Inductive Miner) + BIG instance graphs
Step 3  pattern_mining.py   SUBDUE patterns, support, trace-pattern matrix
Step 4  evaluate.py         precision/recall against a gold standard (optional)

All options of the individual steps are available here; run with ``--help``.
"""
import argparse
import json
import time
from pathlib import Path

import determinism
import evaluate
import pattern_mining
from instance_graphs import (InstanceGraphBuilder, add_instance_graph_arguments,
                             instance_graph_kwargs_from_args)
from preprocess import Preprocessor, add_preprocess_arguments


def main():
    # Restart once with a fixed hash seed so that two runs give identical
    # output (see determinism.py). Must happen before anything else.
    determinism.ensure_fixed_hash_seed()

    parser = argparse.ArgumentParser(description="Run the full organizational pattern mining pipeline.")
    parser.add_argument("input_path", help="Path to the input .xes event log")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--gold-standard", default=None,
                        help="CSV with the expected patterns for this log and attribute. Without it "
                             "step 4 is skipped: a gold standard only makes sense for the log it "
                             "was written for")
    add_preprocess_arguments(parser)
    add_instance_graph_arguments(parser)
    pattern_mining.add_subdue_arguments(parser)
    args = parser.parse_args()
    started = time.time()

    print("=== Step 1: preprocessing ===")
    log_path = Preprocessor(args.input_path).run(
        attribute=args.attribute,
        output_dir=args.output_dir,
        grouping=args.grouping,
        grouping_coverage=args.grouping_coverage,
        roles_threshold=args.roles_threshold,
    )

    print("\n=== Step 2: instance graphs ===")
    InstanceGraphBuilder(args.output_dir).run(log_path, **instance_graph_kwargs_from_args(args))

    print("\n=== Step 3: pattern mining ===")
    miner = pattern_mining.PatternMiner(args.output_dir)
    patterns, stats, matrix, union_graph = miner.run(
        f"{args.output_dir}/instance_graphs.pkl",
        exclude_activities=pattern_mining.excluded_activities_from_args(args),
        min_instances=args.min_instances,
        **pattern_mining.subdue_kwargs_from_args(args),
    )

    print("\n=== Step 4: evaluation ===")
    if not args.gold_standard:
        print("Skipped: no --gold-standard given.")
    else:
        gold_standard = evaluate.load_gold_standard(args.gold_standard)
        mined_signatures = evaluate.mined_pattern_signatures(patterns, union_graph)
        precision, recall = evaluate.evaluate(mined_signatures, gold_standard)
        contains_precision, contains_recall = evaluate.evaluate(
            mined_signatures,
            gold_standard,
            mode="contains",
        )
        metrics = {
            "gold_standard": args.gold_standard,
            "mined_patterns": len(mined_signatures),
            "gold_patterns": len(gold_standard),
            "exact_precision": precision,
            "exact_recall": recall,
            "contains_precision": contains_precision,
            "contains_recall": contains_recall,
        }
        metrics_path = Path(args.output_dir) / "evaluation_metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
        print(f"Exact precision:    {precision:.2f}")
        print(f"Exact recall:       {recall:.2f}")
        print(f"Contains precision: {contains_precision:.2f}")
        print(f"Contains recall:    {contains_recall:.2f}")
        print(f"Saved evaluation metrics to '{metrics_path}'")

    print(f"\nPipeline finished in {time.time() - started:.0f}s.")


if __name__ == "__main__":
    main()

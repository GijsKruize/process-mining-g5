"""Table 6 of the reference paper ("Experimental results of the hospital
log") for our logs: SUBDUE with beam width 4, 10 and 20.

Run with::

    python beam_table.py

after step 1 (BPI 2017) and step 4 (synthetic log) of ``main.py``; it reuses
their saved instance graphs and reruns only SUBDUE, so nothing there is
overwritten. Settings whose instance graphs are missing are skipped.

Columns, per setting and beam width (top list: the ``NUM_BEST`` best patterns):

    Subs             every pattern SUBDUE found in the search
    % top subs       the share of them in the top list (NUM_BEST / Subs)
    COV (%)          edges of all instance graphs covered by a top pattern instance
    DIV              average dissimilarity of the top patterns' activity sets,
                     x 100 (same scale as the paper)
    REP first 10 / REP all
                     average REP (% of cases with a SUBDUE instance of the
                     pattern) of the first 10 and of all top patterns
    seconds          SUBDUE's run time

For the synthetic log also precision, recall and F1 against the gold
standard (containment matching, as in step 4). Results go to
``output/beam_table/``: one CSV per setting, all of them in
``beam_table.csv``, and ``beam_table.tex`` for the paper.
"""
import json
import pickle
import time

import pandas as pd

from main import (
    INSTANCE_GRAPH_DIR, PROJECT_ROOT, SYNTHETIC_OUTPUT_DIR,
    EvaluationStep, PatternMiningStep, SyntheticValidationStep,
)

BEAMS = (4, 10, 20)
NUM_BEST = 20
OUTPUT_DIR = PROJECT_ROOT / "output" / "beam_table"

# setting -> (instance graphs, minimum pattern edges as in its step,
#             evaluation folder of step 4 (gold standard) or None)
SETTINGS = {
    "synthetic_eval1_known_roles": (
        SYNTHETIC_OUTPUT_DIR / "eval1_known_roles" / "instance graphs" / "instance_graphs_pm4py.pkl",
        1, "eval1_known_roles"),
    "synthetic_eval2_full_pipeline": (
        SYNTHETIC_OUTPUT_DIR / "eval2_full_pipeline" / "instance graphs" / "instance_graphs_pm4py.pkl",
        1, "eval2_full_pipeline"),
    "bpi2017": (INSTANCE_GRAPH_DIR / "instance_graphs_pm4py.pkl", 2, None),
}


def gold_scores(evaluation, patterns):
    """Containment precision/recall/F1 of the top patterns against the gold
    standard, labels mapped to departments as in step 4."""
    step = SyntheticValidationStep()
    mapping = {}
    role_table_path = SYNTHETIC_OUTPUT_DIR / evaluation / "role_discovery.csv"
    if role_table_path.exists():
        mapping = step.role_mapping(pd.read_csv(role_table_path, dtype=str))
    pattern_graphs = [step.map_labels(PatternMiningStep.pattern_to_networkx(pattern.definition), mapping)
                      for pattern in patterns]
    _, scores = step.score_patterns(pattern_graphs, step.load_gold(), step.contains_match)
    return {"precision": scores["precision"], "recall": scores["recall"], "f1": scores["f1"],
            "gold_missed": " ".join(scores["gold_missed"])}


def table_row(graphs, beam, min_pattern_edges, evaluation):
    params = {"beam_width": beam, "iterations": 1, "min_pattern_edges": min_pattern_edges,
              "max_pattern_edges": 0, "num_best": NUM_BEST}
    mining_step = PatternMiningStep()
    started = time.time()
    all_patterns = mining_step.run_subdue(graphs, params)
    search = mining_step.search_summary(all_patterns, params, time.time() - started)
    top = all_patterns[:NUM_BEST]
    metrics = EvaluationStep().pattern_metrics(top, graphs)
    rep = [100 * len(mining_step.subdue_traces(pattern)) / len(graphs) for pattern in top]

    def average(values):
        return round(sum(values) / len(values), 2) if values else 0.0

    row = {
        "beam": beam,
        "subs": search["subs"],
        "top_subs_pct": search["top_subs_pct"],
        "COV_pct": round(100 * metrics["COV"], 2),
        "DIV": round(100 * metrics["DIV"], 2),
        "REP_first_10": average(rep[:10]),
        "REP_all": average(rep),
        "seconds": search["seconds"],
    }
    if evaluation:
        row.update(gold_scores(evaluation, top))
    return row


def latex(table):
    """One LaTeX table, a block of rows per setting, columns as in Table 6."""
    lines = [
        r"\begin{tabular}{llrrrrl}",
        r"\hline",
        r"Setting & Beam & Subs & \% top subs & COV (\%) & DIV & Top subs REP (\%) [avg. first 10] \{avg. all\} \\",
        r"\hline",
    ]
    for setting, rows in table.groupby("setting", sort=False):
        for index, row in enumerate(rows.itertuples()):
            name = setting.replace("_", r"\_") if index == 0 else ""
            lines.append(f"{name} & {row.beam} & {row.subs} & {row.top_subs_pct} & {row.COV_pct} & "
                         f"{row.DIV} & [{row.REP_first_10}]\\{{{row.REP_all}\\}} \\\\")
        lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tables = []
    for setting, (graphs_path, min_pattern_edges, evaluation) in SETTINGS.items():
        if not graphs_path.exists():
            print(f"Skipping {setting}: no instance graphs at {graphs_path} "
                  f"(run {'step 4' if evaluation else 'step 1'} of main.py first)")
            continue
        with open(graphs_path, "rb") as file:
            graphs = pickle.load(file)
        rows = []
        for beam in BEAMS:
            print(f"\n=== {setting}, beam {beam} ({len(graphs)} instance graphs) ===", flush=True)
            rows.append(table_row(graphs, beam, min_pattern_edges, evaluation))
        table = pd.DataFrame(rows)
        table.to_csv(OUTPUT_DIR / f"table_{setting}.csv", index=False)
        tables.append(table.assign(setting=setting))

    if not tables:
        return
    table = pd.concat(tables, ignore_index=True)
    table = table[["setting"] + [column for column in table.columns if column != "setting"]]
    table.to_csv(OUTPUT_DIR / "beam_table.csv", index=False)
    (OUTPUT_DIR / "beam_table.tex").write_text(latex(table))
    with open(OUTPUT_DIR / "settings.json", "w") as file:
        json.dump({"beams": BEAMS, "num_best": NUM_BEST, "iterations": 1,
                   "min_pattern_edges": {name: values[1] for name, values in SETTINGS.items()}},
                  file, indent=2)
    print("\n" + table.to_string(index=False))
    print(f"\nBeam table saved in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

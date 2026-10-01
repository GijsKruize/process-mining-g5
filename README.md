# Mining Organizational Patterns — JM0211, Group 5

Implementation of the pipeline from the assignment: preprocess an event log,
build instance graphs with BIG, mine behavioral patterns with SUBDUE, and
evaluate them against a gold standard.

## Project structure

```
preprocess.py         # step 1: relabel activities with a chosen attribute
big_engine.py          # BIG's instance-graph algorithm, see "About BIG" below
instance_graphs.py     # step 2: Petri net + BIG -> networkx instance graphs
pattern_mining.py      # step 3: SUBDUE pattern mining + stats + visualization
evaluate.py             # step 4: precision/recall vs. gold_standard.csv
main.py                 # runs all steps in one go
subdue/                 # vendored SUBDUE algorithm (MIT licensed)
gold_standard.csv       # synthetic validation gold standard
data/                   # put your input .xes file here
output/                 # all generated files land here
datasets_group5_mining_organizational_patterns/   # course-provided dataset
```

## Requirements

- Python 3.9 (pm4py 2.2.16, required for BIG, does not install on newer
  Python versions)

## Installation

```bash
python3.9 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Running

Run everything in one go:

```bash
python main.py "data/BPI2017Denied(3).xes"
```

Synthetic validation run:

```bash
python main.py data/synthetic_validation.xes --attribute org:group --iterations 2
```

This runs preprocessing (step 1, interactive — it will ask which attribute
to fuse into the activity label), then instance graph generation (step 2),
pattern mining (step 3), and evaluation (step 4), in order. The `main.py`
entry point uses the same SUBDUE defaults as `pattern_mining.py`
(`--num-best 6 --min-size 1 --max-size 8 --beam-width 4 --limit 500`), so
the one-command pipeline reproduces the six-pattern mining configuration.
Use `--iterations 2` or higher to enable SUBDUE's compression hierarchy.
Each step can also be run on its own:

```bash
python preprocess.py "data/BPI2017Denied(3).xes"
python instance_graphs.py
python pattern_mining.py
python evaluate.py
```

## Step 1 — preprocessing

Prints every attribute in the log with a few example values, then asks
which one to fuse into the activity label (e.g. `org:resource` for
individual resources, or a coarser attribute like `EventOrigin`). Every
event's activity becomes `<activity>_<attribute value>`.

Output: `output/relabeled_log.xes`, `output/relabeled_log.csv`.
It also writes `output/attribute_recommendations.csv`.

Note on granularity: choose a coarser attribute if the log has many
distinct resource values. `org:resource` alone has 134 distinct values in
the BPI2017 log, and fusing it into the activity makes Inductive Miner
(step 2) extremely slow. `EventOrigin` (3 values) is a fast, "department"-
level example. Other useful candidates to investigate before `org:resource`
are `Action`, `lifecycle:transition`, and case/context attributes such as
`case:ApplicationType` or `case:LoanGoal` for validation slices.

## Step 2 — instance graphs

Discovers a Petri net with the Inductive Miner, then builds one instance
graph per trace with BIG (aligns the trace to the net, then repairs the
graph around the alignment's skip/insert steps — see Definition 18 in [1]).

No BIG jar was provided for this course run, so `big_engine.py` is a direct
port of BIG's own reference algorithm (`newbig2.py` from
https://github.com/a-mircoli/big-gui, by the same research group) as a
plain function, with the Spark/Docker/GUI wrapper removed.

Output: `output/petri_net.pnml`, `output/instance_graphs.g` (BIG's raw
text output), `output/instance_graphs.pkl` (parsed `networkx.DiGraph` list,
one per trace, globally unique node ids).

## Step 3 — pattern mining

All instance graphs are merged into one union graph (their node ids are
already globally unique, so a pattern can never span two traces) and mined
with SUBDUE, vendored under `subdue/` from
https://github.com/holderlb/Subdue. Two bugs were fixed while vendoring it
(see the comments in `subdue/Graph.py` and `subdue/Subdue.py`): edge
direction from a networkx graph was silently ignored, and pattern matching
against the union graph was O(edges²) — fine for one small graph, not for
tens of thousands of merged edges.

Output: `output/patterns.pkl`, `output/pattern_stats.csv` (size, instance
count, and support per pattern), `output/trace_pattern_matrix.csv` (rows =
traces, columns = patterns, 1 if the pattern occurs in that trace),
`output/pattern_hierarchy.pkl`, `output/pattern_hierarchy.csv`, and
`output/patterns/pattern_N.png` (a rendered example instance per pattern).
When `--iterations` is greater than 1, SUBDUE may output compressed
`PATTERN-i-j` nodes. The miner keeps those raw hierarchical records, expands
them back to original event nodes for stats/evaluation/visualization, and
marks them as `hierarchical_expanded` in `pattern_stats.csv`.

## Step 4 — evaluation

`gold_standard.csv` now contains a tiny synthetic validation target for
`data/synthetic_validation.xes` with `--attribute org:group`. Rows with
`A->B` are edge-based behavioral patterns; rows without arrows are still
accepted as the older comma-separated activity-label sets. Precision =
fraction of mined patterns that match a gold pattern exactly; recall =
fraction of gold patterns found among the mined ones.

## References

[1] Diamantini, Genga, Potena. "Behavioral process mining for unstructured
processes." Journal of Intelligent Information Systems 47 (2016): 5-32.

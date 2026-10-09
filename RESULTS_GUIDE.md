# Results Guide

This file records the runs that are useful for the assignment report and how
to read the generated artefacts.

## Runs

### BPI2017 denied, 80% behavior, no mining filter

Command:

```powershell
.venv\Scripts\python.exe pattern_mining.py --graphs-path output_resource_80_model_original\instance_graphs.pkl --output-dir output_resource_80_behavior_only --num-best 10 --min-size 2 --max-size 8 --limit 700 --exclude-activities=
```

Result: the strongest patterns are dominated by low-value bookkeeping
activities:

- `start_User_1 -> A-Create-Application_User_1 -> A-Submitted_User_1`
- `A-Create-Application_User_1 -> A-Submitted_User_1 -> W-Handle-leads-schedule_User_1`

Use this as evidence that keeping 80% of frequent trace variants helps
runtime, but it does not by itself remove uninformative patterns.

### BPI2017 denied, 80% behavior, filtered before SUBDUE

Command:

```powershell
.venv\Scripts\python.exe main.py "data\BPI2017Denied(3).xes" --attribute org:resource --output-dir output_resource_80_model_original --variant-coverage 0.8 --exclude-activities start,end,A-Create-Application,A-Submitted --num-best 10 --min-size 2 --max-size 8 --limit 700
```

Important results:

- Variant filter kept `2475/3093` traces, i.e. `80.0%`.
- The process model was discovered on `original_activity`, giving 98 Petri-net
  transitions, while the instance graph nodes still contain
  `activity_org:resource` labels.
- The mining filter removed 9232 low-value nodes and 21804 edges before SUBDUE.
- Top mined pattern after filtering:
  `W-Handle-leads-schedule_User_1 -> W-Handle-leads-withdraw_User_1 -> W-Complete-application-schedule_User_1`,
  support `1296/2475 = 52.4%`.

This is the better result to discuss in the report, because the pattern is a
work-practice sequence rather than a technical start/submission prefix.

### Synthetic validation

Command:

```powershell
.venv\Scripts\python.exe main.py data\synthetic_validation.xes --attribute org:group --output-dir output_synthetic_validation_fixed --variant-coverage 1.0 --exclude-activities= --num-best 10 --min-size 1 --max-size 4 --limit 100 --gold-standard synthetic_gold_standard.csv
```

Results:

- Exact precision: `0.38`
- Exact recall: `0.75`
- Contains precision: `1.00`
- Contains recall: `1.00`

Interpretation: exact matching is strict, because SUBDUE also reports larger
super-patterns such as `Register -> Check -> Approve -> Notify`. The contains
metric shows that all deliberate gold-standard behaviors are recovered inside
the mined structures.

### Synthetic hierarchical SUBDUE

Command:

```powershell
.venv\Scripts\python.exe pattern_mining.py --graphs-path output_synthetic_validation_fixed\instance_graphs.pkl --output-dir output_synthetic_validation_hierarchy --num-best 10 --min-size 1 --max-size 4 --limit 100 --iterations 2 --exclude-activities=
```

Result: `pattern_stats.csv` contains both `core` and
`hierarchical_expanded` rows. These are the expanded forms of SUBDUE's
compressed `PATTERN-i-j` nodes. Use this to explain the extra hierarchy layer:
the code keeps the compressed hierarchy, but visualizes and evaluates the
expanded original events.

## How to Read Output Files

- `variant_filter_stats.json`: proves how many traces/variants were retained
  before Inductive Miner.
- `mining_filter_stats.json`: records which activities were removed before
  SUBDUE and how much graph size was reduced.
- `instance_graphs.g`: BIG-style text output. Each `XP` block is one trace;
  `v` rows are nodes and `e` rows are directed edges.
- `instance_graphs.pkl`: the parsed `networkx` graph list used by SUBDUE.
- `pattern_stats.csv`: main result table. Use `support_count` and
  `support_fraction` to report how often a pattern occurs.
- `trace_pattern_matrix.csv`: rows are traces and columns are patterns; `1`
  means that trace contains the pattern.
- `pattern_hierarchy.csv`: tells whether a pattern is a direct core SUBDUE
  pattern or an expanded hierarchical pattern.
- `patterns/pattern_N.png`: visual examples for the report.
- `evaluation_metrics.json`: precision/recall output when `main.py` is used.

## Viewing Instance Graphs

Use the viewer script to render individual BIG instance graphs:

```powershell
.venv\Scripts\python.exe visualize_instance_graphs.py --graphs-path output_resource_80_model_original\instance_graphs.pkl --trace-ids 0,1,2 --output-dir output_resource_80_model_original\instance_graph_views
```

The PNGs are useful for explaining what BIG produces before SUBDUE compresses
frequent graph structures into behavioral patterns.

## Code Map

- `preprocess.py`: loads the XES log, shows available attributes, and creates
  labels like `Activity_User_1`.
- `instance_graphs.py`: applies the 80% frequent-variant filter, discovers the
  Petri net on `original_activity`, runs BIG, and parses BIG output.
- `big_engine.py`: local implementation of the provided BIG algorithm.
- `pattern_mining.py`: runs SUBDUE, filters low-value activities before mining,
  expands hierarchical `PATTERN-i-j` structures, writes stats and images.
- `evaluate.py`: compares mined patterns against the synthetic gold standard
  using exact and contains precision/recall.
- `main.py`: runs the full assignment pipeline end to end.

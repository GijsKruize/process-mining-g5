# Mining Organizational Patterns (JM0211, group 5)

Implementation of the behavioral pattern mining approach of Diamantini, Genga &
Potena (2016), *Behavioral process mining for unstructured processes*, on the
BPI Challenge 2017 (denied applications) log.

| Step | What |
|------|------|
| 1 | Instance graph generation: show the log's attributes and let the user pick one, relabel every event as `activity_value` (values optionally grouped into roles, lifecycle collapsed), discover a Petri net (Inductive Miner), run BIG, save the instance graphs |
| 2 | Pattern mining: SUBDUE on the saved instance graphs; support, trace × pattern matrix (rows: case ids), pattern figures |
| 3 | Evaluation: alignment fitness of the Petri net and the instance graphs, plus FREQ/REP/COV/DIV of the patterns |
| 4 | Synthetic validation: steps 1 and 2 on a small hand-made log with a known gold standard, twice (known roles, and roles discovered by pm4py); precision and recall, side by side |
| `figures.py` | Figures of one chosen case for paper/poster, like Figure 1 of the assignment: trace → instance graph → patterns |
| `beam_table.py` | Table 6 of the reference paper (Subs, % top subs, COV, DIV, REP) for beam 4, 10 and 20, on BPI 2017 and both synthetic evaluations |

## Requirements

- **Python 3.9.** The assignment requires **pm4py 2.2.16** (needed for BIG),
  which does not run on newer Python versions.
- **`BIG.py`** from Canvas (course material, not ours to redistribute), placed
  in the project root, next to `main.py`. Both the unchanged Canvas version
  and the sped-up version (see *BIG.py performance work* below, which adds
  `run_big_chunk`) work: without `run_big_chunk`, `main.py` runs the Canvas
  `BIG.big` per chunk itself (`run_canvas_big_chunk`).
- The event logs from Canvas: `data/BPI2017Denied(3).xes` (full log) and
  `data/BPI2017Denied_10pct.xes` (10% sample, used for evaluation). Too large
  for git, so not in this repository.

## Installation

Run these commands in order, from a terminal (Git Bash, macOS or Linux), from
the project root:

```bash
# 1. Get the code
git clone <repository-url> process-mining-g5
cd process-mining-g5

# 2. Create and activate a virtual environment with Python 3.9
python3.9 -m venv .venv            # Windows: py -3.9 -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
                                    # Windows PowerShell: .\.venv\Scripts\activate

# 3. Install the pinned dependencies
pip install -r requirements.txt

# 4. Place BIG.py (from Canvas, unchanged) in the project root, and the event
#    logs under data/ (see Requirements above)
```

`requirements.txt` pins pm4py 2.2.16 and its complete dependency tree, so
everyone gets exactly the same environment.

## Running

Everything runs through one entry point, from the project root with the
virtual environment active:

```bash
python main.py
```

This opens a numbered menu:

```
============================================================
BPI 2017 organizational pattern mining pipeline
============================================================
  1. Instance graph generation  [not run yet]
  2. Pattern mining  [not run yet]
  3. Evaluation  [not run yet]
  4. Synthetic validation (gold standard)  [not run yet]
  A. Run all steps, in order (1, 2, 3, then 4)
  0. Exit

Select a step to run:
```

Pick a step by number (or `A` for all of them in order). It asks for that
step's own parameters one at a time - each with a one-line explanation and a
suggested default (press Enter to accept it) - then runs straight through;
there are no further questions once the parameters are set.

Run step 1, then step 2, then step 3, in that order (each needs the previous
step's output, and reruns it fresh every time - there is no reuse-the-last-
run checkpoint); rerun any one of them individually afterwards to try
different parameters. Step 4 is independent of steps 1-3: it runs its own
copy of steps 1 and 2 on the synthetic log.

**Choosing the attribute (step 1).** Step 1 first loads the log and prints
every attribute: level (event, or trace for `case:` attributes), number of
distinct values, % of events that have a value, and examples. Type the number
or name of the attribute to analyse (Enter = `org:resource`); every event is
then labeled `<activity>_<value>`, e.g. `A-Submitted_Role_4`. The case id,
activity and timestamp are listed but cannot be chosen. Grouping into roles
is suggested only for attributes with more than 20 distinct values.

**Defaults.** Inductive Miner noise threshold 0.2 and SUBDUE beam width 10,
as chosen by the team for the paper; `beam_table.py` shows what beam 4 and 20
would give.

**Figures for the paper and poster.** After steps 1 and 2 (or step 4):

```bash
python figures.py
```

Choose the BPI results or one of the two synthetic evaluations, then `L`
lists candidate cases (some parallel work, many patterns, few events first)
so you can pick a clear example by hand; `C` + a case id writes, to
`output/figures/<case id>/` (synthetic: `output/synthetic
validation/<evaluation>/figures/<case id>/`): `trace.png`,
`instance_graph.png`, one `P<k>.png` and `P<k>_in_case.png` (the pattern
highlighted in this case) per pattern it contains, and `figure1.png` (trace →
instance graph → up to 3 patterns, like Figure 1 of the assignment). `P` + a
pattern draws it in the shortest cases that contain it.

**Beam table for the paper.** After step 1 and step 4:

```bash
python beam_table.py
```

reruns only SUBDUE (beam 4, 10, 20) on the saved instance graphs and writes
`output/beam_table/` - see *Beam table* below.

**Reproducibility.** pm4py's Inductive Miner iterates over Python sets, whose
iteration order is randomized per process unless the hash seed is fixed. Set
`PYTHONHASHSEED=0` before running `python main.py` if you need two runs of
step 1 to discover byte-identical Petri nets (the `.pnml` files will still
differ in the random ids pm4py gives to invisible transitions; the net
itself is the same).

## Current pipeline (`main.py`)

This is the pipeline described under *Running* above: the same three things
(model discovery + BIG instance graphs, pattern mining, evaluation) as an
earlier, more elaborate pipeline this project started from, now consolidated
into a single `main.py` with an interactive menu. That earlier pipeline is
kept, archived, under `OLD/` - see *Archived implementation* further down.

`main.py` is organized as one small class per pipeline step
(`InstanceGraphStep`, `PatternMiningStep`, `EvaluationStep`,
`SyntheticValidationStep`), all implementing
the same `PipelineStep` interface (`output_exists`, `ask_parameters`, `run`),
driven by a `Pipeline` class that prints the menu and dispatches to whichever
step the user picks. A step's adjustable values are declared as a list of
`Parameter` objects (question, explanation, suggested default, type), so
adding or changing a parameter does not touch the menu/prompting code.

| File / folder | What it does |
|------|---------------|
| `main.py` | The single entry point described above: `InstanceGraphStep`, `PatternMiningStep`, `EvaluationStep`, `SyntheticValidationStep`, and the `Pipeline` menu that runs them. `InstanceGraphStep` and `PatternMiningStep` take their input log / output folder as constructor arguments (defaults: the BPI paths), which is how step 4 reuses them. |
| `figures.py` | Figures of one chosen case (trace, instance graph, patterns) and of one pattern, from saved results. |
| `beam_table.py` | The beam width comparison (Table 6 of the reference paper), from saved instance graphs. |
| `README_group.md` | For the group: why each choice was made, the results of the final run, which figures/tables to use in the paper, and the limitations. |
| `BIG.py` | The course's BIG library (alignment-based instance graph construction and repair). Not in git (assignment material), but present locally. See *BIG.py performance work* below for the changes made to it. |
| `data/` | Input logs, e.g. `BPI2017Denied(3).xes` (full log) and `BPI2017Denied_10pct.xes` (10% sample used for evaluation). |
| `data/synthetic/` | The hand-made synthetic log (`synthetic_log.csv`) and its gold standard (`synthetic_gold_standard.csv`), explained in `data/synthetic/README.md`. |
| `output/` | Generated results: `instance graphs/` (relabeled log, Petri net, BIG's raw `.g` output, the pickled graphs, the resource→role mapping, the generation settings), `patterns/` (SUBDUE's patterns as CSV *and* as a pickle of the native SUBDUE objects, trace × pattern matrices, heatmap, pattern figures - see *Pattern statistics* below), `synthetic validation/` (step 4), `figures/` (`figures.py`), `beam_table/` (`beam_table.py`), `evaluation/` (alignment fitness summaries and per-trace CSVs, plus `pattern_evaluation/` - see *Evaluation* below). |
| `subdue/` | SUBDUE v1.4 (Python), unmodified, used by `PatternMiningStep`. |

### Pattern statistics (`PatternMiningStep`)

`output/patterns/patterns.csv` has one row per SUBDUE pattern: `edges`,
`FREQ` (SUBDUE's instances), `traces`/`REP` (cases with a SUBDUE instance),
`support`/`support_pct` (cases in which the pattern occurs, see below),
`subdue_value`, the `values` (roles) involved and a readable `description`
(`A -> B; B -> C`).

SUBDUE is asked to report every pattern it finds in its search (it only uses
its `numBest` setting to trim that report, not in the search itself), and
step 2 keeps the best `num_best`. `subdue_search.json` records how many it
found (**Subs**), the share kept (**% top subs** = `num_best` / Subs) and the
run time, as in Table 6 of the reference paper.

SUBDUE only reports non-overlapping instances, and stops looking once it has
enough, so "has a SUBDUE instance" can miss cases that do contain the
pattern. The **trace × pattern matrix** (`trace_pattern_matrix.csv`, one row
per case id, one column per pattern, 1 = the pattern occurs in that case)
therefore checks every pattern against every instance graph directly
(label-preserving subgraph monomorphism, `contains_pattern`); `support` is its
column sum. The SUBDUE-instance version is kept as
`trace_pattern_matrix_subdue_instances.csv`. `trace_pattern_heatmap.png`
shows the most common pattern combinations and how many cases have each.

Graphs and patterns are drawn left to right in layers (parallel branches
above each other), each node showing activity and role, coloured by role
(the same colour for a role in every figure).

### Synthetic validation (`SyntheticValidationStep`, step 4)

The real log has no ground truth, so step 4 runs steps 1 and 2 on a small
hand-made log (30 loan applications, 4 departments) in which we put 5
organizational patterns ourselves; the gold standard comes from that design,
not from SUBDUE. Both files, and why each case contains which pattern, are
explained in [`data/synthetic/README.md`](data/synthetic/README.md).

On BPI 2017 the true roles are unknown, so a missing pattern there could be
caused by the role discovery or by BIG/SUBDUE. Step 4 therefore runs twice,
each in its own folder under `output/synthetic validation/`:

| Folder | Events labeled with | Tests |
|---|---|---|
| `eval1_known_roles/` | the known `department` (the roles are given) | Petri net, BIG and SUBDUE |
| `eval2_full_pipeline/` | the employee (`org:resource`), grouped into roles by pm4py role discovery, as on BPI 2017 | role discovery + Petri net, BIG and SUBDUE |
| `comparison/` | both side by side | where a gold pattern got lost |

In evaluation 2 each discovered role is mapped to the department most of its
events come from, and the labels are translated (`Decide_Role_1` →
`Decide_Credit`) before scoring; `role_discovery.csv` shows every employee
with their department, discovered role and that role's department. Each
evaluation is scored at three levels:

| Level | Question | Output |
|---|---|---|
| a | Are the gold patterns in the instance graphs at all (Petri net + BIG, no SUBDUE)? | `gold_in_graphs.csv` |
| b | Do SUBDUE's patterns match the gold patterns? Precision, recall, F1, precision@k, with *containment* (headline: the SUBDUE pattern contains the gold pattern, or is contained in it with ≥ 2 edges) and *exact* matching (same labeled graph); plus edge-level precision/recall | `pattern_matching.csv` |
| c | For each gold pattern, is its best-matching SUBDUE pattern found in the right cases? | `gold_cases.csv` |

Each evaluation's `summary.json` has all scores (plus COV/DIV, Subs and,
for evaluation 2, the role discovery scores); `gold/G*.png` are the gold
patterns. `comparison/comparison.csv` has one row per gold pattern with both
evaluations' scores and a `diagnosis`: *found in both*, *lost by role
discovery* (found in 1, not in 2), *missed by SUBDUE* (in the instance graphs
but in no top pattern), or *not (fully) in the instance graphs* (Petri net /
BIG). `summary_comparison.csv` has the overall scores of both, and
`comparison.png` the level c F1 per gold pattern.

### Beam table (`beam_table.py`)

Table 6 of the reference paper, for beam 4, 10 and 20, on three settings:
the synthetic log with known roles, with discovered roles, and BPI 2017. It
reruns only SUBDUE (1 iteration, top 20 patterns, minimum pattern size as in
the step the graphs come from) on the saved instance graphs. Columns: `subs`
(every pattern SUBDUE found), `top_subs_pct` (20 / Subs), `COV_pct`, `DIV`
(× 100, the paper's scale), `REP_first_10` / `REP_all` (average REP of the
first 10 and of all 20 top patterns), `seconds`; for the synthetic settings
also containment precision/recall/F1 against the gold standard and the gold
patterns missed. Output: `output/beam_table/beam_table.csv` (all),
`table_<setting>.csv`, and `beam_table.tex` for the paper.

Our top list is always the best 20 patterns, so *% top subs* is 20 / Subs;
in the paper the number of top patterns differs per beam width, so that
column is comparable in spirit, not in exact definition.

### Evaluation (`EvaluationStep`)

Step 3 runs two independent checks, both written under `output/evaluation/`:

1. **Alignment of the role-based log against the Petri net and the instance
   graphs** (`run_alignment_evaluation`): the chosen log is relabeled the
   same way step 1 relabeled the training log (roles + lifecycle collapse,
   read back from `output/instance graphs/generation_settings.json` and
   `resource_roles.csv`), then compared against the saved Petri net (PM4Py
   alignments: cost, fitness, visited states) and against the saved instance
   graphs (edit distance between the trace's labels and the graph's
   topological event order, since instance graphs have no standard PM4Py
   alignment implementation). Written to `summary.json`,
   `petri_net_alignments.csv`, `instance_graph_alignments.csv`.

   The saved instance graphs carry no case id of their own, only their
   position in the *full* log they were built from; matching them against a
   log that only *samples* some cases (like the 10% evaluation log) is done
   by looking each trace's case id up in that full log first
   (`graph_index_by_case_id`), not by assuming the two line up index-for-index.

2. **Pattern evaluation** (`run_pattern_evaluation`): FREQ/REP/COV/DIV, a
   trace-pattern matrix and visualizations, computed on the *real* instance
   graphs (step 1's pickle) and the *real* discovered patterns (step 2's
   `patterns.pkl` - the native SUBDUE pattern objects, not just the CSV
   summary, so coverage/diversity can be computed from their actual
   instances). Petri-net alignment/fitness of these same traces is already
   covered by the alignment check above, so it is not repeated here. Written
   to `output/evaluation/pattern_evaluation/`:
   - `patterns.csv` / `trace_pattern_matrix.csv`: **FREQ** (instances per
     pattern) and **REP** (% of traces containing it), and the trace ×
     pattern matrix, from `PatternMiningStep.pattern_statistics` (the same
     method step 2 itself uses for its own `output/patterns/`).
   - `summary.json`: **COV** (share of all edges, across every instance
     graph, covered by at least one pattern instance) and **DIV** (average
     pairwise dissimilarity - 1 minus Jaccard similarity of activity sets -
     between the discovered patterns), from `EvaluationStep.pattern_metrics`.
   - `P*.png` / `instance_graph_*.png`: every discovered pattern and a few
     individual instance graphs, drawn with `PatternMiningStep.draw_graph`
     (activity/role labels, directed edges, FREQ/REP/value in the title).

### Roles and lifecycle collapse

`InstanceGraphStep` builds its labels in two steps, in this order (each
switched on/off by its own parameter when you run step 1, both suggested on):

1. **Roles.** pm4py's role discovery (Burattin, Sperduti & Veluscek, 2013;
   threshold adjustable, suggested 0.65) groups activities by the resources
   that perform them. Every resource gets its *dominant role*, the role in
   which it performs most of its events; `Role_1` has the most events. The
   mapping is saved to `output/instance graphs/resource_roles.csv`.
2. **Lifecycle collapse.** The work items carry their lifecycle step in the
   name (`W-Validate-application-start`, `-suspend`, `-resume`, ...). The step
   is removed, and directly repeated events with the same label (same activity
   and same role) within a case are merged into one. A role change inside a
   work item is a handover and is kept.

On the full log, with both on, this gives 106 labels instead of 3,338 (134
resources in 8 roles, 88,638 of 124,866 events kept, all 3,093 cases), so the
Petri net is much smaller and BIG's alignments much faster. The choices made
for a given run are saved to `output/instance graphs/generation_settings.json`
so `EvaluationStep` can relabel its own log the exact same way for a fair
comparison.

### BIG.py performance work

`BIG.py` processes every trace of a log (alignment + instance-graph
construction + repair), which is slow on the full BPI 2017 log — some traces
took 45+ minutes. The algorithm itself was not changed; the following
functions were rewritten to compute the exact same result faster:

- **`extract_instance_graph`**: the original re-scanned the whole window
  between every pair of events to decide if an edge should exist, which is
  O(n³) in the trace length. The two conditions it checks only ever depend on
  the *nearest* causal successor of the source event and *nearest* causal
  predecessor of the target event, so both can be found with a single linear
  pass per trace (tracking, per activity label, the most recently seen
  position) instead of rescanning — O(n) instead of O(n³). Verified
  byte-identical output against the original on 2000 randomized trace/causal-
  relation combinations.
- **`build_causal_maps`** (new): precomputes label → successor/predecessor
  label lookup sets once per log, instead of the original's `(a, b) in cr`
  linear scan of a flat list on every single pair check.
- **`is_path`**: used during insertion repair, this recursed without
  memoization and did `(a, b) in W` as an O(|W|) linear scan of the edge list
  on every recursive step. For traces with several insertions through
  parallel/diamond-shaped parts of the graph, the same sub-paths were
  re-explored repeatedly. Now builds an adjacency map once (O(1) lookups) and
  memoizes `is_path(a, b)` results, plus a visiting-set guard against infinite
  recursion if `W` were ever cyclic (the original had no such guard, but never
  hit a cycle in practice since edges always run from an earlier to a later
  trace position). Verified identical output (including the original's
  quirky "last successful branch wins" behavior) against 3000 randomized DAG
  structures.
- **Variant cache** (new, in `big()`): the alignment + repair pipeline for a
  trace depends only on its sequence of activity labels, not on case id,
  timestamp or resource — so two traces with the same activity sequence
  ("variant") always produce the identical instance graph. `big()` now caches
  the computed graph per variant and skips the expensive alignment + repair
  work entirely on repeats, which matters a lot on logs like BPI 2017 where
  many cases share the same path. The end-of-run log line reports
  `cache_hits/total_traces` so you can see how much this helped on a given
  log.

## Decisions and adaptations from the original approach

Why the implementation looks like it does, where that differs from a literal
reading of the assignment/paper or from an earlier version of this project:

| Decision / adaptation | Why |
|---|---|
| Resources grouped into roles (pm4py role discovery) instead of using raw `org:resource` values | `org:resource` alone has 134 distinct values, producing thousands of distinct activity-resource labels; that makes both the Inductive Miner and BIG slow and fragments SUBDUE's pattern search. Grouping into roles is also what the assignment itself suggests. |
| Lifecycle steps of work items (`W-...-start/suspend/resume/complete/...`) collapsed into one event | BPI 2017 records every lifecycle transition as its own event; BIG's per-trace cost scales with trace length, so this is the single biggest lever on how long BIG takes, independent of any algorithmic speed-up. |
| `BIG.py`'s `extract_instance_graph` rewritten from O(n³) to O(n) in trace length | The original re-scanned the whole window between every pair of events; some traces on the full log took 45+ minutes. The algorithm's result is unchanged (verified on 2000 randomized cases) - only how it is computed. |
| `BIG.py`'s `is_path` made memoized and adjacency-map based | Unmemoized, it re-explored the same sub-paths exponentially on parallel/diamond-shaped sections during insertion repair. Verified identical output on 3000 randomized graphs. |
| `BIG.py` caches the computed instance graph per trace *variant* (sequence of activity labels) | The alignment + repair pipeline for a trace depends only on its activity sequence, not its case id/timestamp/resource. Many BPI 2017 traces share the same sequence, so repeats skip the expensive work entirely. |
| BIG parallelized with the standard library (`concurrent.futures.ProcessPoolExecutor`) instead of PySpark | Spark needed a JVM and a machine-specific, hard-coded `JAVA_HOME` path - exactly what the assignment explicitly forbids ("never use absolute paths ... no adjustments must be made when executed on another system"). `ProcessPoolExecutor` does the same chunked, independent-per-trace parallelization with only the standard library, so the project runs on any machine with just `pip install -r requirements.txt`. |
| Three separate scripts (`Instance Graph Mining.py`, `Pattern Mining.py`, `Alignment Evaluation.py`) merged into one `main.py` | The assignment requires "one main method to execute your code". A single entry point is also simpler to grade and to run. |
| Interactive, numbered/y-n terminal menu instead of `argparse` sub-commands | This project is run by a small team trying different parameters on slow steps, not deployed as a tool for strangers; a menu that explains each parameter inline (with a suggested default) is more discoverable than reading `--help` for every flag, at the cost of not being scriptable. The assignment allows "command line parameters **or** a YAML configuration file" for adjustable parameters; the interactive menu is this project's equivalent of that mechanism. |
| Two superseded experiment scripts (`Final Try.py`, `Final Try PM4Py.py`) removed | They were single-script prototypes that `Instance Graph Mining.py` / `Pattern Mining.py` / `Alignment Evaluation.py` (now `main.py`) fully replaced; keeping dead prototypes around only adds confusion about which code is actually run. |
| `requirements.txt` added at the project root | It was missing; the assignment explicitly requires it, and without it the exact dependency versions this project was built and evaluated against were not reproducible by someone else. |
| Every path derived from `Path(__file__).resolve().parent`, none hard-coded | The assignment explicitly forbids absolute paths and requires the code to run unmodified on another system. |
| The earlier, more elaborate `orgmining/` + `OLD/main.py` pipeline (CLI with 10 sub-commands, a gold-standard evaluator, a synthetic-log experiment harness, a plotting layer) kept archived under `OLD/` rather than deleted or merged in | That pipeline's extra machinery (evaluation against a gold standard, synthetic data with injected ground truth, report figures) answers "does the method work," which is valuable for the short paper, but is not needed to run the pipeline and was far larger than this project needs going forward (roughly 4,200 lines vs. `main.py`'s few hundred). Its results and reasoning are kept for the paper rather than thrown away. |
| Evaluation's FREQ/REP/COV/DIV/trace-pattern-matrix/visualizations computed on the real step 1/2 output, not a synthetic log | A synthetic-log version of this was tried first, but the point of evaluating "the generated instance graphs and patterns" is to evaluate what steps 1 and 2 actually produced on the real BPI 2017 log - a synthetic log answers a different question (whether the method *can* recover a known pattern at all, which needs labeled ground truth the real log doesn't have) and was dropped rather than mixed in. `PatternMiningStep` now also pickles the native SUBDUE pattern objects (`patterns.pkl`), not just their CSV summary, so the evaluation step can compute coverage/diversity from their actual instances without rerunning SUBDUE. |
| No reuse-the-last-run checkpoints ("found existing X, reuse it?") | Originally added so a slow step (Petri net discovery, BIG, SUBDUE) didn't have to be redone after every small tweak elsewhere, but it meant picking a step from the menu could still stop and ask further questions beyond its own parameters, including awkwardly in the middle of "run all steps". Removed in favor of a step always running fresh end to end once its parameters are set - simpler to reason about, and `output/` is already git-tracked so a previous run's results are not lost, just overwritten. |
| `output/evaluation/` renamed from `output/alignment_evaluation/` | Groups both evaluation checks (alignment and pattern recovery) under one clearly-named folder, as requested, instead of a name that only described the first one. |
| Instance-graph alignment now matches log traces to saved graphs by case id, not by raw index | The saved graphs carry no case id (only their position in the *full* log); comparing a *sample* log (e.g. the 10% evaluation log, 309 of 3,093 cases) against them index-for-index silently compared the wrong trace to the wrong graph whenever the sample wasn't an exact prefix of the full log in the same order. Looking each case up by id in the full log it was built from fixes this without needing to regenerate the saved graphs. |
| Step 1 shows every log attribute and asks which one to analyse, instead of always using `org:resource` | Assignment step 1 explicitly requires it ("show the user all the attributes ... allow them to select"). Grouping into roles stays available, but is suggested only for attributes with many values. |
| `_` and whitespace in activity names become `-` in the labels | So the first `_` of a label always separates activity and value (values such as `Role_4` contain `_` themselves), which the figures and the gold-standard matching rely on. BPI 2017's activities already use `-`, so its labels do not change. |
| BIG runs once per trace *variant* inside `main.py` (`InstanceGraphStep.run_big`), and `main.py` can drive the unchanged Canvas `BIG.py` (`run_canvas_big_chunk`) | BIG's result depends only on the label sequence, so this is exact; it halves the BIG work on BPI 2017 (1,423 variants for 3,093 traces) and keeps the pipeline runnable with the Canvas `BIG.py`, without relying on a locally modified copy. |
| Trace × pattern matrix by case id, filled by a subgraph check of each pattern in each instance graph (SUBDUE-instance version kept next to it) | The assignment's matrix is "1 if the pattern occurs in the trace"; SUBDUE's own instances are non-overlapping and incomplete, and graph indices are not application ids. |
| A separate synthetic validation step (4) with a hand-made log and gold standard, instead of synthetic data inside step 3 | Precision and recall need patterns whose presence is known independently of SUBDUE, which only a log we designed ourselves gives; kept separate so step 3 still evaluates the real BPI output only. The log is small (30 cases) so every case can be checked by hand. |
| Precision/recall reported with both *exact* and *containment* matching, containment as the headline | SUBDUE prefers large, well-compressing patterns that glue neighbouring work practices together; these are correct but never an exact match. Exact matching is reported too, to show that effect. |
| Defaults: Inductive Miner noise threshold 0.2 (was 0.4), SUBDUE beam width 10 (was 4) | Chosen by the team for the paper; `beam_table.py` reports beam 4 and 20 next to it, so the effect of the choice is visible. |
| Step 4 runs twice: known roles (`department`) and roles discovered by pm4py from `org:resource` | Separates errors of the role discovery from errors of BIG/SUBDUE, which cannot be told apart on BPI 2017 (true roles unknown). BPI 2017 stays the real-world application, without a gold standard. |
| SUBDUE reports every pattern it found; the top `num_best` are kept | Gives *Subs* and *% top subs* for the beam table without changing SUBDUE: `numBest` only trims its report. |
| Figures of chosen cases in a separate `figures.py` | Picking a good example case is an editorial choice; `figures.py` lists candidates and draws Figure-1-style panels from saved results without rerunning anything. |

## Archived implementation (`OLD/`)

Everything from here on documents the earlier, more elaborate `orgmining/` +
`OLD/main.py` pipeline that this project started from (see the table above
for why it was simplified into the current `main.py`). It is kept for
reference and because its evaluation results (gold standard matching,
synthetic logs) are still valid background for the short paper; it is not
part of what `main.py` runs. Run it, if at all, as `python OLD/main.py ...`
from the project root with the same virtual environment.

## Project structure

```
main.py                     the single entry point; one sub-command per step
orgmining/                  the code, one module per step
  config.py                 paths (derived, never absolute), XES column names, label format
  log_io.py                 read XES -> DataFrame, write DataFrame -> XES
  preprocessing.py          step 1: class EventLogPreprocessor
  roles.py                  step 1: class ResourceRoleGrouper (resources -> roles)
  instance_graphs.py        step 2: PetriNetDiscoverer, BigRunner, GFileConverter,
                            InstanceGraphBuilder
  pattern_mining.py         step 3: PatternMiner, SubdueAccelerator (SUBDUE speed-ups)
  pattern_report.py         step 3: PatternReport (figures for the report)
  visualization.py          InstanceGraphViewer: print and plot instance graphs and patterns
  model_views.py            PetriNetRenderer, RoleActivityMatrix (checks by eye)
  evaluation.py             gold standard matching, precision/recall, frequent-path baseline
  synthetic.py              synthetic loan logs with known departments, patterns and noise
  synthetic_experiment.py   whole pipeline on synthetic logs, noise levels, parameter study
  validation.py             TraceValidator: one trace next to its instance graph
synthetic/                  generated synthetic logs (seeded), their gold standard and employees
gold_standard/              expected work practices for BPI 2017 (CSV, with the rationale)
paper/                      short paper (LaTeX), references and figures
subdue/                     SUBDUE v1.4 (Python), unmodified copy, MIT licence
tests/                      unit tests per step, on tiny hand-made logs and graphs
requirements.txt            pinned dependencies
BIG.py                      BIG library from Canvas (not in git, see above)
outputs/                    generated results (not in git)
  step1_preprocessing/<attribute>[_roles]/
  step2_instance_graphs/<step 1 folder>/
  step3_patterns/<step 2 folder>/        patterns, matrix, figures/
  figures/                  plots made with show-graph, show-roles, show-net
```

## Step 1 – preprocessing

`EventLogPreprocessor` (in `OLD/orgmining`) does the following:

1. **Load** the XES log as a DataFrame (one row per event). Trace attributes
   are copied to every event with the prefix `case:` (e.g. `case:LoanGoal`).
2. **Show all attributes** (`describe_attributes`, `print_attribute_table`):
   a numbered table with level (trace/event), number of distinct values, % of
   events that have a value, and examples. The activity, case id and
   timestamp are shown but cannot be selected.
3. **Ask the user** (`ask_for_attribute`) for a number or name, and keep
   asking until the answer is valid. `--attribute` skips the question.
4. **Ask whether to group the values into roles** (`ask_for_grouping`;
   `--grouping roles|none` skips the question), see below.
5. **Relabel** (`relabel_events`): `concept:name` becomes
   `<activity>_<value>`, e.g. `A-Submitted_User_1` or `A-Submitted_Role_4`.
   - Whitespace in labels is replaced by `-`, because BIG's `.g` output is
     space separated.
   - Events without a value get `UNKNOWN` (the log's own default), so no
     event is lost.
   - Activity, original value (the user) and label value (the role) are also
     kept as the columns `original_activity`, `original_attribute_value` and
     `selected_attribute_value`. The label alone cannot be split back, since
     values such as `User_1` contain `_` too.
6. **Save** to `outputs/step1_preprocessing/<attribute>[_roles]/`:

| File | Content |
|------|---------|
| `attributes_overview.csv` | the table shown to the user |
| `label_counts.csv` | every new label with activity, value and frequency |
| `roles.csv` | (roles only) every discovered role with its activities |
| `resource_roles.csv` | (roles only) the role assigned to every resource |
| `relabeled_log.xes` | the relabelled log, the input for step 2 |
| `summary.json` | chosen attribute and grouping, pm4py version, counts |

### Grouping resources into roles

With `org:resource` the log has 134 users and 3,338 distinct `activity_user`
labels: too slow for step 2 and too fragmented to find frequent patterns.
`ResourceRoleGrouper` (in `OLD/orgmining`) replaces each user by a role,
using pm4py's role discovery (Burattin, Sperduti & Veluscek, 2013):

1. Every activity starts as a role, described by how often each resource
   performs it.
2. The two roles with the most similar resource profiles are merged, as long
   as their similarity is above a threshold (`--roles-threshold`, default
   0.65, pm4py's default).
3. A resource can appear in several of the resulting roles; it is assigned
   its *dominant role*, the one in which it performs most of its events.
   (Using the role of the *activity* instead would make the label carry no
   information beyond the activity itself.)

### Results on the BPI 2017 log

3,093 traces, 124,866 events, 54 activities, 19 attributes.

| Attribute | Grouping | Values in labels | Labels after step 1 |
|-----------|----------|------------------|---------------------|
| `org:resource` | none | 134 users | 3,338 |
| `org:resource` | roles | 8 roles | 225 |
| `EventOrigin` | none | 3 | 54 |

The 8 roles are interpretable: for example `Role_1` (86 users) creates and
sends offers, `Role_2` (21 users) validates applications, `Role_3` (18 users)
denies applications and `Role_4` (2 users, including the system user
`User_1`) creates applications. `EventOrigin` gives exactly one label per
activity: it is determined by the activity, so it adds no organisational
information.

## Step 2 – instance graphs

`InstanceGraphBuilder` (in `OLD/orgmining`) does the following
on the step 1 output:

1. **Petri net** (`PetriNetDiscoverer`): the Inductive Miner on the
   relabelled log. As in the paper, the *infrequent* variant is used, with
   noise threshold 0.2 (ProM's default; `--noise-threshold`).
2. **BIG** (`BigRunner`): runs the course's `BIG.py` *unchanged*. BIG aligns
   every trace with the net, builds its instance graph and repairs it where
   the trace does not fit the net. It handles about 15 traces per minute per
   CPU core, so the log is cut into consecutive chunks, BIG runs on each
   chunk in its own process and folder (`--workers`), and the outputs are
   joined in the original order. Tested: the result is byte-for-byte the same
   as one BIG run on the whole log.
3. **Conversion** (`GFileConverter`): the `.g` text becomes one
   `networkx.DiGraph` per trace.
   - Every node gets a **unique global id**. BIG's local id (1, 2, ... in
     every graph) is kept as attribute `local_id`, and edges are translated
     through the same mapping, so all relations are preserved.
   - Node attributes: `label`, `activity`, `value` (the role), `local_id`.
     Graph attributes: `case_id`, `graph_index`.
   - The `.g` file does not name the traces; its graphs are in log order, so
     graph *i* gets the case id of trace *i*.
   - BIG occasionally writes the same edge twice (69 times in the example
     `BPI2017Denied.g`). An instance graph is a set of edges, so such an edge
     is kept once.
4. **Save** to `outputs/step2_instance_graphs/<step 1 folder>/`:

| File | Content |
|------|---------|
| `petri_net.pnml` | the discovered model |
| `instance_graphs.g` | BIG's raw output |
| `instance_graphs.pkl` | list of `networkx.DiGraph`, the input for step 3 |
| `instance_graphs_summary.csv` | per graph: nodes, edges, parallel branches, connected |
| `summary.json` | settings, timings and totals |

In Python:
`GFileConverter.load("outputs/step2_instance_graphs/org_resource_roles/instance_graphs.pkl")`
returns the list of graphs.

### Looking at instance graphs

`python OLD/main.py show-graph --index N` (or `--case <case id>`) prints a graph
as text (every node with its activity, role and successors) and saves a plot
to `outputs/figures/`. The plot (`InstanceGraphViewer` in
`OLD/orgmining`) needs no Graphviz: nodes are placed in layers by
their longest path from the start, so parallel branches are drawn above each
other, and long graphs wrap like a snake (left to right, then right to left).
The role is shown by the colour of the node border *and* a tag such as `R2`,
so the plot can also be read without colour.

### Results on the BPI 2017 log (roles)

| | Value |
|---|---|
| Petri net | 219 visible transitions (of 225 labels), 134 silent, 167 places |
| Instance graphs | 3,093 (one per trace), 124,866 nodes, 121,781 edges |
| Graphs with parallel branches | 0.3% |
| Graphs not connected | 0 |
| Run time (11 workers) | Petri net 72 s, BIG 49 min |

Almost every instance graph is a sequence, because the discovered net has only
one AND-split. This is **not caused by the roles**: pm4py's Inductive Miner
also finds only one AND-split on the original activities (no roles), at every
noise threshold from 0.0 to 1.0 (`python OLD/main.py show-net --log <log>
--describe-only`). The example net of the assignment
(`BPI2017Denied_petriNet.pnml`, activities only) has five AND-splits, and its
instance graphs (`BPI2017Denied.g`) have parallel branches in 99.3% of the
cases, so that net was made with a different tool or different settings (to
be checked). The paper reports mostly sequential graphs on its real-life log
too (12.5% parallel).

## Step 3 – behavioral patterns

`PatternMiner` (in `OLD/orgmining`) does the following on the
step 2 output:

1. **SUBDUE input**: all instance graphs become one disconnected graph for
   SUBDUE. Vertices are matched on their label (`activity_role`); all edges
   get the label `next` and are explicitly directed. (SUBDUE's own networkx
   loader, `nx_subdue`, silently makes every edge undirected because of a bug,
   so it is not used.) Every vertex keeps its unique id from step 2, so every
   pattern instance can be traced back to its trace.
2. **SUBDUE** (`subdue`, the unmodified Python version from
   https://github.com/holderlb/Subdue) finds the subgraphs that best compress
   the graph: value = (instances − 1) × edges / edges of the graph, with
   non-overlapping instances. Settings (all on the command line):

| Option | Default | Meaning |
|---|---|---|
| `--beam` | 4 | beam width, as in the paper |
| `--min-size` / `--max-size` | 2 / 10 | pattern size in edges |
| `--num-best` | 20 | patterns reported per iteration |
| `--iterations` | 1 | >1: compress the graph with the best pattern and search again, which gives a hierarchy of patterns like Fig. 4 of the paper |
| `--limit` | auto | patterns SUBDUE extends; *auto* = every one-edge pattern once, plus `beam` per level up to `max-size` |

   *Why `--limit auto`:* SUBDUE starts from all one-edge patterns in the order
   of the edges, not ordered by value, and stops after extending `limit`
   patterns. A smaller limit makes the result depend on the arbitrary edge
   order.
3. **Statistics** per pattern (`patterns.csv`): number of instances
   (occurrence-based support, as in the paper), number and share of traces
   that contain it (transaction-based support), size, roles involved and a
   readable description. `trace_pattern_matrix.csv` has one row per trace and
   one column per pattern, with 1 if the pattern occurs in the trace.
4. **Report figures** (`python OLD/main.py pattern-report`, `PatternReport` in
   `OLD/orgmining`), in `outputs/step3_patterns/<run>/figures/`:
   every pattern drawn like the instance graphs, the support per pattern, the
   overlap between patterns (share of traces in common) and the handover of
   work between roles over all instance graphs.

### Performance

SUBDUE compares candidate patterns pairwise: every edge with every other
edge, and every extended instance with every other one. On the 121,781 edges
of the BPI 2017 graphs that does not finish in reasonable time.
`SubdueAccelerator` replaces three of SUBDUE's helper functions at run time
by versions that give **exactly the same result**:

1. one-edge patterns are first grouped by their labels, because only edges
   with the same labels can match;
2. extended instances are grouped by a fingerprint (vertex labels with
   degree, edge labels) that every pair of matching graphs shares, and their
   graphs are built once instead of again for every comparison; SUBDUE's own
   `GraphMatch` still decides within a group;
3. the overlap test uses one set of the vertices already used instead of
   comparing with every accepted instance.

Groups are processed in the original order, so the patterns, their values
and their instances are identical. This is checked by
`OLD/tests` (random graphs, several settings, including
iterations) and on the real data (table below). `--original-subdue` runs
SUBDUE without the speed-ups.

Measured on the BPI 2017 instance graphs (default settings, max size 10;
the first N graphs; same machine, other jobs running):

| Instance graphs | Edges | Original SUBDUE | Accelerated | Speed-up | Same result |
|---|---|---|---|---|---|
| 250 | 9,898 | 23.6 s | 11.0 s | 2.1× | yes |
| 500 | 19,659 | 24.4 s | 11.5 s | 2.1× | yes |
| 1,000 | 39,221 | 282.4 s | 63.2 s | 4.5× | yes |
| 3,093 (all) | 121,781 | not run | 142.7 s | | |

The speed-up grows with the size of the input, because the original's
pairwise comparisons grow quadratically.

### Results on the BPI 2017 log (roles)

Single run (`mine-patterns`, 20 best patterns, 2.4 minutes): the best
patterns are all overlapping variants of the same sequence (in 54-80% of the
traces), because SUBDUE's beam search keeps refining one region of the graph.

Hierarchical run (`--iterations 10 --num-best 3`, 10 minutes): after every
iteration the best pattern is compressed, so every iteration finds a new part
of the process. Best pattern per iteration:

| Pattern | What it shows | Edges | Roles | Traces |
|---|---|---|---|---|
| P1.1 | Role_1 calls after the offer, Role_2 takes over and validates | 10 | Role_1, Role_2 | 1,883 (61%) |
| P2.1 | Role_4 registers the application, Role_1 continues it | 7 | Role_1, Role_4 | 1,394 (45%) |
| P3.1 | Role_1 accepts, creates and sends the offer | 3 | Role_1 | 2,522 (82%) |
| P4.1 | Role_1 calls for incomplete files, Role_2 takes over and validates | 6 | Role_1, Role_2 | 698 (23%) |
| P5.1 | Role_2 starts the validation | 3 | Role_2 | 1,035 (33%) |
| P6.1 | Role_1 completes the application (concept) | 2 | Role_1 | 1,252 (40%) |
| P7.1 | Role_3 denies, the offer is refused, the case ends | 3 | Role_3 | 954 (31%) |
| P8.1 | Role_3 refuses the offer and aborts the validation | 2 | Role_3 | 1,164 (38%) |
| P9.1 | Role_1 suspends and resumes completing the application | 2 | Role_1 | 888 (29%) |
| P10.1 | Role_1 calls the customer after the offer | 2 | Role_1 | 1,131 (37%) |

Patterns with two roles show a **handover of work**: the offer team (Role_1)
hands cases over to the validation team (Role_2) after calling the customer,
and the intake (Role_4) hands over to Role_1. Over all instance graphs, most
work stays within a role (80-93% of the edges, `role_handover.png`); the main
handovers are Role_4 → Role_1 (16% of Role_4's edges), Role_5 → Role_3 (17%),
Role_2 → Role_3 (9%) and Role_1 → Role_2 (7%).


## Evaluation

### 1. Synthetic logs with a known gold standard (main evaluation)

A real log has no ground truth, so `OLD/orgmining` generates a
simplified loan process with four departments (Intake 3, Offer 6, Validation 4,
Decision 3 employees) and 500 cases, in which five work practices are
*injected* (`OLD/synthetic`):

| ID | Injected work practice |
|---|---|
| G1 | Intake registers and checks the application |
| G2 | Handover Intake -> Offer: call the customer and complete the application |
| G3 | Offer team creates and sends the offer |
| G4 | Validation checks documents and fraud **in parallel** (any order), then decision |
| G5 | Handover Decision -> Offer: deny, then notify the customer |

Noise: in 0, 10, 20 or 30% of the cases one random disturbance (an event done
by an employee of another department, an extra event, a missing event, or two
events swapped). `python OLD/main.py synthetic` runs the whole pipeline on every
log (roles, Inductive Miner, BIG, SUBDUE with 5 iterations), maps the discovered
roles to the departments via the employees, and compares the patterns with the
injected ones. The logs are seeded and stored in `OLD/synthetic`.

| Noise | Roles correct | Parallel graphs | Precision | Recall | F1 | Baseline F1 |
|---|---|---|---|---|---|---|
| 0% | 100% | 71% | 0.93 | 1.00 | 0.97 | 0.77 |
| 10-30% | 100% | 0% | 0.60 | 0.80 | 0.69 | 0.80 |

Without noise every practice is found and SUBDUE beats the frequent-path
baseline, which cannot represent parallel work. From 10% noise on, pm4py's
Inductive Miner no longer finds the parallel block (at any noise threshold
between 0 and 0.8), all instance graphs become sequences and G4 is lost; this
is the same effect as on BPI 2017.

**Parameter study** (`--sweep`, 10% noise; `outputs/synthetic/sweep.csv`): the
number of iterations matters most (1: F1 0.75, 3: 0.89, 5: 0.69, 10: 0.47; later
iterations add fragments). Beam width 2, 4 or 10 gives the same result on these
small graphs and only costs time; top-k roles 2, 3 or all give the same scores
(k = 2 merges two departments into `Other`).

### 2. BPI 2017

- **Validation of one instance graph** (`validate-trace`): for
  Application_1691306052 the graph has the same 33 events and labels as the
  trace, the right role for every event, and all 32 edges link consecutive
  events (`outputs/validation/`).
- **Expected work practices**: `OLD/gold_standard`
  lists 9 practices derived from the log description, the lifecycle order of
  the activities and the step 1 role table (written after seeing first
  results, so it is a secondary check). Matching as above; baseline: the most
  frequent label paths of 2, 3 and 4 edges.

| SUBDUE run | Patterns | Precision | Recall | F1 | SUBDUE time |
|---|---|---|---|---|---|
| 1 iteration, beam 4 | 20 | 1.00 | 0.33 | 0.50 | 2.4 min |
| 10 iterations, beam 4 | 30 | 0.63 | 0.89 | 0.74 | 10 min |
| 10 iterations, beam 10 | 30 | 0.77 | 0.89 | 0.82 | 13 min |
| 10 iterations, beam 20 | 30 | 0.87 | 1.00 | 0.93 | 16 min |
| Frequent paths, 3 / 4 edges | 30 | 0.60 / 0.73 | 0.89 | 0.72 / 0.80 | |

On this large graph the beam width does matter: beam 20 finds all 9 practices.

### Matching rules

- A gold pattern is *found* if a discovered pattern contains it (same labels,
  including the role, and all its edges).
- A discovered pattern is *correct* if it contains a gold pattern or is part
  of one.
- Precision = correct / discovered, recall = found / gold, plus F1 and the same
  on edge level (pairs of labels) as partial credit.

## Short paper

`OLD/paper` (course template, 5 pages including references),
`OLD/paper` and `OLD/paper`. In Overleaf: replace `main.tex` and
`literature.bib` and upload the `figures/` folder.

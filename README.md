# Mining Organizational Patterns (JM0211, group 5)

Implementation of the behavioral pattern mining approach of Diamantini, Genga &
Potena (2016), *Behavioral process mining for unstructured processes*, on the
BPI Challenge 2017 log of denied loan applications.

| Step | What |
|------|------|
| 1 | Preprocessing: show all attributes, let the user pick one, relabel every event as `activity_selectedAttribute`; resources grouped into roles, lifecycle steps collapsed |
| 2 | Inductive Miner Petri net + BIG instance graphs → networkx graphs with unique node ids |
| 3 | SUBDUE patterns (hierarchical), support, trace × pattern matrix, visualisations |
| 4 | Evaluation: synthetic logs with injected patterns and noise (gold standard), BPI checks, parameter study |

## Requirements

- **Python 3.9.** The assignment requires **pm4py 2.2.16** (needed for BIG),
  which does not run on newer Python versions.
- **`BIG.py`** from Canvas, unchanged, in the project root.
- Optional: the **Graphviz** program, only for `show-net` (drawing Petri nets).

## Installation

Run these commands in order, from the project root (Git Bash, macOS or Linux):

```bash
# 1. Create and activate a virtual environment with Python 3.9
python3.9 -m venv .venv            # Windows: py -3.9 -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
                                   # Windows PowerShell: .\.venv\Scripts\activate

# 2. Install the pinned dependencies
pip install -r requirements.txt

# 3. Put BIG.py from Canvas (unchanged) in the project root, next to main.py
```

`requirements.txt` pins pm4py 2.2.16 and its complete dependency tree, so
everyone gets exactly the same environment. Graphviz (optional) on Windows:
`winget install --id Graphviz.Graphviz -e`; macOS: `brew install graphviz`.

## Running

Run from the project root with the virtual environment active. These commands
produce all results, in this order (times on a laptop with 12 cores):

```bash
# Step 1: relabel events as <activity>_<role>, lifecycle collapsed       (~2 min)
python main.py preprocess --attribute org:resource --grouping roles

# Step 2: Petri net + BIG instance graphs                                (~5-10 min)
python main.py instance-graphs

# Step 3: SUBDUE, 10 iterations, support and trace x pattern matrix      (~5-15 min)
python main.py mine-patterns
python main.py pattern-report                  # figures of the patterns

# Evaluation on BPI 2017
python main.py validate-trace                  # one trace next to its instance graph
python main.py evaluate                        # expected work practices + baseline
python main.py show-roles                      # which role performs which activity
python main.py show-graph --index 0            # print and plot one instance graph
python main.py show-net                        # draw the Petri net (needs Graphviz)

# Evaluation on synthetic logs with a known gold standard                 (~3 min)
python main.py synthetic                       # noise 0 / 10 / 20 / 30 %
python main.py synthetic --noise 0.1 --sweep   # parameter study (~5 min)

# Unit tests                                                              (seconds)
python -m unittest discover tests -v
```

Without `--attribute` and `--grouping`, step 1 shows all attributes of the log
and asks on the command line which attribute to use and whether to group its
values into roles (as the assignment asks). All results are written to
`outputs/` (not in git). `python main.py <step> --help` lists every option.

Useful variations:

```bash
python main.py preprocess --keep-lifecycle             # keep lifecycle steps in the labels
python main.py preprocess --attribute org:resource --grouping roles --top-roles 4
                                                       # keep the 4 largest roles, rest 'Other'
python main.py instance-graphs --max-traces 100        # quick trial on the first 100 traces
python main.py instance-graphs --workers 4             # use fewer CPU cores
python main.py mine-patterns --beam 10                 # wider SUBDUE beam
python main.py mine-patterns --original-subdue         # SUBDUE without speed-ups (same result, slower)
python main.py convert-g data/BPI2017Denied.g          # only convert a BIG .g file
```

**Reproducibility.** pm4py's Inductive Miner iterates over Python sets, whose
order changes between runs unless the hash seed is fixed. `main.py` restarts
itself once with `PYTHONHASHSEED=0`, so two runs give identical results.

## Project structure

```
main.py                     the single entry point; one sub-command per step
orgmining/                  the code, one module per step
  config.py                 paths (derived, never absolute), XES column names
  log_io.py                 read XES -> DataFrame, write DataFrame -> XES
  preprocessing.py          step 1: EventLogPreprocessor (attributes, labels, lifecycle)
  roles.py                  step 1: ResourceRoleGrouper (resources -> roles)
  instance_graphs.py        step 2: PetriNetDiscoverer, BigRunner, GFileConverter,
                            InstanceGraphBuilder
  pattern_mining.py         step 3: PatternMiner, SubdueAccelerator
  pattern_report.py         step 3: figures of the patterns
  visualization.py          InstanceGraphViewer: print and plot graphs and patterns
  model_views.py            PetriNetRenderer, RoleActivityMatrix
  evaluation.py             gold standard matching, precision/recall, baseline
  synthetic.py              synthetic logs with known departments, patterns and noise
  synthetic_experiment.py   whole pipeline on synthetic logs, parameter study
  validation.py             TraceValidator: one trace next to its instance graph
tests/                      unit tests per step
data/                       BPI 2017 log, example BIG output and Petri net, log description
synthetic/                  generated synthetic logs (seeded) and their gold standard
gold_standard/              expected work practices for BPI 2017
subdue/                     SUBDUE v1.4 (Python), unmodified copy, MIT licence
paper/                      short paper (LaTeX), references and figures
requirements.txt            pinned dependencies
BIG.py                      from Canvas (not in git)
outputs/                    generated results (not in git)
```

## Step 1 – preprocessing

`EventLogPreprocessor` (`orgmining/preprocessing.py`):

1. Loads the XES log; trace attributes get the prefix `case:`.
2. Shows all attributes (level, number of values, coverage, examples) and asks
   which one to use (`--attribute` skips the question).
3. Optionally groups the values into **roles** (`--grouping roles`), with
   pm4py's role discovery (Burattin, Sperduti & Veluscek, 2013): activities
   with similar resource profiles are merged into roles while their similarity
   is above `--roles-threshold` (0.65), and every resource gets its *dominant
   role* (the one with most of its events). `--top-roles k` keeps the k largest
   roles. Roles are discovered on the original activities.
4. Relabels every event as `<activity>_<value>`, e.g. `A-Submitted_Role_4`.
   Whitespace becomes `-` (BIG's output is space separated); missing values
   become `UNKNOWN`.
5. **Collapses the lifecycle** (default; `--keep-lifecycle` turns it off): the
   work items (`W-`) carry their lifecycle step in the name
   (`W-Validate-application-start`, `-suspend`, `-resume`, ...; 7 steps). The
   step is removed, and directly repeated events with the *same* label (same
   activity and same role) are merged into one. A change of role inside a work
   item is a handover and is kept.

Output in `outputs/step1_preprocessing/<attribute>[_roles]/`: the attribute
overview, label counts, roles and the role of every resource, the relabelled
log (input of step 2) and `summary.json`.

Why roles and lifecycle collapsing: with every user as a separate label the
log has 3,338 labels, the Inductive Miner builds a net with >1,300 transitions
and BIG's alignments take up to an hour per trace. With roles and a collapsed
lifecycle there are about 100 labels, a net of about 100 transitions and BIG
needs about a second per trace.

## Step 2 – instance graphs

`InstanceGraphBuilder` (`orgmining/instance_graphs.py`):

1. Discovers a Petri net with the infrequent Inductive Miner (noise threshold
   0.2, ProM's default as in the paper; `--noise-threshold`).
2. Runs the **unchanged** `BIG.py` from Canvas. BIG treats every trace
   independently, so the log is cut into consecutive chunks that run in
   parallel processes (`--workers`); the outputs are joined in the original
   order, which gives the same `.g` file as one run on the whole log.
3. Converts BIG's `.g` text into one `networkx.DiGraph` per trace. Every node
   gets a unique global id (BIG's local id is kept as `local_id`), edges are
   translated through the same mapping, and every graph gets its case id.

Output in `outputs/step2_instance_graphs/<step 1 folder>/`: Petri net, BIG's
`.g` file, `instance_graphs.pkl` (input of step 3), a summary per graph and
`summary.json`.

## Step 3 – behavioral patterns

`PatternMiner` (`orgmining/pattern_mining.py`):

1. All instance graphs form one disconnected, directed graph for SUBDUE;
   vertices are matched on their label.
2. SUBDUE (`subdue/`, unmodified, https://github.com/holderlb/Subdue) finds
   the subgraphs that best compress the graph. With 10 iterations (default)
   the best pattern is compressed after every iteration, so later iterations
   find other parts of the process (the pattern hierarchy of the paper).
   Options: `--beam` (4), `--iterations` (10), `--num-best` (3 per iteration),
   `--min-size`/`--max-size` (2/10 edges), `--limit` (auto: every one-edge
   pattern is extended, so the result does not depend on the edge order).
3. `SubdueAccelerator` replaces three quadratic SUBDUE helper functions by
   versions that group candidates first; the patterns, values and instances
   are identical (tested in `tests/test_pattern_mining.py`).
4. Per pattern: number of instances (occurrence-based support), number and
   share of traces that contain it, roles and a description
   (`patterns.csv`), and `trace_pattern_matrix.csv` (traces × patterns, 1 if
   the pattern occurs in the trace). `pattern-report` draws every pattern, the
   support, the overlap between patterns and the handovers between roles.

## Evaluation

**Synthetic logs (gold standard).** `orgmining/synthetic.py` generates a
loan process with four departments (Intake, Offer, Validation, Decision; 16
employees) and 500 cases, in which five work practices are injected
(`synthetic/gold_standard.csv`): two handovers between departments and one with
parallel work. Noise: in 0, 10, 20 or 30% of the cases one disturbance (an
event by an employee of another department, an extra or missing event, or two
events swapped). `python main.py synthetic` runs the whole pipeline on every
log, maps the discovered roles to the departments via the employees, and
computes precision, recall and F1 against the injected patterns, also for a
frequent-path baseline. `--sweep` varies top-k roles, beam width and
iterations.

**BPI 2017.**
- `validate-trace` puts one trace next to its instance graph and checks the
  labels, the roles and the edges.
- `evaluate` compares the patterns with 9 expected work practices
  (`gold_standard/bpi2017_org_resource_roles.csv`), derived from the log
  description, the order of the activities and the role table of step 1, with
  the lifecycle collapsed in the same way as in step 1
  (`..._lifecycle.csv` is the version for `--keep-lifecycle`).

Matching: a gold pattern is *found* if a discovered pattern contains it (same
labels and all its edges); a discovered pattern is *correct* if it contains a
gold pattern or is part of one. Precision = correct / discovered, recall =
found / gold; also F1 and the same on edge level.

## Short paper

`paper/short_paper.tex` (course template), `paper/literature.bib` and
`paper/figures/`. In Overleaf: replace `main.tex` and `literature.bib` and
upload `figures/`.

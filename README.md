# Mining Organizational Patterns (JM0211, group 5)

Implementation of the behavioral pattern mining approach of Diamantini, Genga &
Potena (2016), *Behavioral process mining for unstructured processes*, on the
BPI Challenge 2017 (denied applications) log.

| Step | What | Status |
|------|------|--------|
| 1 | Preprocessing: relabel every event as `activity_selectedAttribute`, optionally grouping resources into roles | done |
| 2 | Inductive Miner Petri net + BIG instance graphs → networkx | done |
| 3 | SUBDUE patterns, support, trace × pattern matrix, visualisation | done |
| 4 | Evaluation: precision / recall against a hand-made gold standard | to do |

## Requirements

- **Python 3.9.** The assignment requires **pm4py 2.2.16** (needed for BIG),
  and that version does not run on newer Python versions.
- The assignment material from Canvas (see *Add the assignment material*
  below). It is too large for git, so it is not in this repository.

## Installation

Run these commands in order, from a terminal (Git Bash, macOS or Linux):

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
```

`requirements.txt` pins pm4py 2.2.16 and its complete dependency tree, so
everyone gets exactly the same environment.

### Add the assignment material

Download the assignment folder from Canvas and place it in the project root
under exactly this name, together with `BIG.py`:

```
process-mining-g5/
├── BIG.py                                          BIG library (Canvas)
└── datasets_group5_mining_organizational_patterns/
    ├── BPI2017Denied(3).xes                        the event log (input of step 1)
    ├── BPI2017Denied.g                             example BIG output
    ├── BPI2017Denied_petriNet.pnml                 example Petri net
    └── *.pdf                                       assignment, log description, paper
```

## Running

Always run from the project root with the virtual environment active. These
commands reproduce all results, in this order:

```bash
# Step 1: relabel events as <activity>_<role of org:resource>   (about 2 minutes)
python main.py preprocess --attribute org:resource --grouping roles

# Step 2: Petri net + BIG instance graphs on the step 1 output   (about 1 hour)
python main.py instance-graphs

# Step 3: SUBDUE patterns, support, trace x pattern matrix        (about 2.5 minutes)
python main.py mine-patterns
python main.py pattern-report                                   # figures for the report

# Step 3, hierarchical (10 SUBDUE iterations, as in the paper)  (about 20 minutes)
python main.py mine-patterns --iterations 10 --num-best 3 --output-dir outputs/step3_patterns_hierarchy

# Unit tests (tiny logs, a few seconds)
python -m unittest discover tests -v
```

Useful variations:

```bash
python main.py preprocess                          # asks for the attribute and the grouping
python main.py instance-graphs --max-traces 50     # quick trial on the first 50 traces
python main.py instance-graphs --workers 4         # use fewer CPU cores
python main.py mine-patterns --max-graphs 300      # quick trial on the first 300 graphs
python main.py mine-patterns --original-subdue     # SUBDUE without speed-ups (same result, slow)
python main.py show-graph --index 0                # print the first instance graph and plot it
python main.py show-roles                          # heatmap: which role does which activity
python main.py show-net --describe-only            # size and parallel constructs of the net
python main.py show-net                            # draw the net (needs Graphviz, see below)
python main.py show-graph --case Application_1691306052 --output graph.svg
python main.py convert-g datasets_group5_mining_organizational_patterns/BPI2017Denied.g
                                                   # only convert an existing BIG .g file
python main.py preprocess --help                   # all options of a step
```

Results are written to `outputs/` (not in git; re-create them with the
commands above).

`show-net` draws Petri nets with pm4py, which needs the Graphviz *program*
(`pip install graphviz` only installs the Python wrapper). On Windows:
`winget install --id Graphviz.Graphviz -e`, then open a new terminal.

**Reproducibility.** pm4py's Inductive Miner iterates over Python sets, whose
order changes between runs unless the hash seed is fixed. `main.py` therefore
restarts itself once with `PYTHONHASHSEED=0`, so that two runs give identical
instance graphs. (The `.pnml` files still differ in the random ids pm4py gives
to invisible transitions; the net itself is the same.)

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

`EventLogPreprocessor` (in `orgmining/preprocessing.py`) does the following:

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
`ResourceRoleGrouper` (in `orgmining/roles.py`) replaces each user by a role,
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

`InstanceGraphBuilder` (in `orgmining/instance_graphs.py`) does the following
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

`python main.py show-graph --index N` (or `--case <case id>`) prints a graph
as text (every node with its activity, role and successors) and saves a plot
to `outputs/figures/`. The plot (`InstanceGraphViewer` in
`orgmining/visualization.py`) needs no Graphviz: nodes are placed in layers by
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
noise threshold from 0.0 to 1.0 (`python main.py show-net --log <log>
--describe-only`). The example net of the assignment
(`BPI2017Denied_petriNet.pnml`, activities only) has five AND-splits, and its
instance graphs (`BPI2017Denied.g`) have parallel branches in 99.3% of the
cases, so that net was made with a different tool or different settings (to
be checked). The paper reports mostly sequential graphs on its real-life log
too (12.5% parallel).

## Step 3 – behavioral patterns

`PatternMiner` (in `orgmining/pattern_mining.py`) does the following on the
step 2 output:

1. **SUBDUE input**: all instance graphs become one disconnected graph for
   SUBDUE. Vertices are matched on their label (`activity_role`); all edges
   get the label `next` and are explicitly directed. (SUBDUE's own networkx
   loader, `nx_subdue`, silently makes every edge undirected because of a bug,
   so it is not used.) Every vertex keeps its unique id from step 2, so every
   pattern instance can be traced back to its trace.
2. **SUBDUE** (`subdue/`, the unmodified Python version from
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
4. **Report figures** (`python main.py pattern-report`, `PatternReport` in
   `orgmining/pattern_report.py`), in `outputs/step3_patterns/<run>/figures/`:
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
`tests/test_pattern_mining.py` (random graphs, several settings, including
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

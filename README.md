# Mining Organizational Patterns (JM0211, group 5)

Implementation of the behavioral pattern mining approach of Diamantini, Genga &
Potena (2016), *Behavioral process mining for unstructured processes*, on the
BPI Challenge 2017 (denied applications) log.

| Step | What | Status |
|------|------|--------|
| 1 | Preprocessing: relabel every event as `activity_selectedAttribute`, optionally grouping resources into roles | done |
| 2 | Inductive Miner Petri net + BIG instance graphs → networkx | done |
| 3 | SUBDUE patterns, support, trace × pattern matrix, visualisation | to do |
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

# Unit tests (tiny logs, a few seconds)
python -m unittest discover tests -v
```

Useful variations:

```bash
python main.py preprocess                          # asks for the attribute and the grouping
python main.py instance-graphs --max-traces 50     # quick trial on the first 50 traces
python main.py instance-graphs --workers 4         # use fewer CPU cores
python main.py show-graph --index 0                # print the first instance graph and plot it
python main.py show-graph --case Application_1691306052 --output graph.svg
python main.py convert-g datasets_group5_mining_organizational_patterns/BPI2017Denied.g
                                                   # only convert an existing BIG .g file
python main.py preprocess --help                   # all options of a step
```

Results are written to `outputs/` (not in git; re-create them with the
commands above).

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
  visualization.py          InstanceGraphViewer: print and plot instance graphs
tests/                      unit tests per step, on tiny hand-made logs and graphs
requirements.txt            pinned dependencies
BIG.py                      BIG library from Canvas (not in git, see above)
outputs/                    generated results (not in git)
  step1_preprocessing/<attribute>[_roles]/
  step2_instance_graphs/<step 1 folder>/
  figures/                  plots made with show-graph
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

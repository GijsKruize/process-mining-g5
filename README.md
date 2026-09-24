# Organizational Process Mining — JM0211 (Steps 1-3/4)

Steps 1-3 of the JM0211 "Mining Organizational Patterns" pipeline,
built with [pm4py](https://pm4py.fit.fraunhofer.de/) and
[networkx](https://networkx.org/):

1. **`preprocess.py`** — imports an XES event log, lets you interactively
   fuse an attribute (e.g. resource) into the activity label for
   resource-task assignment, and exports a relabelled log.
2. **`instance_graphs.py`** — discovers a Petri net from that log with the
   Inductive Miner, then builds one instance graph per trace using BIG's own
   algorithm (see [Step 2](#step-2-instance-graph-generation) below for why
   it runs natively rather than via the external tool), and converts the
   result into a list of `networkx.DiGraph` objects for the later SUBDUE
   subgraph-mining step.
3. **`pattern_mining.py`** — merges those instance graphs and mines
   recurring behavioral patterns from them with SUBDUE (vendored under
   `subdue/`; see [Step 3](#step-3-pattern-mining) below), reporting each
   pattern's support, a trace-pattern occurrence matrix, and a rendered
   visualization of a representative instance.

## Project structure

```
.
├── preprocess.py                # Step 1 script (entry point: main())
├── instance_graphs.py           # Step 2 script (entry point: main())
├── big_engine.py                # Step 2's native BIG algorithm (see "About BIG")
├── pattern_mining.py             # Step 3 script (entry point: main())
├── g_to_networkx.py             # Standalone .g -> networkx converter (any .g file, no pipeline needed)
├── inspect_graphs.py            # Renders pickled networkx graphs as PNGs for visual inspection
├── subdue/                      # Vendored SUBDUE (MIT licensed), see "Step 3"
├── config.yaml                  # Step 1 parameters
├── config_instance_graphs.yaml  # Step 2 parameters
├── config_pattern_mining.yaml   # Step 3 parameters
├── requirements.txt             # Runtime dependencies (pinned)
├── requirements-dev.txt         # + pytest/flake8, for testing and linting
├── data/                        # Put your input .xes file here (step 1 default input)
├── output/                      # All three scripts write their results here
├── datasets_group5_mining_organizational_patterns/
│   ├── BPI2017Denied(3).xes     # BPI Challenge 2017 log used for evaluation
│   └── BPI2017Denied.g          # Example BIG output, used as a parser fixture
└── tests/
    ├── generate_synthetic_log.py    # Builds a tiny synthetic .xes log
    ├── conftest.py
    ├── test_preprocess.py           # Step 1 test suite
    └── test_instance_graphs.py      # Step 2 test suite
```

All paths used by the scripts are **relative to the project root** (via
`pathlib.Path`, resolved against the current working directory), so no
changes are needed to run this on another machine — just clone/copy the
whole project folder and follow the steps below.

## Requirements

- Python 3.9 (pm4py 2.2.16 is pinned for compatibility with the BIG library
  used by step 2, and does not build on very recent Python interpreters —
  this project was built and tested with Python 3.9.25).
- macOS/Linux/Windows with `git` and Homebrew (or another way to install
  Python 3.9) available.
- For step 2's BIG call specifically: a Java runtime and the BIG tool
  itself, provided by the course (see [Step 2](#step-2-instance-graph-generation) below).

If you don't already have Python 3.9, install it first, e.g. on macOS:

```bash
brew install python@3.9
```

## Installation

Run the following commands in order from the project root:

```bash
# 1. Create an isolated virtual environment using Python 3.9
python3.9 -m venv .venv

# 2. Activate it
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Upgrade pip
pip install --upgrade pip

# 4. Install the pinned runtime dependencies
pip install -r requirements.txt
```

`requirements.txt` pins `pm4py==2.2.16` and PyYAML, plus the exact versions
of every transitive dependency, frozen from a clean install on Python
3.9.25, so the environment is reproducible on any machine.

To also run the test suite and linter, install the dev extras instead
(this includes everything in `requirements.txt`):

```bash
pip install -r requirements-dev.txt
```

## Step 1: preprocessing

### Configuration

Adjustable parameters live in `config.yaml`, not hard-coded in the script:

```yaml
input_path: data      # .xes file, or a directory containing exactly one .xes file
output_dir: output     # where relabeled_log.xes / .csv are written
n_examples: 3           # example values shown per attribute
top_n_labels: 10        # most frequent new labels printed after relabelling
```

Any value can be overridden per run with a matching command line flag
(`--output-dir`, `--n-examples`, `--top-n-labels`), or a different config
file via `--config path/to/other.yaml`, without editing the source code.

### Usage

```bash
python preprocess.py [INPUT_PATH] [--output-dir DIR] [--config FILE] \
                      [--n-examples N] [--top-n-labels N]
```

- `INPUT_PATH` (optional, positional) — overrides `input_path` from
  `config.yaml`. Can be an `.xes` file or a directory containing exactly
  one `.xes` file.

The BPI Challenge 2017 log used for evaluation lives in
`datasets_group5_mining_organizational_patterns/BPI2017Denied(3).xes`.
`data/BPI2017Denied(3).xes` is a symlink to it, so the default invocation
(using `config.yaml` as-is) works out of the box:

```bash
python preprocess.py
```

The script is interactive: it prints a log summary (traces, events,
distinct activities) and a numbered overview of every attribute (distinct
value count + example values), then asks you to:

1. Pick one attribute (by number or name — invalid input just re-prompts)
   to fuse with the activity name for resource-task assignment.
2. Choose how to handle events with a missing/empty value for that
   attribute (`drop` them, or relabel as `UNKNOWN`).

It then prints before/after activity-label statistics and exports the
result.

### Output

- `output/relabeled_log.xes` — the relabelled event log. Its activity
  (`concept:name`) is now `<original_activity>_<attribute_value>`; the
  original, un-fused activity is kept under the `original_activity`
  attribute (used by step 2).
- `output/relabeled_log.csv` — the same data as a flat table, for manual
  inspection.

### Code structure

`preprocess.py` is organized as small, independently testable classes, each
with a single responsibility:

- `PipelineConfig` — loads/validates parameters from `config.yaml`.
- `EventLogRepository` — reads XES → DataFrame and writes the result back
  out (XES + CSV).
- `LogReporter` — prints log/column/relabelling statistics.
- `AttributeSelector` — interactive attribute prompt with re-prompting.
- `MissingValueHandler` — counts and resolves missing values.
- `ActivityRelabeler` — sanitizes values and builds the new activity label.
- `PreprocessingPipeline` — orchestrates the above; its `run()` method is
  the full pipeline.

`main()` is the single entry point: it parses CLI arguments, builds a
`PipelineConfig`, and runs the pipeline. `instance_graphs.py` reuses
`EventLogRepository` directly instead of re-implementing log I/O.

## Step 2: instance graph generation

### About BIG

No BIG jar/binary was distributed for this course run. BIG is open source,
though: its GUI wrapper (Docker + Spark + Tkinter) and the algorithm behind
it are published by the same research group that set this assignment
(Diamantini, Genga, Mircoli, Potena) at
[a-mircoli/big-gui](https://github.com/a-mircoli/big-gui)
(`app/BIG2/BigSpark/newbig2.py`). That algorithm — align each trace against
the Petri net, derive the net's causal relation, build a provisional
instance graph, then repair it around the alignment's skip/insert steps —
does not actually need Spark; Spark there only fans per-trace work across a
cluster for very large logs.

`big_engine.py` ports that algorithm's core functions directly (same logic,
same `.g` output format), with the Spark driver, the Tkinter GUI, the
IPython/graphviz live preview, and BIG's hard-coded project paths removed —
none of that is needed to call the graph-construction algorithm itself as a
plain library function. `instance_graphs.py` uses it automatically as long
as `big_command` is unset in the config (the default). See `big_engine.py`'s
module docstring for the full provenance.

If you do have a real BIG deployment (e.g. the Docker/Spark GUI above) and
want to shell out to it instead, set `big_command`:

```yaml
big_command: "java -jar tools/BIG.jar {log} {petri_net} {output}"
```

`{log}`, `{petri_net}`, and `{output}` are substituted with the discovery
log, the discovered Petri net (PNML), and the path BIG should write its
`.g` file to; when set, this takes priority over the native engine.

Either way, the `.g` → `networkx` parser can also be exercised directly on
any pre-generated `.g` file — e.g. the example `BPI2017Denied.g` shipped
with the assignment — via `--parse-only`:

```bash
python instance_graphs.py --parse-only "datasets_group5_mining_organizational_patterns/BPI2017Denied.g"
```

### Why the Petri net uses plain activities

Inductive Miner discovery and the log handed to BIG use the event's
**`original_activity`** attribute (the plain activity, preserved by step
1) rather than the resource-fused `concept:name`. Two reasons:

- With thousands of distinct `<activity>_<resource>` combinations,
  Inductive Miner becomes impractically slow (confirmed: discovery on the
  full BPI2017 log did not finish in several minutes with the fused
  labels, versus ~2s with plain activities).
- BIG aligns the log against the Petri net's transition labels, so both
  must use the same activity values; the provided example
  `BPI2017Denied.g` was itself built this way ("only event activities are
  used as labels").

This is configurable (`activity_key` in the config, or `--activity-key`),
in case you want to experiment with the fused labels regardless.

### Configuration

```yaml
log_path: output/relabeled_log.xes   # step 1's output
output_dir: output                    # where all step 2 files are written
activity_key: original_activity       # see above
discovery_log_filename: discovery_log.xes
petri_net_filename: petri_net.pnml
graphs_filename: instance_graphs.g
parsed_graphs_filename: instance_graphs.pkl
big_command: null                     # set this once you have BIG
```

### Usage

```bash
python instance_graphs.py [--config FILE] [--log-path FILE] [--output-dir DIR] \
                           [--activity-key KEY] [--big-command CMD] \
                           [--force] [--parse-only G_FILE]
```

Full pipeline (works out of the box, no extra setup needed):

```bash
python instance_graphs.py
```

This discovers a Petri net from `output/relabeled_log.xes`, exports it,
runs BIG (the native engine by default, or the external tool if
`big_command` is configured), and parses the resulting `.g` output into
instance graphs — unless `output/instance_graphs.g` already exists, in
which case it's reused (pass `--force` to regenerate). Parse an existing
`.g` file directly, skipping discovery and BIG entirely:

```bash
python instance_graphs.py --parse-only path/to/file.g
```

### Output

- `output/discovery_log.xes` — the log actually handed to BIG (activity
  key swapped to `original_activity`).
- `output/petri_net.pnml` — the Inductive Miner's discovered Petri net.
- `output/instance_graphs.g` — BIG's raw textual output.
- `output/instance_graphs.pkl` — a pickled `List[networkx.DiGraph]`, one
  graph per trace, ready for the SUBDUE step. Each node has a **globally
  unique id** across the whole collection (BIG's local per-graph ids reset
  for every instance graph, so they are remapped rather than reused) plus
  `label` and `local_id` attributes; each edge has a `label` attribute.

### Code structure

- `InstanceGraphConfig` — loads/validates parameters from
  `config_instance_graphs.yaml`.
- `PetriNetDiscoverer` — runs the Inductive Miner and exports the result
  to PNML.
- `NativeBigEngine` — runs BIG's own algorithm (via `big_engine.py`)
  trace-by-trace and writes the same textual `.g` format BIG produces; used
  by default (see [About BIG](#about-big)).
- `BigRunner` — invokes an external BIG command as a subprocess; only used
  when `big_command` is explicitly configured.
- `InstanceGraphParser` — parses `.g` text into `networkx.DiGraph`
  objects, assigning globally unique node ids; also summarizes,
  pickles, and reloads results.
- `InstanceGraphPipeline` — orchestrates the above; its `run()` method is
  the full pipeline.

## Step 3: pattern mining

### About SUBDUE

The assignment specifies leveraging the
[SUBDUE](https://github.com/holderlb/Subdue) subgraph-mining algorithm.
Unlike BIG, SUBDUE's own repository is a complete, MIT-licensed, pure-Python
implementation with a `nx_subdue()` entry point built specifically to run
directly on a `networkx` graph — no external process, jar, or Docker
container needed. It's vendored under `subdue/` (`subdue/LICENSE` is its
original MIT license).

Two real bugs and one performance issue in the upstream code were found and
fixed while wiring it up (see the comments at each fix in `subdue/Graph.py`
and `subdue/Subdue.py` for details):

- `Graph.load_from_networkx` read `networkx_graph.is_directed` without
  calling it, so every edge from *any* networkx graph was silently treated
  as undirected — significant here, since edge direction encodes causal
  order in our instance graphs. Fixed, and verified with a test that
  forward- and reverse-direction edges are no longer merged into one
  pattern.
- The same function passed non-string node ids straight through, but the
  rest of the codebase assumes string ids (crashes in `print_vertex`).
  Fixed by stringifying on the way in; `pattern_mining.py` casts pattern
  results back to `int` to match our own node ids.
- `Subdue.GetInitialPatterns` compares every pair of single-edge graphs
  with `GraphMatch`, which is O(E²) — fine for one small graph, but
  prohibitive once many instance graphs are merged into one union graph
  (E in the hundreds of thousands for the full BPI2017Denied log). Since a
  length-1, non-temporal pattern's match is fully determined by its
  (source, edge, target) attributes, edges are now grouped into buckets by
  that signature first, turning the all-pairs comparison into a per-bucket
  one. Verified to produce byte-identical output to the original algorithm
  on a synthetic test case; only used for the non-temporal case (SUBDUE's
  `--temporal` option still uses the original algorithm).

### Why instance graphs are merged into one union graph

Step 2 guarantees every instance graph has globally unique node ids across
the whole collection. That means all instance graphs can be merged into a
single disjoint-union graph and mined in one SUBDUE pass: since there are no
edges between different traces, a discovered pattern's instances can never
span more than one original trace, so this is equivalent to mining each
trace separately, just faster. `pattern_mining.py`'s `UnionGraphBuilder`
does this and also returns a node id → trace index map, used to compute
support and the trace-pattern matrix.

### Configuration

```yaml
instance_graphs_path: output/instance_graphs.pkl   # step 2's output
output_dir: output
node_attributes: [label]   # what SUBDUE matches nodes on
edge_attributes: [label]   # what SUBDUE matches edges on
beam_width: 4
limit: 500        # SUBDUE's own default (0 -> |E|/2) is impractical here
min_size: 1
max_size: 8       # ditto (0 -> |E|/2); behavioral patterns are small motifs
num_best: 6
overlap: none
prune: false
value_based: false
iterations: 1      # see the comment in the YAML for why iterations > 1
                   #  needs extra care before this pipeline supports it
render_patterns: true
```

`limit` and `max_size` deliberately default away from SUBDUE's own `0` (=
`|E|/2`) defaults: once many traces are merged into one union graph, `|E|/2`
is tens of thousands of edges, and we're looking for small recurring
behavioral motifs (a handful of activities), not whole-trace-sized
subgraphs. Raise these if you want larger patterns and have the time to
spare — mining the full BPI2017Denied instance graphs (131,052 edges) with
the defaults above takes about 7 minutes on a laptop.

### Usage

```bash
python pattern_mining.py [--config FILE] [--instance-graphs-path FILE] \
                          [--output-dir DIR] [--num-best N] \
                          [--min-size N] [--max-size N] [--no-render]
```

```bash
python pattern_mining.py
```

### Output

- `output/patterns.pkl` — the raw discovered patterns: a list of patterns,
  each a list of instance dicts (`{'nodes': [...], 'edges': [(src, dst), ...]}`
  with our own global node ids).
- `output/pattern_stats.csv` — one row per pattern: `num_nodes`, `num_edges`
  (its size), `num_instances` (raw occurrence count, can exceed the number
  of traces if a pattern recurs within one trace), `support_count` (number
  of *distinct* traces containing it), `support_fraction`
  (`support_count` / total traces).
- `output/trace_pattern_matrix.csv` — the trace × pattern occurrence
  matrix the assignment asks for: rows are traces, columns are patterns,
  each cell is 1 if that pattern occurs at least once in that trace.
- `output/patterns/pattern_N.png` — a rendered representative instance of
  each pattern, plus a text summary (size, distinct activities, edges)
  printed to stdout for every pattern.

### Code structure

- `UnionGraphBuilder` — merges instance graphs into one graph for SUBDUE,
  tracking which trace each node came from.
- `PatternMiner` — thin wrapper around `nx_subdue()`; normalizes ids back
  to `int` afterward.
- `PatternStatistics` — support counts and the trace-pattern matrix.
- `PatternVisualizer` — text summaries and PNG rendering (networkx +
  matplotlib, `Agg` backend, no display needed).
- `PatternMiningPipeline` — orchestrates the above; its `run()` method is
  the full pipeline.

## Visually inspecting instance graphs

`inspect_graphs.py` renders any pickle of `List[networkx.DiGraph]` (step 2's
`output/instance_graphs.pkl`, or anything `g_to_networkx.py` produced) as
PNGs, laid out left-to-right by causal depth (topological generation) rather
than a generic force-directed layout, since instance graphs are DAGs and this
reads as "what can happen after what":

```bash
# List every graph in the file (index, size, first few activities)
python inspect_graphs.py output/instance_graphs.pkl --list

# Render one graph
python inspect_graphs.py output/instance_graphs.pkl --index 0

# Render several (capped at --max to avoid generating thousands of PNGs
# for a large collection by accident)
python inspect_graphs.py output/instance_graphs.pkl --all --max 10
```

Output goes to `output/graph_inspection/` by default.

## Tests

```bash
python -m pytest tests/ -v
```

`tests/generate_synthetic_log.py` builds a tiny in-memory log (5 traces, 6
distinct activities, 3 resources, one event with a missing resource) so
step 1's whole pipeline — including the missing-value branch — can be
validated without loading the full BPI 2017 log.

For step 2, `tests/data/sample_instance_graphs.g` is a genuine two-graph
excerpt of the provided `BPI2017Denied.g`, used to regression-test the
parser against BIG's real output format; `BigRunner` is tested against
trivial stand-in shell commands (e.g. `echo`/`cp`) rather than the real
BIG tool, and the end-to-end pipeline test stubs BIG the same way.

Step 3 (`pattern_mining.py`) does not have a pytest suite yet; it's been
validated ad hoc: against a small synthetic instance-graph set with a known
injected pattern (correct patterns, support, and matrix all came back
exactly as expected), against SUBDUE's own upstream example graph (matches
its documented output), and end-to-end against the full BPI2017Denied
instance graphs (3,093 traces, 131,052-edge union graph, ~7 minutes,
6 patterns with 62-70% support each). A proper test suite covering
`UnionGraphBuilder`, `PatternStatistics`, and the vendored SUBDUE fixes
would be a good addition.

Style can be checked with (`subdue/` is vendored third-party code and
deliberately excluded — its style is upstream's to fix, not ours):

```bash
python -m flake8 --max-line-length=99 preprocess.py instance_graphs.py big_engine.py \
    pattern_mining.py tests/*.py
```

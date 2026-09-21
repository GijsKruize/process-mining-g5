# Organizational Process Mining — JM0211 (Steps 1-2/4)

Steps 1 and 2 of the JM0211 "Mining Organizational Patterns" pipeline,
built with [pm4py](https://pm4py.fit.fraunhofer.de/) and
[networkx](https://networkx.org/):

1. **`preprocess.py`** — imports an XES event log, lets you interactively
   fuse an attribute (e.g. resource) into the activity label for
   resource-task assignment, and exports a relabelled log.
2. **`instance_graphs.py`** — discovers a Petri net from that log with the
   Inductive Miner, feeds it (with the log) to the external BIG library to
   build one instance graph per trace, and converts BIG's textual output
   into a list of `networkx.DiGraph` objects for the later SUBDUE
   subgraph-mining step.

## Project structure

```
.
├── preprocess.py                # Step 1 script (entry point: main())
├── instance_graphs.py           # Step 2 script (entry point: main())
├── config.yaml                  # Step 1 parameters
├── config_instance_graphs.yaml  # Step 2 parameters
├── requirements.txt             # Runtime dependencies (pinned)
├── requirements-dev.txt         # + pytest/flake8, for testing and linting
├── data/                        # Put your input .xes file here (step 1 default input)
├── output/                      # Both scripts write their results here
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

BIG is a tool **provided by the course**, not bundled with this project —
it is not available at the time of writing, so `instance_graphs.py` calls
it as a **configurable external command** rather than a hard-coded
integration. Once you have it (typically a `.jar`), point `big_command` in
`config_instance_graphs.yaml` at it:

```yaml
big_command: "java -jar tools/BIG.jar {log} {petri_net} {output}"
```

`{log}`, `{petri_net}`, and `{output}` are substituted with the discovery
log, the discovered Petri net (PNML), and the path BIG should write its
`.g` file to. Until then, the `.g` → `networkx` parser can be exercised
directly on any pre-generated `.g` file — e.g. the example
`BPI2017Denied.g` shipped with the assignment — via `--parse-only`:

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

Full pipeline (requires `big_command` to be configured):

```bash
python instance_graphs.py
```

This discovers a Petri net from `output/relabeled_log.xes`, exports it,
runs BIG, and parses its `.g` output into instance graphs — unless
`output/instance_graphs.g` already exists, in which case it's reused
(pass `--force` to regenerate). Parse an existing `.g` file directly,
skipping discovery and BIG entirely:

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
- `BigRunner` — invokes the configured BIG command as a subprocess.
- `InstanceGraphParser` — parses `.g` text into `networkx.DiGraph`
  objects, assigning globally unique node ids; also summarizes,
  pickles, and reloads results.
- `InstanceGraphPipeline` — orchestrates the above; its `run()` method is
  the full pipeline.

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

Style can be checked with:

```bash
python -m flake8 --max-line-length=99 preprocess.py instance_graphs.py tests/*.py
```

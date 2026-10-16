# Mining Organizational Patterns (JM0211, group 5)

Implementation of the behavioral pattern mining approach of Diamantini, Genga &
Potena (2016), *Behavioral process mining for unstructured processes*, on the
BPI Challenge 2017 (denied applications) log.

| Step | What | Status |
|------|------|--------|
| 1 | Preprocessing: relabel every event as `activity_selectedAttribute` | done |
| 2 | Inductive Miner Petri net + BIG instance graphs → networkx | to do |
| 3 | SUBDUE patterns, support, trace × pattern matrix, visualisation | to do |
| 4 | Evaluation: precision / recall against a hand-made gold standard | to do |

## Requirements

- **Python 3.9.** The assignment requires **pm4py 2.2.16** (needed for BIG),
  and that version does not run on newer Python versions.
- The assignment material from Canvas (see step 2 below). It is too large for
  git, so it is not in this repository.

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

Always run from the project root with the virtual environment active.

```bash
python main.py preprocess                             # shows all attributes, asks which one
python main.py preprocess --attribute org:resource    # same, without the question
python main.py preprocess --log path/to/other.xes     # another log (.xes or .xes.gz)
python main.py preprocess --help                      # all options

python -m unittest discover tests -v                  # unit tests (tiny log, a few seconds)
```

Results are written to `outputs/` (not in git; re-create them with the
commands above).

## Project structure

```
main.py                     the single entry point; one sub-command per step
orgmining/                  the code, one module per step
  config.py                 paths (derived, never absolute), XES column names, label format
  log_io.py                 read XES -> DataFrame, write DataFrame -> XES
  preprocessing.py          step 1: class EventLogPreprocessor
tests/
  test_preprocessing.py     unit tests for step 1 on a 5-event log
requirements.txt            pinned dependencies
outputs/                    generated results (not in git)
  step1_preprocessing/<attribute>/
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
4. **Relabel** (`relabel_events`): `concept:name` becomes
   `<activity>_<value>`, e.g. `A-Submitted_User_1`.
   - Whitespace in labels is replaced by `-`, because BIG's `.g` output is
     space separated.
   - Events without a value get `UNKNOWN` (the log's own default), so no
     event is lost.
   - The original activity and the value are also kept in the columns
     `original_activity` and `selected_attribute_value`. The label alone
     cannot be split back, since values such as `User_1` contain `_` too.
5. **Save** to `outputs/step1_preprocessing/<attribute>/`:

| File | Content |
|------|---------|
| `attributes_overview.csv` | the table shown to the user |
| `label_counts.csv` | every new label with activity, value and frequency |
| `relabeled_log.xes` | the relabelled log, the input for step 2 |
| `summary.json` | chosen attribute, pm4py version, counts |

### Results on the BPI 2017 log

3,093 traces, 124,866 events, 54 activities, 19 attributes.

| Attribute | Distinct values | Labels after step 1 |
|-----------|-----------------|---------------------|
| `org:resource` | 134 | 3,338 |
| `EventOrigin` | 3 | 54 |

`EventOrigin` gives exactly one label per activity: it is fully determined by
the activity (A_ = Application, O_ = Offer, W_ = Workflow), so it adds no
organisational information. With 3,338 labels for `org:resource`, discovery
and BIG in step 2 will be slow; whether and how to reduce the number of
resources (e.g. by grouping them into roles) is a decision for step 2.

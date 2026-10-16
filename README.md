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

## Setup

The assignment requires **pm4py 2.2.16** (needed for BIG). That version only
runs on **Python 3.9**, so create the virtual environment with 3.9:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` pins pm4py and its full dependency tree, so everyone gets
the same environment.

## Running

```powershell
python main.py preprocess                            # shows the attributes, asks which one
python main.py preprocess --attribute org:resource   # same, without the question
python main.py preprocess --log path\to\other.xes    # another log
python -m unittest discover tests -v                 # tests (tiny log, a few seconds)
```

## Project structure

```
main.py                     command-line entry point, one sub-command per step
orgmining/
  config.py                 paths, XES column names, label format
  log_io.py                 read XES -> DataFrame, write DataFrame -> XES
  preprocessing.py          step 1
tests/
  test_preprocessing.py     unit tests for step 1 on a 5-event log
datasets_group5_mining_organizational_patterns/
                            assignment material (log, example BIG output, PDFs)
outputs/                    generated results, not in git
  step1_preprocessing/<attribute>/
```

## Step 1 – preprocessing

`orgmining/preprocessing.py` does the following:

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

With 3,338 labels, discovery and BIG in step 2 will be slow. Whether and how
to reduce the number of resources (e.g. by grouping them into roles) is a
decision for step 2.

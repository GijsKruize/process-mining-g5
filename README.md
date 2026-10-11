# Mining Organizational Patterns — JM0211, Group 5

Implementation of the pipeline from the assignment: preprocess an event log,
build instance graphs with BIG, mine behavioral patterns with SUBDUE, and
evaluate them against a gold standard. The approach follows Diamantini, Genga
and Potena (2016) [1].

## Project structure

```
main.py                # runs all steps in one go
preprocess.py          # step 1: relabel activities with a chosen attribute (with grouping)
instance_graphs.py     # step 2: Petri net (Inductive Miner) + BIG -> networkx instance graphs
big_engine.py          # BIG's instance-graph algorithm (from the provided BIG.py)
determinism.py         # makes two runs give identical output
pattern_mining.py      # step 3: SUBDUE pattern mining + support + trace-pattern matrix + images
evaluate.py            # step 4: precision/recall against a gold standard
subdue/                # vendored SUBDUE algorithm (MIT licensed)
tests/                 # unit tests based on the worked examples in [1]
synthetic_gold_standard.csv   # gold standard for data/synthetic_validation.xes
data/                  # input logs
datasets_group5_mining_organizational_patterns/   # course-provided dataset
output/                # all generated files land here
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

The whole pipeline on the course dataset, with the resource as the
organisational attribute:

```bash
python main.py "data/BPI2017Denied(3).xes" --attribute org:resource --workers 4
```

Without `--attribute` step 1 prints all attributes of the log and asks which
one to use. `--workers` only affects speed, never the result.

The small synthetic log, with its gold standard:

```bash
python main.py data/synthetic_validation.xes --attribute org:group --noise-threshold 0 --num-best 10 --max-size 4 --gold-standard synthetic_gold_standard.csv
```

Each step can also be run on its own:

```bash
python preprocess.py "data/BPI2017Denied(3).xes" --attribute org:resource
python instance_graphs.py --workers 4
python pattern_mining.py
python evaluate.py --gold-standard my_gold_standard.csv
```

The unit tests:

```bash
python -m unittest discover -s tests -v
```

Every script lists its options with `--help`.

### Running time

Measured on the BPI 2017 "denied" log (3,093 traces, 124,866 events) with
`--attribute org:resource` on a 2-core machine, single process:

| step | time |
|------|------|
| 1 preprocessing (incl. role discovery) | about 40 s |
| 2 Petri net discovery | 1 to 2 min |
| 2 BIG (2,316 alignments + repair) | about 3 min |
| 3 SUBDUE + support matrix | 1 to 2 min |

## Step 1 — preprocessing

Prints every attribute of the log with a few example values, then asks which
one to fuse into the activity label. Every event's activity becomes
`<activity>_<attribute group>`; the untouched activity is kept in
`original_activity` and the group in `attribute_group`.

**Grouping.** Using every single user of `org:resource` gives 3,338 distinct
labels (54 activities, 134 users) on the course log, and the Inductive Miner then
runs for hours. Following the teacher's advice, the number of resources is
reduced first (`--grouping`):

| `--grouping` | what it does | labels on the course log | whole pipeline |
|--------------|--------------|--------------------------|----------------|
| `roles` | pm4py's role discovery [2]; each user is replaced by the role in which they perform most of their events | 225 (8 roles) | about 8 min |
| `frequency` | keeps the most frequent users covering `--grouping-coverage` of the events (default 0.8), the rest becomes `OTHER` | 1,675 at 0.8; 670 at 0.5 | about 23 min at 0.5 |
| `none` | uses the attribute as it is | 3,338 | hours |
| `auto` (default) | `roles` if the attribute has more than 20 distinct values, otherwise `none` | 225 | about 8 min |

pm4py's role discovery returns groups of activities performed by similar
sets of users, so a user normally appears in several roles. Assigning each
user to one (dominant) role is our own step; it is what makes the label say
"which kind of worker did this" rather than repeat the activity.
`roles.csv` lists the roles and `attribute_groups.csv` the role of every user.

Not every attribute with few values is useful: in the course log
`EventOrigin` is fully determined by the activity. Step 1 prints
"values/activity" per attribute; 1.0 means the attribute adds no information.

Output: `relabeled_log.xes`, `relabeled_log.csv`, `attribute_groups.csv`,
`roles.csv` (roles only), `attribute_recommendations.csv`.

## Step 2 — instance graphs

1. **Petri net.** The Inductive Miner is run on the relabelled log, as the
   assignment prescribes, so the causal relations are relations between
   activity-attribute pairs (Definition 5 in [1]). It runs with a noise
   threshold (`--noise-threshold`, default 0.2, i.e. the variant that keeps
   about 80% of the behaviour); 0 gives the basic miner from the lecture.
   A net mined elsewhere, for example in ProM from `relabeled_log.xes`, can
   be used instead with `--petri-net file.pnml`.
2. **BIG.** Every trace is aligned with the net; the instance graph is built
   with the instance-ordering rule (Definition 6 in [1]) and repaired around
   inserted and deleted events (Algorithm 1 in [1]). All traces get a graph,
   also those that do not fit the net.
3. **networkx.** BIG's textual output is parsed into one `networkx.DiGraph`
   per trace with node ids that are unique across all graphs.

`big_engine.py` contains the algorithm of the course-provided `BIG.py`,
restructured so that it can be called per trace. Differences, all explained
in the file: causal relations are stored in a set, each distinct label
sequence is aligned once, alignments use Dijkstra search by default
(`--alignment-variant astar` selects pm4py's default), and the path test in
the insertion repair gives the provided library's answers in linear time
(`--strict-path-check` switches to a real reachability test).

Other options: `--variant-coverage` (discover the net on the most frequent
trace variants only; off by default because most variants of this log occur
once), `--model-activity-attribute original_activity` (discover the net on
the bare activity and only label the nodes with the attribute; the earlier
behaviour, kept as a fallback), `--max-align-seconds`.

Output: `petri_net.pnml`, `instance_graphs.g` (BIG's text format),
`instance_graphs.pkl` (list of `networkx.DiGraph`, each with its `case_id`),
`instance_graph_index.csv` (one row per trace: case id, number of inserted
and deleted events, status), `instance_graph_stats.json` (model size, how
many traces fit, how many were repaired, running times).

### What to expect on the course log

With `--attribute org:resource` and the defaults, 1,644 of the 3,093 traces
fit the discovered net and 1,449 are repaired (1,703 inserted and 841
deleted events). The discovered model consists mostly of nested loops, so
almost every event may follow almost every other one, and the instance
graphs come out nearly sequential: 8 of the 3,093 graphs contain a split or
a join. The paper reports the same tendency for its real-life log. The
strongest pattern is a hand-over from the offer/call role to the validation
role (8 edges, in 2,010 of 3,093 traces).

A more selective net gives graphs with parallel branches. Two ways:

- mine the net in ProM from `output/relabeled_log.xes` and pass it with
  `--petri-net`;
- use the course-provided net, which was mined on the bare activities, and
  keep the role labels on the nodes:

  ```bash
  python preprocess.py "data/BPI2017Denied(3).xes" --attribute org:resource
  python instance_graphs.py --petri-net datasets_group5_mining_organizational_patterns/BPI2017Denied_petriNet.pnml --model-activity-attribute original_activity
  python pattern_mining.py
  ```

  This takes about a minute for step 2; no trace fits that net, so every
  graph is repaired, and 3,072 of the 3,093 graphs contain a split or a
  join. The price is that the organisational attribute then plays no part
  in the process model.

## Step 3 — pattern mining

All instance graphs are merged into one union graph (node ids are globally
unique, so a pattern can never span two traces) and mined with SUBDUE,
vendored under `subdue/` from https://github.com/holderlb/Subdue.

- `--limit 0` (default) lets SUBDUE extend every single-edge pattern once,
  which is needed for patterns to grow up to `--max-size`.
- Patterns with fewer than `--min-instances` (default 2) instances are
  dropped; SUBDUE would otherwise pad its list with one-off patterns.
- **Support** of a pattern is the number of traces whose instance graph
  contains the pattern as a subgraph (same labels, same edge directions),
  divided by the number of all traces. It is computed by matching the
  pattern against every instance graph. SUBDUE's own number of
  (non-overlapping) instances is reported next to it.
- `--iterations N` (N > 1) enables SUBDUE's hierarchy: after each iteration
  the best pattern is compressed into a single node and the search starts
  again. Patterns that contain such nodes are expanded back to the original
  events and marked `hierarchical_expanded`.
- `--exclude-activities start,end` removes events before mining and
  connects their neighbours.

Changes to the vendored SUBDUE, all marked in the source: edge direction
from networkx graphs was ignored upstream; patterns of earlier iterations
were corrupted when a later iteration compressed the graph; and three
quadratic loops were replaced by equivalent indexed versions (same output,
checked against the version without them).

Output: `pattern_stats.csv` (size, instances, support per pattern),
`trace_pattern_matrix.csv` (rows = cases, columns = patterns, 1 if the
pattern occurs in the case), `pattern_hierarchy.csv`, `patterns.pkl`,
`pattern_hierarchy.pkl`, `patterns/pattern_N.png`, `mining_filter_stats.json`.

## Step 4 — evaluation

`evaluate.py` compares the mined patterns with a gold standard file: one row
per expected pattern, written as edges `SourceLabel->TargetLabel` separated
by commas. Precision is the share of mined patterns that match a gold
pattern; recall the share of gold patterns that were mined. "Exact" requires
identical edge sets; "contains" also accepts a mined pattern that includes
the gold pattern.

A gold standard belongs to one log and one attribute, so `main.py` only
runs this step when `--gold-standard` is given.
`synthetic_gold_standard.csv` is the one for `data/synthetic_validation.xes`
with `--attribute org:group`.

## Reproducibility

Two runs with the same arguments produce byte-identical `instance_graphs.g`,
`instance_graph_index.csv`, `pattern_stats.csv` and
`trace_pattern_matrix.csv`, for any number of `--workers`.

This needed extra work, described in `determinism.py`: a trace that does not
fit the net usually has several optimal alignments, and pm4py 2.2.16 picks
one depending on memory addresses, so the unmodified library gives different
instance graphs on every run. `main.py` and `instance_graphs.py` therefore
restart themselves once with `PYTHONHASHSEED=0`. `petri_net.pnml` is the
same net in every run but contains random node ids written by pm4py's
exporter, so the file itself is not byte-identical.

## References

[1] Diamantini, Genga, Potena. "Behavioral process mining for unstructured
processes." Journal of Intelligent Information Systems 47 (2016): 5-32.

[2] Burattin, Sperduti, Veluscek. "Business models enhancement through
discovery of roles." IEEE CIDM 2013.

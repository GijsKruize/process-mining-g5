# Organizational behavioral pattern mining — Group 5

Python 3.9 + **PM4Py 2.2.16**. Entry point: `main.py`.

**Start with [the results guide](docs/RESULTATEN_LEESWIJZER.md).** It lists the actual outputs, conformance statistics, graph printouts and remaining human review. The historical audit is in [docs/AUDIT_BEVINDINGEN.md](docs/AUDIT_BEVINDINGEN.md).

## Weekend snapshot for teammates

Read [the change rationale and limits](docs/WEEKEND_HANDOFF.md) and [the committed results index](results/weekend/README.md). The branch extends Friday commit `40b9a51`; automatic reference scores are separate from the still-pending human gold standard. All graph printouts are in the committed graph archive.

## Project organization

```text
main.py                     small entry point
orgmining/
  cli.py                    command-line arguments and dispatch
  preprocessing.py          attribute selection and event relabelling
  roles.py                  role discovery and dominant-resource assignment
  instance_graphs.py        Petri-net discovery, BIG execution, step 2 orchestration
  graph_io.py               BIG parsing, NetworkX persistence and integrity checks
  conformance.py            full-log alignment, caching and statistics
  subdue_adapter.py         pinned upstream integration and indexing optimizations
  patterns.py               SUBDUE discovery, exact support, occurrences and matrix
  exports.py                every graph as SVG/text/GraphML, full tables and ZIP
  evaluation.py             draft gold, review packets, proxy and human evaluation
  repair_diagnostics.py     inspect worst-fitting and branching cases
  reporting.py              paper tables/figures/report and full results archive
  research.py               resume the complete research workflow
  visualization.py          matplotlib graph viewer
  artifacts.py, log_io.py    shared artifact/XES helpers
  config.py                 project paths and XES keys
scripts/
  diagnostics/              original audit and reference/single-case checks
  install_subdue.ps1        download the pinned upstream dependency
  run_conformance.py        direct convenience runner
  run_patterns.py           direct convenience runner
  export_all_graphs.py      direct convenience runner
vendor/subdue.lock.json     upstream URL, revision and license
vendor/subdue/              downloaded upstream source (MIT; ignored by Git)
evaluation/                 editable gold-standard draft
outputs/                    generated results, separated by pipeline stage
  step1_preprocessing/      preserved preprocessed log and role tables
  step2_instance_graphs/    preserved full baseline, no replacement
  conformance/             one alignment-statistics row per case
  step3_patterns/          discovered definitions, support, matrix, evidence
  instance_graph_exports/  ALL graph printouts and machine-readable exports
  evaluation/              automatic reference plus blank human review forms
  paper/                   paper-ready tables, figures, report and results bundle
tests/                      regression/unit/integration fixtures
docs/                       methodology, review instructions and results guide
BIG.py                      supplied course library, unmodified
```

New code imports the dedicated `graph_io` module. `GFileConverter` is still re-exported from `instance_graphs` for compatibility with earlier scripts. Input and output paths are derived from the project root. The dataset may be in the project or its immediate parent, as in the supplied working copy.

## Environment and upstream dependency

Use the existing environment or create one with Python 3.9:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\scripts\install_subdue.ps1
```

In this workspace the existing environment is one level above: `..\.venv\Scripts\python.exe`.

The assignment's [holderlb/Subdue](https://github.com/holderlb/Subdue) Python implementation is pinned at `f33567dea2fa7e9595c27b807f16b120a7bdebb2`. Vendor source stays unchanged. The adapter avoids its defective NetworkX direction import by using explicit directed JSON, and indexes repeated membership/overlap checks. Discovery retains the upstream search and score. Exact matching independently verifies support and occurrences. This release scores edge compression; do not call those scores full MDL description lengths.

## Commands

Run from the project root with the environment active:

```powershell
python main.py --help
python main.py preprocess --attribute org:resource --grouping roles
python main.py instance-graphs --workers 4
python main.py show-graph --case Application_1691306052
python main.py conformance --workers 3
python main.py mine-patterns
python main.py export-graphs
python main.py inspect-repairs
python main.py evaluate
python main.py paper-report
```

The existing step 1 and step 2 full artifacts are already present. **Do not rerun preprocessing/discovery just to regenerate the reports.** Continue from them with:

```powershell
python main.py research
```

This fingerprints and retains the saved baseline, resumes conformance from its input-hashed variant cache, reuses pattern/graph exports when the graph hash matches, prepares evaluation, and packages results. `conformance` can safely resume; it does not mine a new net. The baseline must exist before `research`. `mine-patterns` explicitly reruns mining with its CLI settings; `research` reuses a matching existing run. Use a separate `--output` folder for alternate mining experiments.

New step 2 output records the miner variant and PM4Py version. Existing baseline metadata is historical and was preserved. IM_CLEAN is the actual baseline variant; optional `--miner-variant imf` uses a separate `_imf` output folder. Noise threshold 0.2 is not proof of preserving 80% of observed behavior. `--max-traces` discovers a new model on a subset; it is not a one-case test with the full model.

## Definitions that matter for the paper

- A node represents an event occurrence. Repeated activity labels retain separate nodes and do not become loops in the DAG.
- Node labels are `activity_role`; IDs, case IDs and event positions are metadata, excluded from pattern equality.
- No cross-case edges are added. All exported graph edges remain directed.
- Case support counts each trace once; occurrence counts include each distinct exact matching edge set, allowing overlaps.
- SUBDUE uses bounded, heuristic beam search; it does not enumerate all patterns. Upstream-selected overlap-restricted instances and independently counted occurrences are different quantities.
- Exact support uses directed labelled **non-induced** subgraph matching: extra host edges are allowed.
- Graph branching is not proof of real-world concurrency. New summaries use `has_branching`; old baseline files retain the old metric name.
- Fitness measures conformance to a model learned on these same data. It is not model precision or proof of causal correctness.
- Human gold-standard metrics remain pending until the definitions and annotations have actually been reviewed. The automatic reference benchmark is labelled separately.

See [gold-standard instructions](docs/GOLD_STANDARD_HANDLEIDING.md) before entering labels. `evaluate` preserves an existing manual form and does not fill empty labels automatically.

## Checks

```powershell
python -m unittest discover tests -v
python scripts/diagnostics/audit_group5_outputs.py --log outputs/step1_preprocessing/org_resource_roles/relabeled_log.xes --graphs outputs/step2_instance_graphs/org_resource_roles/instance_graphs.pkl --roles outputs/step1_preprocessing/org_resource_roles/resource_roles.csv
python scripts/diagnostics/test_group5_single_case.py
python scripts/diagnostics/test_group5_reference_big.py
```

The supplied BIG library has a confirmed path-search defect. The baseline has deliberately been preserved. Selected-case diagnostics compare its repair result with a correct reachability function, on identical alignments; consult the resulting sensitivity summary before reporting the repair limitation. Event integrity alone does not establish semantic correctness of graph dependencies.

# Sophie weekend results: teammate handoff

**Base:** `origin/friday1610`, commit `40b9a51` (16 October 2026, instance-graph viewer). This was still the latest fetched Friday pipeline when the results branch was prepared on 18 October. This branch extends that pipeline; it does not replace it with the older resource-filter experiments.

## Verdict: do these results make sense?

They are a technically checked demonstration of frequent **activity-role sequences**, with limited coverage of different role interactions. They do not yet establish broad discovery of interactions between actual departments.

The eight roles are inferred resource activity profiles. Every resource is mapped to its dominant profile; the result is not an externally validated department label. All 16 selected patterns use Role_1 and/or Role_2. Four cross roles, and all four cross the **same Role_1 -> Role_2 boundary**. They are nested variants of a call-after-offers to validation sequence, not four independent kinds of collaboration.

| Observed role-changing graph edge | Cases containing that edge type | Selected motifs representing it | Cases with a selected motif |
|---|---:|---|---:|
| Role_1 -> Role_2 | 2,930 | P001, P004, P006, P012 | 2,679 |
| Role_2 -> Role_3 | 2,055 | None | 0 |
| Role_4 -> Role_1 | 2,229 | None | 0 |
| Role_2 -> Role_5 | 920 | None | 0 |

The cross-role motifs jointly occur in **2,679/3,093 cases (86.61%)**, and cover 91.43% of cases containing a Role_1 -> Role_2 graph edge. There are 35 observed directed cross-role edge types, but only one appears in the selected motifs. This is a descriptive coverage comparison on the existing graphs, not a manual-gold recall score. See `results/weekend/paper/role_handoff_coverage.csv` and its PNG/PDF heatmap.

For example P001 is:

```text
W-Call-after-offers-suspend_Role_1
 -> W-Call-after-offers-ate-abort_Role_2
 -> W-Validate-application-schedule_Role_2
 -> W-Validate-application-start_Role_2
 -> A-Validating_Role_2
 -> O-Returned_Role_2
```

It occurs in 2,475 cases (80.02%). These are exact checked occurrences in the supplied representation; interpreting them as real organisational responsibility transfers still needs domain validation.

## What changed from the Friday pipeline, and why

| Component | Friday implementation | Weekend change and reason |
|---|---|---|
| Preprocessing and roles | Attribute selection, role discovery, dominant-resource role | Preserved. No newly claimed organisational ground truth. |
| Discovery | PM4Py convenience IM call, noise 0.2 | Default behaviour preserved as IM_CLEAN; documentation corrected from explicit IMf. Optional IMf has a separate output suffix. |
| BIG | Supplied library and parallel chunks | Supplied BIG.py preserved. Added event/graph integrity checks and selected repair diagnostics. |
| Conversion | Converter inside instance_graphs.py | Moved to graph_io.py; compatibility import retained. Labels, IDs and edges preserved. |
| CLI | All entry-point code in main.py | Small main.py plus cli.py; original commands retained, research commands added. |
| Graph visualisation | Snake layout without event numbers | Added event numbers; complete SVG/text/GraphML exports and searchable case index. |
| Conformance | No full-case statistics persisted | Exact full-log alignment statistics, input-hashed resumable variant cache, cached empty-trace cost, per-case moves. Verified against PM4Py's evaluator. |
| Pattern mining | Not implemented | Pinned assignment SUBDUE implementation; directed JSON adapter, indexed membership/overlap operations, bounded beam search. |
| Support | Not implemented | Independently checked exact directed labelled non-induced matches, binary case support, all edge-set occurrences and 3,093 x 16 matrix. |
| Evaluation | Not implemented | Explicitly separate automatic reference test from blank human review forms. No invented manual labels. |
| Reporting | README run totals | Case statistics, paper tables/figures, exact evidence, full graph archive and methodology notes. |

The vendor NetworkX loader has a direction-import defect. We use its documented JSON loader with `directed="true"` instead of silently mining undirected edges. Vendor source itself remains unchanged. The adapter retains upstream search/scoring, with set indexes for membership, duplicate instances and overlap checks. The generated pattern IDs are local: metadata now comes from pattern labels rather than assuming those IDs identify original trace events; a regression test covers this.

The supplied BIG path search also has a known defect. We preserved it for the baseline and compared its repairs to correct reachability on 25 selected cases (all eight branching cases, ten lowest-fitness cases, prior missing-label cases and the example). All 25 reproduce the baseline; the path correction changes none of those 25 results. This does not prove the defect is harmless on every repaired case.

## Actual validation and conformance

- All 3,093 graphs checked against 124,866 events; labels, role assignments, event positions and unique IDs are preserved.
- All graphs are connected DAGs. 3,085 are chains; eight have branching. Branching alone does not prove concurrency.
- All 3,093 GraphML exports round-trip to the baseline; all SVG documents parse; support/matrix/occurrence totals agree.
- All 3,093 cases have completed recomputed alignments: mean trace fitness **0.982216**, PM4Py log fitness **0.980817**.
- **1,644 cases (53.15%)** have no visible alignment deviation; **1,449 (46.85%)** need at least one.
- **1,703 log-only moves**, **841 visible model-only moves**, and **293,452 silent routing moves**. Silent moves are not counted as visible deviations.
- These are in-sample model-conformance statistics, not model precision, held-out generalisation, or proof of correct causal edges.

High mean fitness and many imperfect cases are compatible: the deviations are often small within a longer trace. Only 1.36% of source events are log-only moves. The predominance of chains means SUBDUE is principally finding sequences in this run.

## Evaluation: what is known, and what is still missing

Search used beam 4, limit 5,000, size 2-5 edges, one iteration, vertex overlap, no temporal option and no pruning. Scores are the upstream **edge-compression heuristic**, not full MDL bit lengths. The returned patterns are not exhaustive and include nested alternatives.

The automatic reference test recovers **4/8 proposed motifs**, with micro precision 1.000, recall 0.692 and F1 0.818 over trace-motif cells. It is not the assignment's manual gold standard and does not judge all other returned patterns. In particular, the acceptance-to-offer motif is missed even though it appears in 2,909 cases: missing patterns are not necessarily rare patterns. Four unrecovered targets account for 5,258 missed positive trace-motif cells.

Human review is still pending: 280 cells over 35 selected cases plus 16 pattern-relevance decisions, and approval of the draft definitions. The human metrics remain null. Follow `docs/GOLD_STANDARD_HANDLEIDING.md`. Do not report the automatic precision 1.000 as independently validated pattern quality.

## Where to start reviewing

1. Open `results/weekend/README.md` and `results/weekend/paper/PAPER_RESULTS.md`.
2. Compare the handoff coverage heatmap with `step3_patterns/pattern_support.csv`: the selected motifs heavily concentrate on a single handoff.
3. Inspect `step3_patterns/figures/`, `occurrences.csv` (event positions), and `trace_pattern_matrix.csv`.
4. Read `conformance/per_case.csv`, `worst_cases.csv`, and `selected_cases/repair_sensitivity.csv`.
5. Unzip `instance_graph_exports/all_instance_graphs.zip` and open its `index.html` to see every case. This archive contains all 3,093 vector figures, text printouts and GraphML files, plus shared node/edge data.
6. Read the draft gold and complete independent human review before final claims. The proposed targets were informed by the earlier exploratory audit and are not preregistered independent expert labels.

## Reproduce without repeating the original long BIG run

Use Python 3.9, install `requirements.txt`, and get the supplied BIG.py from Canvas as before. Install the pinned assignment SUBDUE with `scripts/install_subdue.ps1` (or clone its URL and checkout the revision in `vendor/subdue.lock.json`).

```powershell
python scripts/restore_weekend_results.py --unpack-graphs
python main.py mine-patterns --output outputs/reproduced_patterns
python scripts/analyse_role_handoffs.py
python -m unittest discover tests -v
```

Restore copies committed derived artifacts to `outputs/`, preserves existing files by default, and recreates the NetworkX pickle from the raw BIG graphs plus the committed label/case mapping. The original XES, 121 MB relabelled XES, redundant 48 MB SUBDUE input and binary pickle are not committed; the raw .g, full graph archive, discovered patterns and conformance results are. To recompute conformance from the original assignment dataset, first run preprocessing and use a fresh `--output` folder if the serialized-log hash differs from the archived input hash. An identical semantic log may be serialized differently; do not repurpose an incompatible cache.

For method sensitivity, compare wider beam/numbest settings and different role mappings in separate output folders. Rechecking support alone cannot recover patterns excluded by the search. Consider the uncommon role groups and the dominant-role assumption. Activity-only discovery with later role enrichment remains a separate proposed comparison, not the method used for these results.

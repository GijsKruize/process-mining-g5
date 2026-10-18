# Paper results — actual run

## Scope and reproducibility

The existing baseline was retained: 3,093 cases, 124,866 events and 121,781 directed instance-graph edges. Its Petri net was discovered on the complete role-labelled log using PM4Py 2.2.16 IM_CLEAN, noise threshold 0.2. Organisational role discovery (threshold 0.65) followed by dominant-resource-role assignment produced eight assigned profiles and 225 labels. Noise 0.2 is not a demonstrated guarantee of preserving 80% of observed behaviour.

The baseline historical generation took 72.3 s for discovery and 4690.7 s for BIG on 4 workers. The current conformance run is a separate recomputation, not an additional discovery run. Identical label sequences share an alignment calculation; every case contributes once to the reported statistics.

## Conformance paragraph for the paper

All 3,093 cases were evaluated against the saved role-labelled Petri net using state-equation A* alignments in PM4Py 2.2.16. There were 3,093 completed and 0 incomplete alignments. Mean trace fitness was 0.982216; cost-normalized log fitness was 0.980817. A total of 1,644 cases (53.15%) required no visible log or model moves, whereas 1,449 cases required visible deviations. Across completed cases, alignments contained 1,703 log-only moves and 841 visible model-only moves. The 293,452 silent model moves represent allowed internal routing and were excluded from the visible-deviation criterion. These are in-sample conformance statistics; they do not establish held-out performance, model precision, causal correctness, or the accuracy of repaired instance-graph edges.

The complete case table is `../conformance/per_case.csv`; worst cases are in `../conformance/worst_cases.csv`. Fitness is PM4Py 2.2.16's default integer-cost normalization. Log fitness follows PM4Py's evaluation function: 1 minus summed raw alignment cost divided by summed best-worst cost. Raw costs include the small permitted silent-move costs. Individual trace fitness uses PM4Py 2.2.16's integer normalization, which floors costs to visible-move units. Thus log fitness is neither the mean case fitness nor a percentage of fitting traces. Optimal alignment ties may differ from those used in the historical BIG run.

## Pattern results

The assignment's Python SUBDUE implementation (commit f33567dea2fa7e9595c27b807f16b120a7bdebb2) was run on the disjoint union of all cases: no cross-case edges were added. Search used beam width 4, limit 5,000, pattern size 2–5 edges, one iteration, vertex overlap, no pruning and no temporal matching. Only activity-role node labels and the original edge labels participated in matching; event IDs and case metadata were excluded. Input edges explicitly retain their direction. Upstream search and compression scoring are retained with equivalent set-indexing optimizations for one-edge grouping, duplicate instances and overlap checks. Discovery uses upstream's approximate graph matcher; all reported support and occurrence counts were independently recomputed using exact directed labelled non-induced subgraph matching.

There are 16 retained definitions. Their compression scores are upstream's edge-compression heuristic, not full MDL description lengths. Case support counts each trace once even if a pattern occurs several times. The occurrence export counts all distinct matching edge sets, including overlaps; it is therefore different from the greedily overlap-restricted instance count used by SUBDUE scoring. Search is bounded and not exhaustive. With 3,085 chain graphs and eight branching graphs, these results principally characterize sequential resource-task behaviour.

All patterns: `../step3_patterns/pattern_support.csv` and `../step3_patterns/figures/`. Binary trace-pattern matrix: `../step3_patterns/trace_pattern_matrix.csv`. Event-level evidence: `../step3_patterns/occurrences.csv`.

## Evaluation: provisional automatic results and pending manual work

The automated benchmark compares detected motifs against eight machine-suggested reference sequences matched contiguously in the source event log, across all cases. A target is recovered when a mined pattern contains the exact directed labelled target motif; the target is predicted for a trace when any such mined pattern occurs in it. It measures target detection, not the relevance of every mined pattern or exhaustive pattern-set precision/recall. It is not a human gold standard. Its micro precision is 1.000000, recall 0.691956, F1 0.817936 (TP=11811, FP=0, FN=5258, TN=7675). The draft motifs were informed by event labels and a previous exploratory audit; do not describe them as independently human-selected or preregistered.

Human review status: **pending_human_review**; 0/280 annotation cells reviewed. Final assignment evaluation complete: **False**. No final human-gold precision or recall is claimed while those labels and target approvals remain missing. See `../../docs/GOLD_STANDARD_HANDLEIDING.md`.

## Known methodological limits

Resources are assigned to one dominant profile, not a confirmed job title. Six model-absent labels cover 385 events. A confirmed defect in supplied BIG.is_path can affect insertion repair; the extended selected-case study tested 25 cases, including all eight branching cases and the ten lowest-fitness cases. All 25 reruns reproduced historical edges; a correct path search changed edges in 0 of these cases. This is not a complete comparison for all 1,449 repair-requiring cases. Thus all-graph event integrity and all-case alignment fitness should not be interpreted as proof of semantic edge correctness. Human relevance review, the declared manual gold scope, and any model/role sensitivity analyses remain essential to final conclusions.

## Complete graph printouts

Open `../instance_graph_exports/index.html` to search every application and access its SVG, text and GraphML. `all_instance_graphs.zip` holds every case. The PDF `selected_graphs_and_all_patterns.pdf` contains selected cases and all discovered patterns; it is a readable selection, not a claim to contain all 3,093 graph pages. The SVG collection is the complete set of scalable printouts.

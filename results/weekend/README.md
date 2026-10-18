# Weekend results snapshot

Read [the teammate handoff](../../docs/WEEKEND_HANDOFF.md) for the changes from Friday commit `40b9a51`, interpretation and open questions.

- [Actual paper report](paper/PAPER_RESULTS.md), [conformance table](paper/conformance_table.csv), and [pattern table](paper/pattern_table.csv).
- [Role-handoff coverage](paper/role_handoff_coverage.csv) and [heatmap](paper/role_handoff_coverage.png): only Role_1 -> Role_2 appears in the selected cross-role motifs.
- [All 16 pattern definitions](step3_patterns/patterns.json), [support](step3_patterns/pattern_support.csv), [figures](step3_patterns/figures/), [binary trace-pattern matrix](step3_patterns/trace_pattern_matrix.csv), and [event evidence](step3_patterns/occurrences.csv).
- [Every case's conformance](conformance/per_case.csv), [summary](conformance/summary.json), and [selected-case repair diagnostics](conformance/selected_cases/).
- [All 3,093 graph printouts](instance_graph_exports/all_instance_graphs.zip): download/unzip, then open `index.html`; includes SVG, text, GraphML, nodes, edges and JSONL.
- [Selected graphs and all patterns PDF](paper/selected_graphs_and_all_patterns.pdf).
- [Automatic reference test](evaluation/automatic_benchmark.json) is explicitly a proxy. [Human review status](evaluation/manual_evaluation.json) is pending; blank forms are included.
- [Source graph file](step2_instance_graphs/org_resource_roles/instance_graphs.g), [saved Petri net](step2_instance_graphs/org_resource_roles/petri_net.pnml), [role mapping](step1_preprocessing/org_resource_roles/resource_roles.csv).
- [Artifact verification](paper/artifact_verification.json) and [test log](paper/tests.log).

The files are copied from the actual outputs, not rerun or edited to improve scores. [manifest.json](manifest.json) records their SHA-256 hashes. Historical paper text uses `outputs/` paths: restore the snapshot to those paths with `python scripts/restore_weekend_results.py --unpack-graphs`. Existing output files and annotations are preserved by default. Original XES inputs are intentionally excluded; no large duplicate input JSON or pickle is required to inspect results.

These roles are inferred work profiles, not verified departments. The frequent motifs have exact checked support; comprehensive organisational interpretation and manual-gold precision/recall remain unvalidated. See the handoff before using the scores in the paper.

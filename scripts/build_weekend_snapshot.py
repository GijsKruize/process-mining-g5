"""Curate a reviewable Git snapshot; exclude the raw XES and duplicate bulky inputs."""
import json
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from orgmining.artifacts import sha256,write_json


def run():
    target=ROOT/'results/weekend'
    target.mkdir(parents=True,exist_ok=True)
    selected=[]
    for folder in ['step1_preprocessing/org_resource_roles','step2_instance_graphs/org_resource_roles',
                   'conformance','step3_patterns','evaluation']:
        for source in (ROOT/'outputs'/folder).rglob('*'):
            if not source.is_file() or source.suffix not in ('.csv','.json','.jsonl','.svg','.log','.pnml','.g'):
                continue
            if source.name=='subdue_input.json' or source.suffix=='.log' and folder!='step3_patterns':
                continue
            selected.append(source)
    for name in ['all_instance_graphs.zip','case_index.csv','summary.json']:
        selected.append(ROOT/'outputs/instance_graph_exports'/name)
    for source in (ROOT/'outputs/paper').iterdir():
        if source.is_file() and source.suffix in ('.csv','.json','.md','.tex','.png','.pdf') and source.name!='baseline_manifest.json':
            selected.append(source)
    selected.append(ROOT/'outputs/paper/tests.log')
    if (ROOT/'outputs/paper/publication_tests.log').exists():
        selected.append(ROOT/'outputs/paper/publication_tests.log')
    records=[]
    for source in sorted(set(selected)):
        relative=source.relative_to(ROOT/'outputs')
        destination=target/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        records.append(dict(path=relative.as_posix(),bytes=source.stat().st_size,sha256=sha256(source)))
    write_json(target/'manifest.json',dict(base_commit='40b9a51',prepared_date='2026-10-18',
        full_case_count=3093,pattern_count=16,files=records,
        excluded=['Original assignment XES','121 MB relabeled XES','Binary NetworkX pickle (recreated by restore helper)',
                  '48 MB redundant SUBDUE input JSON','Duplicate results_bundle.zip','Unrelated parent-folder experiments'],
        status='Automatic results complete; human gold-standard review pending.'))
    (target/'README.md').write_text('''# Weekend results snapshot

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
''',encoding='utf-8')
    print(f'{len(records)} result files, {sum(r["bytes"] for r in records)/1e6:.2f} MB uncompressed, copied to {target}')


if __name__=='__main__':
    run()

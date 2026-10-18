"""Paper tables/figures and a self-contained results archive; no invented results."""
import json
import zipfile
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from .artifacts import GRAPHS, STEP1, STEP2, LOG, NET, sha256, write_json, write_csv
from .graph_io import GFileConverter
from .patterns import from_record
from .visualization import InstanceGraphViewer


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def run(output='outputs/paper'):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    conf=read('outputs/conformance/summary.json')
    mining=read('outputs/step3_patterns/summary.json')
    exports=read('outputs/instance_graph_exports/summary.json')
    proxy=read('outputs/evaluation/automatic_benchmark.json')
    manual=read('outputs/evaluation/manual_evaluation.json')
    inspection=read('outputs/conformance/selected_cases/summary.json')
    cases=pd.read_csv('outputs/conformance/per_case.csv')
    patterns=pd.read_csv('outputs/step3_patterns/pattern_support.csv')
    historical=read(STEP2/'summary.json')
    table=[('Cases',conf['cases_total']),('Events',exports['nodes']),('Instance graph edges',exports['edges']),
           ('Completed alignments',conf['cases_completed']),('Incomplete alignments',conf['cases_incomplete']),
           ('Fully fitting cases (no visible deviations)',conf['fitting_cases']),
           ('Cases with visible deviations',conf['cases_requiring_visible_repair']),
           ('Fitting cases (%)',conf['fitting_cases_pct']),('Mean trace alignment fitness',conf['average_trace_fitness']),
           ('Cost-weighted log alignment fitness',conf['log_fitness']),
           ('Log-only moves',conf['totals']['log_moves']),('Visible model-only moves',conf['totals']['visible_model_moves']),
           ('Silent model moves',conf['totals']['silent_model_moves']),('Discovered patterns',mining['patterns'])]
    frame=pd.DataFrame(table,columns=['Measure','Value'])
    frame.to_csv(output/'conformance_table.csv',index=False)
    latex_frame=frame.copy()
    latex_frame['Value']=[str(value) if isinstance(value,int) else f'{value:.6f}' for _,value in table]
    latex_frame.to_latex(output/'conformance_table.tex',index=False,escape=True)
    pattern_columns=['pattern_id','nodes','edges','support_cases','support_pct','total_exact_occurrences']
    patterns[pattern_columns].to_csv(output/'pattern_table.csv',index=False)
    patterns[pattern_columns].to_latex(output/'pattern_table.tex',index=False,escape=True,float_format='%.2f')
    fig,ax=plt.subplots(figsize=(7,4))
    ax.hist(cases.fitness.dropna(),bins=30,color='#2a78d6',edgecolor='white')
    ax.set(xlabel='In-sample alignment fitness',ylabel='Number of cases',title='Conformance against the saved role-labelled Petri net')
    fig.tight_layout()
    for suffix in ['pdf','png']:
        fig.savefig(output/f'conformance_fitness.{suffix}',dpi=200)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,5))
    ax.bar(patterns.pattern_id,patterns.support_pct,color='#1baf7a')
    ax.set(xlabel='SUBDUE pattern',ylabel='Case support (%)',ylim=(0,100))
    ax.tick_params(axis='x',rotation=60)
    fig.tight_layout()
    for suffix in ['pdf','png']:
        fig.savefig(output/f'pattern_support.{suffix}',dpi=200)
    plt.close(fig)
    graphs=GFileConverter.load(GRAPHS)
    viewer=InstanceGraphViewer(graphs)
    chosen={0}
    chosen.update(i for i,g in enumerate(graphs) if any(d>1 for _,d in g.out_degree()))
    chosen.update(map(int,cases.sort_values('fitness').head(5).graph_index))
    definitions=read('outputs/step3_patterns/patterns.json')
    with PdfPages(output/'selected_graphs_and_all_patterns.pdf') as pdf:
        for i in sorted(chosen):
            fig=viewer.plot(graphs[i],title=f"{graphs[i].graph['case_id']} | fitness {cases.loc[cases.graph_index==i,'fitness'].iloc[0]:.4f}")
            pdf.savefig(fig,bbox_inches='tight');plt.close(fig)
        for record in definitions:
            g=from_record(record)
            fig=viewer.plot(g,title=record['pattern_id'])
            pdf.savefig(fig,bbox_inches='tight');plt.close(fig)
    metrics=proxy['micro_metrics']
    text=f'''# Paper results — actual run

## Scope and reproducibility

The existing baseline was retained: {conf['cases_total']:,} cases, {exports['nodes']:,} events and {exports['edges']:,} directed instance-graph edges. Its Petri net was discovered on the complete role-labelled log using PM4Py 2.2.16 IM_CLEAN, noise threshold 0.2. Organisational role discovery (threshold 0.65) followed by dominant-resource-role assignment produced eight assigned profiles and 225 labels. Noise 0.2 is not a demonstrated guarantee of preserving 80% of observed behaviour.

The baseline historical generation took {historical['petri_net_seconds']} s for discovery and {historical['big_seconds']} s for BIG on {historical['workers']} workers. The current conformance run is a separate recomputation, not an additional discovery run. Identical label sequences share an alignment calculation; every case contributes once to the reported statistics.

## Conformance paragraph for the paper

All {conf['cases_total']:,} cases were evaluated against the saved role-labelled Petri net using state-equation A* alignments in PM4Py 2.2.16. There were {conf['cases_completed']:,} completed and {conf['cases_incomplete']:,} incomplete alignments. Mean trace fitness was {conf['average_trace_fitness']:.6f}; cost-normalized log fitness was {conf['log_fitness']:.6f}. A total of {conf['fitting_cases']:,} cases ({conf['fitting_cases_pct']:.2f}%) required no visible log or model moves, whereas {conf['cases_requiring_visible_repair']:,} cases required visible deviations. Across completed cases, alignments contained {conf['totals']['log_moves']:,} log-only moves and {conf['totals']['visible_model_moves']:,} visible model-only moves. The {conf['totals']['silent_model_moves']:,} silent model moves represent allowed internal routing and were excluded from the visible-deviation criterion. These are in-sample conformance statistics; they do not establish held-out performance, model precision, causal correctness, or the accuracy of repaired instance-graph edges.

The complete case table is `../conformance/per_case.csv`; worst cases are in `../conformance/worst_cases.csv`. Fitness is PM4Py 2.2.16's default integer-cost normalization. Log fitness follows PM4Py's evaluation function: 1 minus summed raw alignment cost divided by summed best-worst cost. Raw costs include the small permitted silent-move costs. Individual trace fitness uses PM4Py 2.2.16's integer normalization, which floors costs to visible-move units. Thus log fitness is neither the mean case fitness nor a percentage of fitting traces. Optimal alignment ties may differ from those used in the historical BIG run.

## Pattern results

The assignment's Python SUBDUE implementation (commit {mining['upstream_commit']}) was run on the disjoint union of all cases: no cross-case edges were added. Search used beam width 4, limit 5,000, pattern size 2–5 edges, one iteration, vertex overlap, no pruning and no temporal matching. Only activity-role node labels and the original edge labels participated in matching; event IDs and case metadata were excluded. Input edges explicitly retain their direction. Upstream search and compression scoring are retained with equivalent set-indexing optimizations for one-edge grouping, duplicate instances and overlap checks. Discovery uses upstream's approximate graph matcher; all reported support and occurrence counts were independently recomputed using exact directed labelled non-induced subgraph matching.

There are {mining['patterns']} retained definitions. Their compression scores are upstream's edge-compression heuristic, not full MDL description lengths. Case support counts each trace once even if a pattern occurs several times. The occurrence export counts all distinct matching edge sets, including overlaps; it is therefore different from the greedily overlap-restricted instance count used by SUBDUE scoring. Search is bounded and not exhaustive. With 3,085 chain graphs and eight branching graphs, these results principally characterize sequential resource-task behaviour.

All patterns: `../step3_patterns/pattern_support.csv` and `../step3_patterns/figures/`. Binary trace-pattern matrix: `../step3_patterns/trace_pattern_matrix.csv`. Event-level evidence: `../step3_patterns/occurrences.csv`.

## Evaluation: provisional automatic results and pending manual work

The automated benchmark compares detected motifs against eight machine-suggested reference sequences matched contiguously in the source event log, across all cases. A target is recovered when a mined pattern contains the exact directed labelled target motif; the target is predicted for a trace when any such mined pattern occurs in it. It measures target detection, not the relevance of every mined pattern or exhaustive pattern-set precision/recall. It is not a human gold standard. Its micro precision is {metrics['precision']:.6f}, recall {metrics['recall']:.6f}, F1 {metrics['f1']:.6f} (TP={metrics['tp']}, FP={metrics['fp']}, FN={metrics['fn']}, TN={metrics['tn']}). The draft motifs were informed by event labels and a previous exploratory audit; do not describe them as independently human-selected or preregistered.

Human review status: **{manual['status']}**; {manual['reviewed_cells']}/{manual['annotation_cells']} annotation cells reviewed. Final assignment evaluation complete: **{manual['final_assignment_evaluation_complete']}**. No final human-gold precision or recall is claimed while those labels and target approvals remain missing. See `../../docs/GOLD_STANDARD_HANDLEIDING.md`.

## Known methodological limits

Resources are assigned to one dominant profile, not a confirmed job title. Six model-absent labels cover 385 events. A confirmed defect in supplied BIG.is_path can affect insertion repair; the extended selected-case study tested {inspection['cases']} cases, including all eight branching cases and the ten lowest-fitness cases. All {inspection['original_rerun_matches_historical']} reruns reproduced historical edges; a correct path search changed edges in {inspection['cases_with_edges_changed_by_correct_path_search']} of these cases. This is not a complete comparison for all 1,449 repair-requiring cases. Thus all-graph event integrity and all-case alignment fitness should not be interpreted as proof of semantic edge correctness. Human relevance review, the declared manual gold scope, and any model/role sensitivity analyses remain essential to final conclusions.

## Complete graph printouts

Open `../instance_graph_exports/index.html` to search every application and access its SVG, text and GraphML. `all_instance_graphs.zip` holds every case. The PDF `selected_graphs_and_all_patterns.pdf` contains selected cases and all discovered patterns; it is a readable selection, not a claim to contain all 3,093 graph pages. The SVG collection is the complete set of scalable printouts.
'''
    (output/'PAPER_RESULTS.md').write_text(text,encoding='utf-8')
    write_reader_guide(conf,mining,manual,patterns,inspection)
    tables={**conf,'patterns':mining['patterns'],'automatic_proxy':proxy,'manual_evaluation':manual}
    write_json(output/'results_summary.json',tables)
    paths=[LOG,NET,GRAPHS,STEP2/'instance_graphs.g',STEP2/'summary.json']
    write_json(output/'baseline_manifest.json',{str(p):sha256(p) for p in paths})
    write_json(output/'reproducibility.json',dict(python='3.9',pm4py='2.2.16',subdue_commit=mining['upstream_commit'],
               graph_sha256=sha256(GRAPHS),net_sha256=sha256(NET),log_sha256=sha256(LOG),
               patterns_sha256=sha256('outputs/step3_patterns/patterns.json'),
               gold_draft_sha256=sha256('evaluation/gold_standard_draft.json')))
    # Bundle inputs/results/source without nested copies of existing ZIP archives.
    roots=[STEP1,STEP2,Path('outputs/conformance'),Path('outputs/step3_patterns'),
           Path('outputs/instance_graph_exports'),Path('outputs/evaluation'),output,
           Path('docs'),Path('evaluation'),Path('orgmining'),Path('tests'),Path('scripts')]
    with zipfile.ZipFile(output/'results_bundle.zip','w',zipfile.ZIP_DEFLATED) as bundle:
        for root in roots:
            for path in root.rglob('*'):
                if path.is_file() and path.suffix not in ('.zip','.pyc') and '__pycache__' not in path.parts:
                    bundle.write(path,path.as_posix())
        for name in ['main.py','requirements.txt','README.md','BIG.py','vendor/subdue/LICENSE','vendor/subdue/README.md','vendor/subdue.lock.json']:
            bundle.write(name,name)
        for path in Path('vendor/subdue/src').glob('*.py'):
            bundle.write(path,path.as_posix())
    print(f'Paper report and full bundle written to {output}',flush=True)


def write_reader_guide(conf,mining,manual,patterns,inspection):
    pattern_rows='\n'.join(f"| {r.pattern_id} | {r.support_cases} | {r.support_pct:.2f}% | {r.description} |" for r in patterns.itertuples())
    text=f"""# Resultaten en vervolgstappen - 17 oktober 2026

De volledige automatische workflow is uitgevoerd op het bewaarde rollenmodel en alle 3.093 instance graphs. De handmatige beoordeling is voorbereid, maar kan niet namens een menselijke beoordelaar als voltooid worden aangemerkt.

## Open deze bestanden eerst

| Doel | Exact pad vanaf de projectmap |
|---|---|
| Alles bij elkaar, inclusief code en baseline | `outputs/paper/results_bundle.zip` |
| Papertekst met werkelijke cijfers en beperkingen | `outputs/paper/PAPER_RESULTS.md` |
| Alle 3.093 graphs doorzoeken | `outputs/instance_graph_exports/index.html` |
| Alle graphs als SVG, tekst en GraphML | `outputs/instance_graph_exports/all_instance_graphs.zip` |
| Alle eventnodes en gerichte edges | `outputs/instance_graph_exports/nodes.csv`, `edges.csv` |
| Graphs als één machineleesbare export | `outputs/instance_graph_exports/all_graphs.jsonl` |
| Conformance van iedere application | `outputs/conformance/per_case.csv` |
| Conformance-samenvatting | `outputs/conformance/summary.json` |
| Laagste fitness en acht branching cases | `outputs/conformance/worst_cases.csv`, `selected_cases/branching_cases.csv` |
| Geselecteerde alignmentstappen en events | `outputs/conformance/selected_cases/alignments/`, `events/` |
| Alle gevonden patronen en support | `outputs/step3_patterns/pattern_support.csv` |
| Exacte patroongraphs | `outputs/step3_patterns/patterns.json` |
| Patroonfiguren voor je paper | `outputs/step3_patterns/figures/P001.svg` t/m `P016.svg` |
| Matrix: 3.093 traces x 16 patronen | `outputs/step3_patterns/trace_pattern_matrix.csv` |
| Voorkomens met concrete eventposities | `outputs/step3_patterns/occurrences.csv` |
| Figuren en LaTeX-tabellen | `outputs/paper/conformance_table.tex`, `pattern_table.tex`, `conformance_fitness.pdf`, `pattern_support.pdf` |
| Leesbare PDF met geselecteerde cases en alle patronen | `outputs/paper/selected_graphs_and_all_patterns.pdf` |
| Gold-standardvoorstel | `evaluation/gold_standard_draft.json` |
| Handmatige invulformulieren | `outputs/evaluation/manual_annotations.csv`, `manual_pattern_relevance.csv` |
| Stapsgewijze annotatiehandleiding | `docs/GOLD_STANDARD_HANDLEIDING.md` |

De PDF is een selectie; de SVG/tekst/GraphML-map bevat werkelijk alle applications. Voorbeeld: index 0 is `outputs/instance_graph_exports/svg/0000_Application_1691306052.svg`. Gebruik de SVG direct als schaalbare figuur of de GraphML in een graph-editor. Alle lokale event-ID's en globale node-ID's zijn terug te vinden in de CSV's. De oorspronkelijke BIG/NetworkX-output blijft in `outputs/step2_instance_graphs/org_resource_roles/`.

## Conformance: cijfers die je mag rapporteren

- {conf['cases_completed']}/{conf['cases_total']} cases voltooid; {conf['cases_incomplete']} onvolledig.
- Gemiddelde trace-fitness: **{conf['average_trace_fitness']:.6f}**.
- PM4Py log-fitness: **{conf['log_fitness']:.6f}**.
- Cases zonder zichtbare afwijkingen: **{conf['fitting_cases']} ({conf['fitting_cases_pct']:.2f}%)**.
- Cases met zichtbare afwijkingen: **{conf['cases_requiring_visible_repair']} ({100-conf['fitting_cases_pct']:.2f}%)**.
- Log-only moves: **{conf['totals']['log_moves']}**; zichtbare model-only moves: **{conf['totals']['visible_model_moves']}**.
- Stille modelmoves: **{conf['totals']['silent_model_moves']}**, apart gehouden van zichtbare afwijkingen.

Dat veel cases minstens één afwijking hebben, is verenigbaar met hoge gemiddelde fitness: de afwijking is vaak klein binnen een langere trace. Slechts {100*conf['totals']['log_moves']/conf['event_rows']:.2f}% van de geregistreerde events valt op een log-only move. Dit bewijst geen juiste causaliteit en betreft dezelfde data als waarop het model is geleerd. Er is geen held-out generalisatietest of modelprecisionmeting uitgevoerd.

De uitgebreide repaircontrole omvat {inspection['cases']} geselecteerde cases. Alle {inspection['original_rerun_matches_historical']} herhalingen geven dezelfde edges als de baseline; een correcte BIG-padzoekfunctie verandert bij {inspection['cases_with_edges_changed_by_correct_path_search']} van deze cases de edges. De bekende fout is dus niet aangetoond als oorzaak in deze steekproef. De geleverde library en baseline zijn bewaard.

## Alle gevonden patronen

SUBDUE rangschikt op een compression-heuristiek, niet op support alleen. Kortere patronen kunnen meer support hebben dan de hoogst gerangschikte langere patronen. Verschillende patronen kunnen overlappende of geneste delen van dezelfde werkfase beschrijven.

| Patroon | Cases | Support | Labelpad |
|---|---:|---:|---|
{pattern_rows}

De discovery draait op alle graphs als losse componenten. Er zijn geen edges tussen applications toegevoegd. Alleen labels tellen mee bij matching. Alle gerapporteerde support is na discovery exact gecontroleerd. De zoekinstellingen (beam 4, limit 5000, maximaal 5 edges, minimaal 2 edges) begrenzen welke patronen worden gevonden. De uitvoer is geen uitputtende inventaris van alle mogelijke gedragingen.

## Wat is al geëvalueerd en wat vul je zelf in?

De automatische referentietest gebruikt acht voorgestelde sequentiemotieven en telt die rechtstreeks in de eventvolgorde. De uitkomsten staan in `outputs/evaluation/automatic_benchmark.json`. Het is een proxy voor motiefdetectie, geen handmatig beoordeelde gold standard en geen oordeel over alle overige gevonden patronen. De betekenis en beperkingen staan ook in de papertekst.

Voor de menselijke stap zijn {manual['annotation_cells']} trace-motiefcellen over 35 geselecteerde cases voorbereid, plus {manual['mined_patterns_for_relevance_review']} relevantiebeoordelingen van gevonden patronen. Momenteel zijn {manual['reviewed_cells']} trace-motiefcellen beoordeeld. Handmatige scores zijn daarom nog niet beschikbaar. De handleiding laat precies zien hoe je definities bevestigt, events bekijkt, 0/1 invult en daarna scores berekent. Een ingevulde automatische suggestie is geen menselijke beoordeling.

## Stap voor stap opnieuw uitvoeren

1. Activeer de Python 3.9-omgeving. In deze werkmap kun je `..\.venv\Scripts\python.exe` gebruiken in plaats van `python`.
2. `python main.py research` hervat de volledige workflow zonder de baseline opnieuw te leren. De conformance-cache voorkomt dubbel rekenwerk.
3. Voor alleen de tabellen/figuren: `python main.py paper-report`.
4. Voor nieuwe SUBDUE-instellingen: `python main.py mine-patterns --beam 8 --numbest 30 --output outputs/experiments/beam8`; dit bewaart de hoofdresultaten. Deze alternatieve experimenten zijn nog niet uitgevoerd.
5. Na echte handmatige annotatie: `python main.py evaluate` en daarna `python main.py paper-report`. Archiveer de oude resultaten als je definities wijzigt.

De root bevat nu alleen `main.py`, README, requirements en de geleverde BIG-library. Pipelinecode staat in `orgmining/`; oude auditscripts in `scripts/diagnostics/`; instructies in `docs/`. De tests staan in `tests/`.
"""
    Path('docs/RESULTATEN_LEESWIJZER.md').write_text(text,encoding='utf-8')

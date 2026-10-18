# Resultaten en vervolgstappen - 17 oktober 2026

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

- 3093/3093 cases voltooid; 0 onvolledig.
- Gemiddelde trace-fitness: **0.982216**.
- PM4Py log-fitness: **0.980817**.
- Cases zonder zichtbare afwijkingen: **1644 (53.15%)**.
- Cases met zichtbare afwijkingen: **1449 (46.85%)**.
- Log-only moves: **1703**; zichtbare model-only moves: **841**.
- Stille modelmoves: **293452**, apart gehouden van zichtbare afwijkingen.

Dat veel cases minstens één afwijking hebben, is verenigbaar met hoge gemiddelde fitness: de afwijking is vaak klein binnen een langere trace. Slechts 1.36% van de geregistreerde events valt op een log-only move. Dit bewijst geen juiste causaliteit en betreft dezelfde data als waarop het model is geleerd. Er is geen held-out generalisatietest of modelprecisionmeting uitgevoerd.

De uitgebreide repaircontrole omvat 25 geselecteerde cases. Alle 25 herhalingen geven dezelfde edges als de baseline; een correcte BIG-padzoekfunctie verandert bij 0 van deze cases de edges. De bekende fout is dus niet aangetoond als oorzaak in deze steekproef. De geleverde library en baseline zijn bewaard.

## Alle gevonden patronen

SUBDUE rangschikt op een compression-heuristiek, niet op support alleen. Kortere patronen kunnen meer support hebben dan de hoogst gerangschikte langere patronen. Verschillende patronen kunnen overlappende of geneste delen van dezelfde werkfase beschrijven.

| Patroon | Cases | Support | Labelpad |
|---|---:|---:|---|
| P001 | 2475 | 80.02% | W-Call-after-offers-suspend_Role_1 -> W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 -> O-Returned_Role_2 |
| P002 | 2444 | 79.02% | W-Call-after-offers-schedule_Role_1 -> W-Call-after-offers-start_Role_1 -> A-Complete_Role_1 -> W-Call-after-offers-suspend_Role_1 -> W-Call-after-offers-resume_Role_1 -> W-Call-after-offers-suspend_Role_1 |
| P003 | 2418 | 78.18% | W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 -> O-Returned_Role_2 -> W-Validate-application-suspend_Role_2 |
| P004 | 2403 | 77.69% | W-Call-after-offers-resume_Role_1 -> W-Call-after-offers-suspend_Role_1 -> W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 |
| P005 | 2691 | 87.00% | W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 -> O-Returned_Role_2 |
| P006 | 2679 | 86.61% | W-Call-after-offers-suspend_Role_1 -> W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 |
| P007 | 2451 | 79.24% | W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 -> O-Returned_Role_2 -> W-Validate-application-suspend_Role_2 |
| P008 | 2448 | 79.15% | W-Call-after-offers-schedule_Role_1 -> W-Call-after-offers-start_Role_1 -> A-Complete_Role_1 -> W-Call-after-offers-suspend_Role_1 -> W-Call-after-offers-resume_Role_1 |
| P009 | 2918 | 94.34% | W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 |
| P010 | 2895 | 93.60% | W-Call-after-offers-schedule_Role_1 -> W-Call-after-offers-start_Role_1 -> A-Complete_Role_1 -> W-Call-after-offers-suspend_Role_1 |
| P011 | 2717 | 87.84% | W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 -> O-Returned_Role_2 |
| P012 | 2679 | 86.61% | W-Call-after-offers-suspend_Role_1 -> W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 |
| P013 | 2935 | 94.89% | W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 -> A-Validating_Role_2 |
| P014 | 2944 | 95.18% | O-Create-Offer_Role_1 -> O-Created_Role_1 -> O-Sent-mail-and-online_Role_1 |
| P015 | 3014 | 97.45% | W-Call-after-offers-schedule_Role_1 -> W-Call-after-offers-start_Role_1 -> A-Complete_Role_1 |
| P016 | 2918 | 94.34% | W-Call-after-offers-ate-abort_Role_2 -> W-Validate-application-schedule_Role_2 -> W-Validate-application-start_Role_2 |

De discovery draait op alle graphs als losse componenten. Er zijn geen edges tussen applications toegevoegd. Alleen labels tellen mee bij matching. Alle gerapporteerde support is na discovery exact gecontroleerd. De zoekinstellingen (beam 4, limit 5000, maximaal 5 edges, minimaal 2 edges) begrenzen welke patronen worden gevonden. De uitvoer is geen uitputtende inventaris van alle mogelijke gedragingen.

## Wat is al geëvalueerd en wat vul je zelf in?

De automatische referentietest gebruikt acht voorgestelde sequentiemotieven en telt die rechtstreeks in de eventvolgorde. De uitkomsten staan in `outputs/evaluation/automatic_benchmark.json`. Het is een proxy voor motiefdetectie, geen handmatig beoordeelde gold standard en geen oordeel over alle overige gevonden patronen. De betekenis en beperkingen staan ook in de papertekst.

Voor de menselijke stap zijn 280 trace-motiefcellen over 35 geselecteerde cases voorbereid, plus 16 relevantiebeoordelingen van gevonden patronen. Momenteel zijn 0 trace-motiefcellen beoordeeld. Handmatige scores zijn daarom nog niet beschikbaar. De handleiding laat precies zien hoe je definities bevestigt, events bekijkt, 0/1 invult en daarna scores berekent. Een ingevulde automatische suggestie is geen menselijke beoordeling.

## Stap voor stap opnieuw uitvoeren

1. Activeer de Python 3.9-omgeving. In deze werkmap kun je `..\.venv\Scripts\python.exe` gebruiken in plaats van `python`.
2. `python main.py research` hervat de volledige workflow zonder de baseline opnieuw te leren. De conformance-cache voorkomt dubbel rekenwerk.
3. Voor alleen de tabellen/figuren: `python main.py paper-report`.
4. Voor nieuwe SUBDUE-instellingen: `python main.py mine-patterns --beam 8 --numbest 30 --output outputs/experiments/beam8`; dit bewaart de hoofdresultaten. Deze alternatieve experimenten zijn nog niet uitgevoerd.
5. Na echte handmatige annotatie: `python main.py evaluate` en daarna `python main.py paper-report`. Archiveer de oude resultaten als je definities wijzigt.

De root bevat nu alleen `main.py`, README, requirements en de geleverde BIG-library. Pipelinecode staat in `orgmining/`; oude auditscripts in `scripts/diagnostics/`; instructies in `docs/`. De tests staan in `tests/`.

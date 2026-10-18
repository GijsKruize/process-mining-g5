> Historische audit van 16 oktober. Op 17 oktober is volledige conformance uitgevoerd en stap 3 toegevoegd. Zie RESULTATEN_LEESWIJZER.md en outputs/paper/PAPER_RESULTS.md voor de actuele resultaten; eerdere uitspraken over nog niet uitgevoerde analyses hieronder beschrijven de toestand op 16 oktober.

# Audit Group 5 — 16 oktober 2026

De huidige graphs zijn technisch consistent met de events en met BIG's opgeslagen output. Je kunt hiermee SUBDUE ontwikkelen en terugkerende activiteit-rolsequenties onderzoeken. De graphs zijn nog geen gevalideerde weergave van organisatorische causaliteit of concurrency. De belangrijkste beperking zit in het geleerde model en de interpretatie van de rollen; jouw voorbeeldcase wordt niet door een conversie- of tekenfout een keten.

## Wat werkelijk is gecontroleerd

Ik heb de aangeleverde audit als te toetsen bron gebruikt en preprocessing, role discovery, discovery-aanroep, BIG, chunking, conversie, visualisatie en tests gelezen. De checks zijn uitgevoerd in de bestaande Python 3.9-omgeving met PM4Py 2.2.16. Alle bestaande productie-output is bewaard.

| Controle | Resultaat |
|---|---|
| Oorspronkelijke XES versus relabelled XES | Alle cases, eventvolgorde, oorspronkelijke activiteiten en bestaande eventwaarden behouden. Datum- en getalnotatie kan door serialisatie verschillen; vergeleken op betekenis. |
| Relabelled XES versus alle opgeslagen graphs | 3.093 cases, 124.866 events/nodes, alle labels en posities correct |
| Rollen versus resource_roles.csv | Geen mismatches |
| BIG .g versus pickle | Alle nodelabels en unieke gerichte edges gelijk |
| Structuur alle rollengraphs | Allemaal verbonden DAGs; globale node-ID's uniek; geen terugwaartse edges of verkeerde edgelabels |
| Simpele ketens | 3.085 van 3.093; de andere 8 hebben branching |
| Referentiebestand versus oorspronkelijke XES | Alle 3.093 labelsequenties gelijk; 124.866 nodes, 136.282 unieke edges; 3.072 branching graphs |
| Nieuwe BIG-run voorbeeld met volledig rollenmodel | Exact dezelfde 33 nodes en 32 edges als de bestaande volledige run |
| Nieuwe BIG-run voorbeeld met meegeleverd referentiemodel | Exact dezelfde 33 nodes en 37 edges als de meegeleverde eerste referentiegraph |
| Nieuwe integriteitsvalidator op bestaande productiegraphs | Zie runtime_validation.txt |
| Unit tests na aanpassingen | 29 tests geslaagd |

Bronnen: `outputs/diagnostics/audit_all_cases.txt`, `audit_all_cases.csv`, `investigation.json`, `single_case.txt`, `reference_case.txt`, `runtime_validation.txt` en `unit_tests.txt`.

## Waarom jouw application een vreemde sequence lijkt

`Application_1691306052` bevat 33 afzonderlijke events. Het model/BIG levert hiervoor daadwerkelijk de keten 1→2→…→33. De visualisatie vouwt die keten om de acht lagen: de tweede rij leest van rechts naar links. Dat verklaart het visueel vreemde verloop. De nieuwe figuur voegt eventnummers toe zodat je de pijlen en oorspronkelijke posities kunt volgen.

De alignment heeft fitness 1,0: 33 synchrone moves, nul log-only moves en nul zichtbare model-only moves. Er zijn 83 stille modelmoves. Die stille moves zijn toegestane interne Petri-netstappen, geen ontbrekende geregistreerde werkzaamheden. Rechtstreeks de graph extraheren op de zichtbare events, zonder enige repair, geeft dezelfde 32 edges. Repairs verklaren deze keten dus niet.

Een instance graph bewaart eventinstanties. De twee `W-Call-after-offers-suspend_Role_1` events op posities 19 en 21 blijven twee nodes. De `W-Validate-application-resume_Role_3` events op 27 en 29 ook. Het terugkerende gedrag wordt hier niet tot één node of cyclus samengevouwen: zo'n samenvoeging zou eventidentiteit en de DAG-interpretatie veranderen. SUBDUE moet daarna herhaalde gelabelde subgraphs vinden.

Herhaling is aantoonbaar aanwezig. De graph-path `O-Create-Offer_Role_1 → O-Created_Role_1` komt 3.983 keer voor in 3.053 verschillende cases. De vijf-nodepath `W-Call-after-offers-ate-abort_Role_2 → W-Validate-application-schedule_Role_2 → W-Validate-application-start_Role_2 → A-Validating_Role_2 → O-Returned_Role_2` komt voor in 2.691 cases. `recurring_paths.csv` bevat exacte paden van twee tot vijf nodes, met aantallen occurrences en case support. Dit is een controle op herhaling, geen uitvoering of MDL-ranking van SUBDUE.

## Waarom er zoveel branching verdwijnt

Het opgeslagen rollenmodel heeft slechts één overgang met meerdere uitgaande arcs: `A-Create-Application_Role_3`. Jouw case begint met Role_4 en benut die split niet. BIG leidt 9.931 paren van mogelijke zichtbare opvolgers uit dit model af. Zulke relaties lopen ook via stille stappen en lussen; ze zijn geen bewijs dat een werknemer een andere werknemer werkelijk veroorzaakt of aanstuurt.

De oorspronkelijke audit vergelijkt verschillende labels én verschillende modellen. Daarom heb ik ook opnieuw discovery op de volledige dataset uitgevoerd, met dezelfde IM_CLEAN en noise 0,2, maar zonder de rollen in de labels:

| Model | Labels | Voorbeeldnodes | Voorbeeldedges | Fitness voorbeeld |
|---|---|---:|---:|---:|
| Opgeslagen huidige IM_CLEAN, 0,2 | activiteit + rol | 33 | 32 | 1,0 |
| Nieuwe IM_CLEAN, 0,2, volledig log | alleen activiteit | 33 | 35 | 1,0 |
| Meegeleverd referentiemodel | alleen activiteit | 33 | 37 | Niet opnieuw gemeten in deze benchmark |

Het nieuwe activity-only model heeft één stille AND-split met vier uitgaande arcs. Het aantal splits alleen zegt dus onvoldoende: hun locatie en bereik zijn bepalend. Deze vergelijking ondersteunt dat relabelling de geleerde structuur verandert, maar maakt van de referentie geen gegarandeerde ground truth voor de rollenversie. Alleen de voorbeeldcase is met deze nieuwe activity-only net door BIG gehaald; geen nieuwe volledige activity-only dataset gegenereerd.

Resultaat van die controle: `outputs/diagnostics/activity_control/comparison.json`. De figuur `reference_case_with_roles.png` gebruikt referentie-edges met per-event rolkleuren ter vergelijking; het is geen nieuw gekozen productiemethode.

## Bevindingen die echt aandacht verdienen

1. **De miner was onjuist beschreven.** PM4Py 2.2.16's convenience API kiest IM_CLEAN; de README beweerde expliciet IMf. De documentatie is gecorrigeerd. `--miner-variant imf` selecteert IMf nu expliciet met de juiste eigen noiseparameter en schrijft naar een aparte `_imf`-map. De standaard blijft IM_CLEAN zodat de bestaande resultaten niet stilzwijgend een andere methode krijgen. Een experimentele volledige IMf-discovery is gestopt na ruim vier minuten CPU en circa 3 GB werkgeheugen, zonder modelresultaat. Er is dus geen bewijs dat IMf dit probleem oplost. Zie `miner_comparison/imf_status.json`.

2. **Zes labels ontbreken in het model.** Samen betreffen ze 385 events: fraud-suspend/Role_4 (178), validate-suspend/Role_4 (150), call-incomplete-ate-abort/Role_3 (47), validate-ate-abort/Role_6 (6), handle-leads-ate-abort/Role_1 (3), complete-application-resume/Role_4 (1). Exacte labels staan in `labels_absent_from_model.csv`. Zulke events vereisen log moves/insertion repair; er kunnen daarnaast andere afwijkingen bestaan door de toegestane volgorde. Het ontbreken is niet hetzelfde als verlies van die events uit de graphs.

3. **Werkelijke fout in de meegeleverde BIG.is_path.** De recursieve functie kan een gevonden pad overschrijven met False bij onderzoek van een volgende tak. Reproduceerbaar: edges 1→2, 2→4, 1→3, 3→5; een pad van 1 naar 4 bestaat, maar BIG retourneert False. Dit kan insertion repair beïnvloeden. Het geleverde BIG.py is bewaard; `check_group5_repairs.py` vergelijkt in geheugen met een correcte visited-setzoekfunctie, op exact dezelfde alignment. Voor elk ontbrekend label is de eerste betrokken case getest: alle zes originele repairs reproduceren de opgeslagen edges, en de correcte padzoekfunctie verandert bij deze zes cases geen edge. Hun fitness ligt tussen 0,877 en 0,980. De fout verklaart geen van deze zeven gecontroleerde cases inclusief jouw passende voorbeeld. Dit is geen garantie voor alle overige repairs. Zie `repair_sample.json` en het minimale tegenvoorbeeld in `investigation.json`. Bespreek een wijziging van de geleverde library en controleer de repairgevoelige resultaten voordat je definitieve causale claims maakt.

4. **Dominante rollen zijn profielgroepen, geen bewezen functies.** 37/134 resources hebben minder dan 50% van hun events in hun dominante activiteitengroep. Gewogen ligt 57,66% van alle events in de activiteitengroep die bij de toegewezen rol hoort. Role_7 vertegenwoordigt slechts zes events en Role_8 één event. Gebruik deze labels als afgeleide werkprofielen; zonder inhoudelijke validatie kun je ze niet zomaar ‘acceptatiemedewerker’ of ‘fraudespecialist’ noemen. De mapping is technisch consistent; de keuze voor één dominante rol blijft een methodologische aanname.

5. **Branching is niet automatisch concurrency.** `has_parallelism` is in nieuwe code vervangen door `has_branching`; nieuwe summaries gebruiken `graphs_with_branching_pct`. De historische CSV/JSON blijft intact en bevat nog de oude namen. Ook tijd/workerclaims in de README zijn gecorrigeerd naar de werkelijk opgeslagen run: vier workers, BIG 4.690,7 seconden.

6. **De steekproefoptie en reproduceerbaarheid vragen precisie.** `--max-traces 50` leert nog steeds een nieuw model op 50 traces. De diagnostische single-casescripts gebruiken juist de bestaande volledige net. De eerste case is consistent tussen de chunkrun en losse run; daarmee is geen byte-voor-bytegelijkheid voor alle alignments bewezen. Gelijkwaardige optimale alignments kunnen verschillen.

## Wat is aangepast en wat volgt

Naast de genoemde documentatie, minerkeuze en figuurnummers valideert de pipeline voortaan de graph/eventintegriteit voordat de pickle voor stap 3 wordt opgeslagen. De summary registreert de minerimplementatie, PM4Py-versie en ontbrekende labels. Tests bewaken onder andere de correcte IMf-parameter en het weigeren van verkeerde labels/terugwaartse edges. De meegeleverde diagnostische scripts zijn opgenomen; hun assertions laten een referentie- of caseverschil nu ook werkelijk falen.

Voor SUBDUE is er voldoende technische basis om **nu te beginnen met verkennende mining van activiteit-rolsequenties**. Een keten is daarvoor bruikbare input. Bewaar daarbij gelijke labels over cases heen, afzonderlijke casegrenzen en gerichte edges; globale event-ID's zijn identificatie, geen patroonlabels. Controleer het exacte invoerformaat van de gekozen SUBDUE-implementatie voordat je BIG's .g rechtstreeks gebruikt. SUBDUE zelf is in deze projectmap nog niet geïmplementeerd of uitgevoerd.

Voor definitieve conclusies over parallelle organisatorische samenwerking is deze representatie onvoldoende gevalideerd. Rond dan de interpretatie van de rollen, de repairbeperking en de methodekeuze af, vergelijk gevonden patronen met originele traces/inhoudelijke verwachtingen en maak een gold standard/evaluatie. Activity-only discovery met later toegevoegde rollen is een zinvolle aparte vergelijking, maar verandert de preprocessing/discoveryvolgorde en is hier niet als definitieve methode ingevoerd.

De volledige log is niet opnieuw op alle cases gealigneerd om gemiddelde fitness te berekenen, en de volledige BIG-productierun is niet herhaald. De integriteit van alle bestaande graphs is wel gecontroleerd; alignment/repairgedrag is voor de genoemde zeven cases getest. Dat onderscheid voorkomt dat een structurele PASS wordt verward met inhoudelijk bewezen causaliteit.

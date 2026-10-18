# Handmatige gold standard: werkwijze

De bestanden zijn een **voorstel en beoordelingspakket**, geen door mensen ingevulde gold standard. Er zijn geen handmatige beoordelingen verzonnen. De automatische referentie-uitkomsten zijn apart opgeslagen. Gebruik die niet als bewijs dat een onafhankelijke handmatige evaluatie is afgerond.

## 1. Spreek eerst af wat jullie beoordelen

Er zijn twee verschillende vragen:

- **Patroonrelevantie:** beschrijft het gevonden patroon herkenbaar gedrag rond de gekozen activiteit-roltoewijzing? Dit beoordeel je voor ieder gevonden patroon in `outputs/evaluation/manual_pattern_relevance.csv`. Precision is het aandeel relevante patronen onder de beoordeelde gevonden patronen. Een gevonden patroon dat niet in jullie eerste lijstje stond, is niet automatisch fout.
- **Terugvinden van vooraf gedefinieerde motieven:** bevat een trace een verwacht motief, en vindt de pipeline dat terug? Dit beoordeel je met `manual_annotations.csv`. Hieruit volgen precision en recall voor de binaire trace-motiefdetectie. Recall van patroontypes is daarnaast het aandeel goedgekeurde doelmotieven dat in minstens één gevonden patroon terugkomt.

De gegenereerde acht kandidaatmotieven zijn sequenties van activiteit-rollabels. Ze zijn gesuggereerd op basis van de eventnamen en de eerdere verkennende audit, niet onafhankelijk door een domeinexpert geselecteerd. Voor een sterkere evaluatie ontwikkelt een teamlid aanvullende motieven uit oorspronkelijke traces voordat die persoon de SUBDUE-resultaten bekijkt. Voeg niet achteraf alleen motieven toe die SUBDUE toevallig vindt.

Deze beperkte lijst is geen uitputtende beschrijving van al het procesgedrag. Noem de scope expliciet. De huidige automatische referentietest ondersteunt padmotieven; algemene vertakkende goldgraphs vereisen een expliciete, onafhankelijk onderbouwde annotatieprocedure en uitbreiding van die referentietest.

## 2. Bekijk en bevestig de motiefdefinities

Open `evaluation/gold_standard_draft.json`. Per kandidaat vind je een naam, nodes met exacte labels en gerichte edges. Controleer met je team of de labels en rollen inhoudelijk zinvol zijn. `Role_2` is een ontdekt profiel, geen officieel functielabel.

De voorgestelde referentiedefinitie is **aaneengesloten events in de oorspronkelijke opgeslagen eventvolgorde met exact dezelfde activiteit-rollabels**. Dit is een toetsbare sequentiedefinitie, geen bewering over echte causaliteit. Besluit vóór de beoordeling of dit de gewenste definitie is. Wijzig definities niet na het bekijken van de scores zonder die wijziging als nieuwe evaluatie te registreren.

Voor een goedgekeurde definitie zet je `approved` op `true` en vul je `reviewed_by` in. De software maakt deze menselijke goedkeuringen niet voor jullie aan.

## 3. Beoordeel de oorspronkelijke events

Open `outputs/evaluation/annotation_cases.csv`: hierin staan de geselecteerde cases en de reden van selectie. De selectie combineert een reproduceerbare hashselectie, alle acht branching cases, de tien cases met de laagste fitness en de eerder besproken application. Dit is een gerichte steekproef, geen willekeurige representatieve schatting van de hele populatie.

Open per case `outputs/evaluation/annotation_packets/<Application-id>.csv`. Je ziet oorspronkelijke activiteit, rol, resource, timestamp en eventpositie. De packets bevatten geen SUBDUE-voorspellingen. Houd `automatic_suggestions_NOT_manual.csv`, de gevonden patronen en de automatische scores gesloten tijdens onafhankelijke trace-annotatie.

Vul in `outputs/evaluation/manual_annotations.csv` per case en motief:

- `present`: `1` wanneer het afgesproken motief voorkomt, anders `0`. Laat het leeg als je nog niet hebt beoordeeld; leeg is nooit automatisch negatief.
- `reviewer`: de naam of een vaste beoordelaarcode.
- `reviewed_at`: beoordelingsdatum.
- `evidence_event_positions`: de posities van een positief voorkomen, bijvoorbeeld `23 24 25`.
- `reason`: korte toelichting, zeker bij twijfel of uitsluiting.

Voorbeeld van invullen: GS04 beschrijft `W-Validate-application-schedule_Role_2 → W-Validate-application-start_Role_2 → A-Validating_Role_2`. In `Application_1691306052` staan deze op posities 23, 24 en 25. Na eigen controle kan een beoordelaar voor deze cel `present=1` en `evidence_event_positions=23 24 25` invullen. Dit voorbeeld is een uitleg, niet alvast een namens jullie ingevulde beoordeling.

Laat bij voorkeur twee teamleden een vooraf afgesproken deel onafhankelijk beoordelen. Bespreek verschillen en bewaar de oorspronkelijke beoordelingen of een geschillenlog. Die tweede beoordeling en interbeoordelaarsovereenstemming zijn nog niet uitgevoerd.

## 4. Beoordeel ook alle gevonden patronen

Open de SVG's in `outputs/step3_patterns/figures/` en de echte eventvoorkomens in `occurrences.csv`. Vul `manual_pattern_relevance.csv` in met `relevant=1` of `0`, een reviewer en een inhoudelijke reden. Bepaal vooraf wat relevant betekent: bijvoorbeeld minstens één herkenbare werkfase of overdracht, correct rolgebruik en geen louter administratieve start/end-combinatie. Pas deze criteria consequent toe, ook op patronen die niet in de voorgestelde acht motieven staan.

## 5. Bereken de scores opnieuw

Vanuit de projectmap, met de Python 3.9-omgeving actief:

```powershell
python main.py evaluate
python main.py paper-report
```

`evaluate` bewaart een bestaand handmatig formulier; het vult de lege beoordelingen niet automatisch in. Bewaar vóór definities wijzigen wel een versie van je ingevulde formulieren en de oude outputs.

In `outputs/evaluation/manual_evaluation.json` vind je de beoordeelde en openstaande cellen, precision/recall/F1 op beoordeelde trace-motiefcellen, precision van beoordeelde gevonden patronen en recall van goedgekeurde doelmotieven. Zolang niemand heeft beoordeeld staan handmatige scores op `null` en de status op `pending_human_review`.

Formules voor trace-motiefcellen: precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = 2PR/(P+R). Lege beoordelingen tellen niet mee. Een nulnoemer wordt expliciet als ongedefinieerd gemarkeerd; de numerieke conventie in de export is dan 0.

## 6. Rapporteer eerlijk in je paper

Rapporteer de bron van de motieven, de gekozen semantiek, aantal traces/motieven/beoordelaars, selectieprocedure, matchingregel, beoordelingscriteria en eventuele geschillen. De actuele automatische benchmark vergelijkt contigu gematchte labelsequenties met teruggevonden motieven; dat is een **automatische proxy**, niet de gevraagde handmatige gold standard. De benchmark beoordeelt bovendien niet de relevantie van alle overige gevonden patronen. Neem deze proxycijfers dus niet over als definitieve handmatige precision/recall.

De grote conformance-analyse toetst passendheid bij het op dezelfde data geleerde Petri-net. Ook die vervangt geen handmatige patroonevaluatie.

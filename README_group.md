# README for the group: choices, results and what is left

`README.md` explains how to install and run the code. This file is for us:
**why** we made the choices we made, **what came out**, and **what the next
person should do with it** for the paper and the poster. Keep it up to date
when you change something.

> Status (2026-10-31): the code is done and everything in `output/` comes from
> one full re-run with the final settings (`org:resource` → 8 roles, lifecycle
> collapsed, noise 0.2, beam 10, top 20, `PYTHONHASHSEED=0`), followed by
> `beam_table.py` and `figures.py`. The next job is **writing the paper and the
> poster** from sections 3-5 below.

---

## 1. Assignment → where it is

| Assignment asks | Where | Output |
|---|---|---|
| Show all log attributes, user selects one, label = `activity_attribute` | `main.py` step 1 (`InstanceGraphStep.ask_attribute`) | `output/instance graphs/` |
| Inductive Miner → Petri net → BIG instance graphs → networkx with unique node ids | step 1 | `instance_graphs_pm4py.pkl`, `petri_net_pm4py.pnml` |
| SUBDUE patterns, support, trace × pattern matrix, visualizations | step 2 (`PatternMiningStep`) | `output/patterns/` |
| Evaluate against a manual gold standard, at least precision and recall | step 4 (`SyntheticValidationStep`) + `data/synthetic/` | `output/synthetic validation/` |
| Pattern statistics (FREQ, REP, COV, DIV), fitness | step 3 (`EvaluationStep`) | `output/evaluation/` |
| Figures like Figure 1 (trace → instance graph → patterns) | `figures.py` | `output/figures/`, `output/synthetic validation/<eval>/figures/` |
| Table like Table 6 of the reference paper (beam 4/10/20) | `beam_table.py` | `output/beam_table/` |
| pm4py 2.2.16, one main, no absolute paths, requirements.txt | `requirements.txt`, `main.py` | — |

---

## 2. Choices and why

### Data and labels
- **Attribute: `org:resource`, grouped into roles** (pm4py role discovery,
  threshold 0.65). 134 users give thousands of labels; BIG becomes very slow
  and SUBDUE finds nothing general. 8 roles give 106 labels.
- **Lifecycle collapse** for work items (`W-...-start/suspend/complete` → one
  event). It shortens every trace and is the biggest speed-up for BIG. A role
  change inside a work item stays two events (that *is* a handover).
- **`_` → `-` in activity names**, so the first `_` of a label always
  separates activity and role (`A-Submitted_Role_4`).

### Model and instance graphs
- **Inductive Miner noise 0.2** (team decision; ProM's default). Was 0.4.
- **BIG runs once per trace variant** (1,423 variants for 3,093 traces) and
  the graph is copied to every trace of that variant. BIG's result depends
  only on the label sequence, so this is exact; instance-graph fitness is 1.0
  for every trace, which confirms the mapping.
- `main.py` works with the **unchanged Canvas `BIG.py`** (and with the
  sped-up version, if someone has it).

### Patterns
- **SUBDUE beam 10** (team decision; was 4). `beam_table.py` shows beam 4 and
  20 next to it.
- **Top 20 patterns, 1 iteration.** The SUBDUE hierarchy (iterations > 1:
  compress the graph with the best pattern and search again) is *not used*;
  the team decided it has no priority. Note: step 2 still asks for
  "iterations" (default 3) but only the first iteration's patterns are kept.
- **Support / trace × pattern matrix by exact subgraph check**, not by
  SUBDUE's own instances: SUBDUE only reports non-overlapping instances and
  misses cases. Rows are application ids.
- **Subs** = every pattern SUBDUE found in its search; **% top subs** = 20 /
  Subs. Done by letting SUBDUE report everything (its `numBest` only trims the
  report, it does not change the search). In the paper the number of top subs
  differs per beam, so our column is "the same idea", not the exact same
  definition - say so in the paper.

### Evaluation
- **No gold standard for BPI 2017.** We do not know the real roles there, so
  BPI is the *real-world application*, reported with pattern statistics
  (support, REP, COV, DIV) and the beam table.
- **Synthetic log with a gold standard** (`data/synthetic/`, hand-made, 30
  cases, 4 departments, 5 planted patterns, see `data/synthetic/README.md`).
  The gold standard is fixed by the design, independent of SUBDUE.
- **Two synthetic evaluations**, so a missing pattern can be traced to its
  cause:
  1. *Known roles*: labels from the `department` column → tests BIG + SUBDUE.
  2. *Full pipeline*: labels from the employees, grouped by pm4py role
     discovery (as on BPI) → tests role discovery + BIG + SUBDUE. Discovered
     roles are mapped to the department most of their events come from.
- **Three levels**: a = are the gold patterns in the instance graphs (BIG
  check); b = do SUBDUE's top patterns match the gold patterns (precision,
  recall, F1); c = are those patterns found in the right cases.
- **Containment matching is the headline** (a SUBDUE pattern counts when it
  contains a gold pattern, or is contained in it with ≥ 2 edges); exact
  matching is reported too. SUBDUE prefers big patterns that glue practices
  together, so exact matching is almost always 0.

---

## 3. Results

### 3.1 BPI 2017 (real-world application)

| What | Value | File |
|---|---|---|
| Roles | 134 users → 8 roles (Role_1: 86 users, Role_2: 21, Role_3: 18, Role_4–8: 1–3 each) | `output/instance graphs/resource_roles.csv` |
| Labels / events | 106 labels; 88,638 of 124,866 events kept after lifecycle collapse | console / `generation_settings.json` |
| Petri net fitness (alignments) | mean 0.999, 3,014 of 3,093 traces perfect, min 0.92 | `output/evaluation/summary.json` |
| Instance graph fitness | 1.0 for all 3,093 traces | same |
| Instance graphs | 3,093, on average 28.7 events; **none has a parallel split** (all sequential) | `instance_graphs_pm4py.pkl` |
| SUBDUE search | Subs = 334, top 20 = 5.99 %, 24 min (beam 10) | `output/patterns/subdue_search.json` |
| Patterns | 20, 7–19 edges, support 28.7 %–74.7 % of cases | `output/patterns/patterns.csv` |
| COV / DIV | 0.40 / 0.26 | `output/evaluation/pattern_evaluation/summary.json` |
| Cases with no pattern | 778 of 3,093 (25 %) | `output/patterns/trace_pattern_matrix.csv` |

**Interpretation.** All 20 patterns describe the same handover: the offer team
(**Role_1**) creates and sends the offer (`O-Create-Offer → O-Created →
O-Sent-mail-and-online`), completes the application and calls the customer
(`W-Call-after-offers`), and then the work item is passed to the validation
team (**Role_2**: `W-Call-after-offers_Role_2 → W-Validate-application_Role_2
→ A-Validating → O-Returned`). P18 and P20 (≈30 % of cases) also contain
Role_4 (intake). The patterns overlap heavily (DIV 0.26): they are variations
and sub-parts of one practice. **Role_3** (who performs the final denial,
`A-Denied`) appears in **no** pattern, although every case ends with a denial.

### 3.2 Synthetic log (validation, gold standard)

| Level | Known roles (eval 1) | Discovered roles (eval 2) |
|---|---|---|
| Role discovery: employees in the role of their own department | — | **9 of 9 (100 %)**: 4 departments + System recovered exactly |
| a. gold patterns in the instance graphs (recall) | 1.0 | 1.0 |
| b. containment precision / recall / F1 | 1.0 / 0.8 / 0.89 | 1.0 / 0.8 / 0.89 |
| b. exact recall | 0.0 | 0.0 |
| b. edge-level precision / recall | 0.82 / 0.82 | 0.82 / 0.82 |
| c. mean F1 of the cases of the best pattern | 0.78 | 0.78 |
| COV / DIV | 0.86 / 0.28 | 0.86 / 0.28 |
| Subs / % top subs | 110 / 18.2 % | 110 / 18.2 % |

Per gold pattern (`output/synthetic validation/comparison/comparison.csv`):
G1–G4 are **found in both** (case F1 0.94–1.0); **G5** (denial: Credit denies,
Intake notifies the customer, 10 of 30 cases) is **missed by SUBDUE** - it is
in the instance graphs (level a = 1.0) but in none of the top 20 patterns.

**Interpretation.**
- Petri net + BIG are not the problem: every planted pattern is in exactly the
  right instance graphs, also with noise 0.2.
- Role discovery is not the problem either *on this log*: pm4py finds the 4
  departments exactly, so eval 2 = eval 1. (Our synthetic employees each work
  in one department only; on BPI people overlap more, so this is a best case.)
- The loss is in **SUBDUE**: it ranks by compression, so the most frequent
  behaviour (the approved path, 2/3 of the cases) fills the top 20 with
  overlapping variants and the rarer denial path never makes it. This is the
  same effect as Role_3 / denial missing on BPI.
- Containment precision (1.0) is flattering: the one-edge G1 is contained in
  almost every pattern. Edge-level (0.82) and level c (0.78) are more honest.
- Exact recall 0: SUBDUE glues neighbouring practices together into bigger
  patterns (e.g. P2 = G1+G2+G3+G4 in one), so a discovered pattern almost
  never equals one gold pattern.

### 3.3 Beam table (Table 6 style)

`output/beam_table/beam_table.csv` and `beam_table.tex` (DIV ×100, as in the paper):

| Setting | Beam | Subs | % top subs | COV (%) | DIV | REP [first 10] {all} | Time | P / R / F1 |
|---|---|---|---|---|---|---|---|---|
| Synthetic, known roles | 4 | 56 | 35.7 | 82.2 | 29.6 | [70.0] {68.7} | 0.3 s | 1.0 / 0.8 / 0.89 |
| | 10 | 110 | 18.2 | 85.5 | 27.8 | [75.3] {62.0} | 0.6 s | 1.0 / 0.8 / 0.89 |
| | 20 | 175 | 11.4 | 85.5 | 31.1 | [77.3] {62.0} | 0.8 s | 1.0 / 0.8 / 0.89 |
| Synthetic, discovered roles | 4/10/20 | identical to known roles | | | | | | |
| BPI 2017 | 4 | 90 | 22.2 | 42.7 | 28.5 | [64.0] {59.0} | 10 min | — |
| | 10 | 334 | 6.0 | 40.0 | 25.9 | [64.0] {61.0} | 16 min | — |
| | 20 | 717 | 2.8 | 40.0 | 25.9 | [64.0] {61.0} | 19 min | — |

**Interpretation.** A wider beam makes SUBDUE look at many more patterns
(BPI: 90 → 334 → 717) and costs more time, but the **top 20 hardly change**:
on BPI beam 10 and 20 give the same COV/DIV/REP, and on the synthetic log
G5 is missed at every beam. So the beam is not what limits us; the
compression-based ranking (and keeping only the top 20 of one iteration) is.
Beam 10 is a reasonable choice: beyond it nothing changes but run time.

---

## 4. For the paper and poster

**Figures** (all already made):

| Figure | File |
|---|---|
| Figure-1 style, BPI (trace → instance graph → patterns), most common variant (193 cases) | `output/figures/Application_81204346/figure1.png` (+ `instance_graph.png`, `P*_in_case.png`) |
| One BPI pattern highlighted in the shortest cases that contain it | `output/figures/P1/` |
| Figure-1 style, synthetic approved case (parallel credit check visible!) | `output/synthetic validation/eval1_known_roles/figures/C01/figure1.png` |
| Synthetic denied case (G5 is in the graph, but no pattern covers it) | `.../eval1_known_roles/figures/C15/` |
| Synthetic deviation (Check-credit done by Offers) | `.../eval1_known_roles/figures/C25/` |
| Gold patterns G1–G5 | `output/synthetic validation/gold/` |
| Known vs discovered roles per gold pattern | `output/synthetic validation/comparison/comparison.png` |
| Trace × pattern matrix (most common combinations) | `output/patterns/trace_pattern_heatmap.png` |
| All BPI patterns | `output/patterns/P1.png` … `P20.png` |

Need another case? `python figures.py` → `L` lists good candidates → `C <case id>`.

**Tables**: section 3.1 (BPI statistics), 3.2 (synthetic, both evaluations),
3.3 (beam table; LaTeX in `output/beam_table/beam_table.tex`).

**Suggested story for the paper.**
1. Method: attribute selection → roles → IM (0.2) → BIG → SUBDUE (beam 10).
2. Validation on the synthetic log, in two evaluations: BIG reproduces every
   planted pattern (a = 1.0); role discovery recovers the departments exactly;
   SUBDUE finds 4 of 5 patterns (recall 0.8) and misses the less frequent
   denial handover. Because eval 1 = eval 2, the miss is SUBDUE's, not the
   role discovery's - that is exactly why we did two evaluations.
3. Application to BPI 2017: the dominant practice is the offer → validation
   handover between Role_1 and Role_2 (in ~70 % of the cases); the denial by
   Role_3 is not found, which the synthetic result explains.
4. Beam study: more beam = more candidates, same top patterns.

---

## 5. Limitations (write these in the paper)

- **SUBDUE favours frequent behaviour**: less frequent but meaningful
  patterns (denial handover, G5 / Role_3) do not reach the top 20 at any beam.
  The SUBDUE hierarchy (iterations > 1, compress and search again) could help
  but is not used (team decision, no priority).
- **Redundant patterns** (low DIV, 0.26–0.31): the top 20 are mostly
  variations of one practice.
- **No parallelism in BPI instance graphs**: all 3,093 are sequential, so the
  BPI patterns are chains, not diamonds like Figure 1 (the synthetic log does
  have parallelism, and BIG finds it there).
- **No gold standard for BPI**; the synthetic validation is a best case
  (small, clean, perfectly separated departments → role discovery is trivially
  right there). It shows the method *can* work, not how well it works on BPI.
- **Containment precision is optimistic** (see 3.2); report edge-level and
  case-level scores next to it.
- **% top subs** is 20 / Subs (fixed-size top list), not exactly the paper's
  definition.
- The Petri net is discovered with noise 0.2, so 79 BPI traces don't fit it
  perfectly; BIG repairs those graphs (instance-graph fitness 1.0).
- **Roles are skewed**: Role_1 has 86 of 134 users, five roles have ≤ 3 users.

## 6. Open ideas (only if time is left)

- SUBDUE iterations > 1 (keep the patterns of every iteration) to find the
  denial pattern.
- A harder synthetic log (employees working in two departments) so that eval 2
  can actually differ from eval 1.
- Role similarity threshold other than 0.65 on BPI.

---

## 7. How to rerun

```bash
python main.py        # A = steps 1-4 with defaults (Enter at every question)
python beam_table.py  # after steps 1 and 4
python figures.py     # pick a case by hand, see README.md
```

Set `PYTHONHASHSEED=0` first for a reproducible Petri net.

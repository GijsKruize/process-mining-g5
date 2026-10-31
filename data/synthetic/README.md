# Synthetic validation data

This folder holds a small, **hand-made** event log and its **gold standard**.
Together they let us measure how well our pipeline (step 1 instance graphs →
step 2 SUBDUE patterns) finds organizational patterns, with precision and
recall, as the assignment asks.

| File | What | Written by |
|---|---|---|
| `synthetic_log.csv` | 30 loan applications, 304 events | hand (this document is the spec) |
| `synthetic_gold_standard.csv` | the 5 organizational patterns we put into the log on purpose, and in which cases | hand (this document is the spec) |
| `README.md` | this explanation | — |

Step 4 of `python main.py` ("Synthetic validation") converts the CSV to XES,
runs steps 1 and 2 on it, and compares SUBDUE's patterns with the gold standard.
It does this twice:

1. **Known roles** (`eval1_known_roles/`): events labeled with the
   `department` column, so the roles are given and only BIG and SUBDUE are
   tested.
2. **Full pipeline** (`eval2_full_pipeline/`): events labeled with the
   employee (`resource`), grouped into roles by pm4py's role discovery, as on
   BPI 2017. Each discovered role is mapped to the department most of its
   events come from before scoring.

`comparison/` puts both side by side, per gold pattern, so we can see whether
a missing pattern is caused by the role discovery or by BIG/SUBDUE. All
results go to `output/synthetic validation/`, never over the BPI 2017 results.

---

## 1. Why a synthetic log?

On the real BPI 2017 log nobody knows which work patterns are "really" there,
so we cannot say whether SUBDUE's 20 patterns are right. In a log we design
ourselves we **know** the organizational behaviour, because we put it there.
The gold standard is fixed **before** and **independent of** what SUBDUE
predicts. It comes from the design below, not from looking at SUBDUE's output.

We keep the log small (30 cases) on purpose: every case can be checked by
hand, and the whole pipeline runs on it in seconds.

---

## 2. The process: a small loan application

Four departments with their employees (plus a technical `System` user for the
artificial start and end events):

| Department | Employees (`resource`) | Activities |
|---|---|---|
| Intake | Anna, Bram | Submit-application, Check-documents, Notify-customer |
| Credit | Carla, Daan, Eva | Check-credit, Verify-income, Decide, Deny |
| Offers | Fleur, Gijs | Create-offer, Send-offer |
| BackOffice | Hanna | Sign-contract, Archive |
| System | System | start, end |

The normal flow:

```
start → Submit-application → Check-documents ─┬─ Check-credit ──┬─ Decide ─┬─ Create-offer → Send-offer → Sign-contract → Archive → end   (approved)
        (Intake)             (Intake)          └─ Verify-income ─┘ (Credit) └─ Deny → Notify-customer → end                                (denied)
                                                  (Credit, in parallel)        (Credit)  (Intake)
```

- **Check-credit and Verify-income run in parallel.** The log contains both
  orders, so the Inductive Miner finds an AND and the instance graph gets a
  diamond, like the B–C–D–G part of Figure 1 in the assignment.
- **A denial goes back to Intake.** Credit denies and Intake tells the
  customer, so work is handed back from one department to another.

### Naming rules (important, BIG's output is space separated)
- No spaces and no `_` in activity, resource or department names; use `-`.
  The pipeline joins them with `_`: label = `<activity>_<department>`, e.g.
  `Check-credit_Credit`.
- Activity names are exactly as in the table above (case sensitive).

---

## 3. `synthetic_log.csv`: format and content

One row per event, events of a case in time order, cases one after another.

| Column | Example | Meaning |
|---|---|---|
| `case_id` | `C01` | application id, `C01` … `C30` (becomes `case:concept:name`) |
| `activity` | `Check-credit` | activity name (becomes `concept:name`) |
| `resource` | `Carla` | employee who did it (becomes `org:resource`) |
| `department` | `Credit` | department of that employee **for this event** (becomes `department`) |
| `timestamp` | `2026-01-05 09:30:00` | becomes `time:timestamp` |

`resource` and `department` are deliberately two separate attributes. When
step 1 asks which attribute to analyse, we choose `department`. Choosing
`resource` instead gives one label per employee per activity, which is the
"spaghetti" effect the assignment describes.

### 3.1 Variants: which case follows which path

"Order a" = Check-credit before Verify-income, "order b" = the other way round.

| Variant | Cases | # | Path | Events per case |
|---|---|---|---|---|
| **V1** approved | C01–C08 | 8 | normal approved flow, order a | 11 |
| **V2** approved | C09–C14 | 6 | normal approved flow, order b | 11 |
| **V3** denied | C15–C19 | 5 | normal denied flow, order a | 9 |
| **V4** denied | C20–C24 | 5 | normal denied flow, order b | 9 |
| **V5** deviation: wrong department | C25 (a), C26 (b) | 2 | approved, but **Check-credit is done by Fleur (Offers)** | 11 |
| **V6** deviation: skipped step | C27 (a), C28 (b) | 2 | approved, but **Sign-contract is skipped** (Send-offer → Archive) | 10 |
| **V7** deviation: no handover | C29 (a), C30 (b) | 2 | denied, but **Notify-customer is done by the Credit employee** instead of Intake | 9 |
| | | **30** | | **304 events** |

The deviations V5–V7 each break exactly one gold pattern (see section 4).
They test that the pipeline does not report a pattern in cases where it is
not there.

### 3.2 Who does what (fixed rules, no randomness)

Within one case, one employee per department does all of that department's
work (they are the case owner):

| Department | Rule (n = case number, e.g. C07 → 7) |
|---|---|
| Intake | odd n → Anna, even n → Bram |
| Credit | n mod 3 = 1 → Carla, 2 → Daan, 0 → Eva |
| Offers | odd n → Fleur, even n → Gijs |
| BackOffice | Hanna |
| System | System (start and end only) |

Exceptions are only the deviations: in C25/C26 `Check-credit` has resource
`Fleur`, department `Offers`. In C29/C30 `Notify-customer` has the case's
Credit employee as resource, department `Credit`.

### 3.3 Timestamps

Case Cn starts on day n of January 2026 (C01 → 2026-01-01) at 09:00. Every next
event of the case is **10 minutes** later. The exact times do not matter to the
pipeline. They only need to keep the events in order.

### 3.4 Example: case C01 (V1) and C15 (V3) written out

```csv
case_id,activity,resource,department,timestamp
C01,start,System,System,2026-01-01 09:00:00
C01,Submit-application,Anna,Intake,2026-01-01 09:10:00
C01,Check-documents,Anna,Intake,2026-01-01 09:20:00
C01,Check-credit,Carla,Credit,2026-01-01 09:30:00
C01,Verify-income,Carla,Credit,2026-01-01 09:40:00
C01,Decide,Carla,Credit,2026-01-01 09:50:00
C01,Create-offer,Fleur,Offers,2026-01-01 10:00:00
C01,Send-offer,Fleur,Offers,2026-01-01 10:10:00
C01,Sign-contract,Hanna,BackOffice,2026-01-01 10:20:00
C01,Archive,Hanna,BackOffice,2026-01-01 10:30:00
C01,end,System,System,2026-01-01 10:40:00
...
C15,start,System,System,2026-01-15 09:00:00
C15,Submit-application,Anna,Intake,2026-01-15 09:10:00
C15,Check-documents,Anna,Intake,2026-01-15 09:20:00
C15,Check-credit,Eva,Credit,2026-01-15 09:30:00
C15,Verify-income,Eva,Credit,2026-01-15 09:40:00
C15,Decide,Eva,Credit,2026-01-15 09:50:00
C15,Deny,Eva,Credit,2026-01-15 10:00:00
C15,Notify-customer,Anna,Intake,2026-01-15 10:10:00
C15,end,System,System,2026-01-15 10:20:00
```

(15 mod 3 = 0, so the Credit employee of C15 is Eva.)

### 3.5 What step 1 should produce on this log (sanity checks)

- The attribute table lists `org:resource`, `department` (and the
  non-selectable `concept:name`, `case:concept:name`, `time:timestamp`).
  `department` has 5 distinct values, `org:resource` 9 (8 employees + System).
- With `department` selected: **15 distinct labels**:
  `start_System`, `Submit-application_Intake`, `Check-documents_Intake`,
  `Check-credit_Credit`, `Check-credit_Offers`, `Verify-income_Credit`,
  `Decide_Credit`, `Create-offer_Offers`, `Send-offer_Offers`,
  `Sign-contract_BackOffice`, `Archive_BackOffice`, `Deny_Credit`,
  `Notify-customer_Intake`, `Notify-customer_Credit`, `end_System`.
- 30 instance graphs. Every graph has the parallel diamond after
  `Check-documents`. The expected instance graph of C01:

```
start_System
  → Submit-application_Intake
  → Check-documents_Intake ──┬→ Check-credit_Credit ──┬→ Decide_Credit
                             └→ Verify-income_Credit ─┘
  → Create-offer_Offers → Send-offer_Offers
  → Sign-contract_BackOffice → Archive_BackOffice
  → end_System
```

  C09 (order b) must give the **same** graph: the order of parallel work is
  not visible in an instance graph. This is a quick check that BIG did its job.

---

## 4. `synthetic_gold_standard.csv`: the patterns we put in

### 4.1 Format

| Column | Meaning |
|---|---|
| `id` | `G1` … `G5` |
| `name` | short name, used in tables and figures |
| `description` | the organizational behaviour in words |
| `edges` | the pattern as directed edges between labels: `A -> B; C -> D` (separator `; `) |
| `expected_cases` | the cases that contain the pattern by design; ranges `C01-C14` and single cases, separated by `;` |

`start_System` / `end_System` are never part of a gold pattern: they are
technical events, not organizational behaviour.

### 4.2 Content

| id | name | edges | kind | expected_cases | # |
|---|---|---|---|---|---|
| **G1** | Intake handles the application | `Submit-application_Intake -> Check-documents_Intake` | work within one department | `C01-C30` | 30 |
| **G2** | Parallel credit assessment | `Check-documents_Intake -> Check-credit_Credit; Check-documents_Intake -> Verify-income_Credit; Check-credit_Credit -> Decide_Credit; Verify-income_Credit -> Decide_Credit` | handover Intake → Credit, parallel work | `C01-C24;C27-C30` | 28 |
| **G3** | Offer handling | `Decide_Credit -> Create-offer_Offers; Create-offer_Offers -> Send-offer_Offers` | handover Credit → Offers | `C01-C14;C25-C28` | 18 |
| **G4** | Closing by the back office | `Send-offer_Offers -> Sign-contract_BackOffice; Sign-contract_BackOffice -> Archive_BackOffice` | handover Offers → BackOffice | `C01-C14;C25-C26` | 16 |
| **G5** | Denial handed back to Intake | `Decide_Credit -> Deny_Credit; Deny_Credit -> Notify-customer_Intake` | handover Credit → Intake | `C15-C24` | 10 |

The CSV file contains exactly these rows (with `description` filled in from
section 2), e.g.:

```csv
id,name,description,edges,expected_cases
G1,Intake handles the application,"An Intake employee submits and then checks the documents of the application.",Submit-application_Intake -> Check-documents_Intake,C01-C30
G2,Parallel credit assessment,"After Intake has checked the documents, Credit checks the credit and verifies the income in parallel, and then decides.",Check-documents_Intake -> Check-credit_Credit; Check-documents_Intake -> Verify-income_Credit; Check-credit_Credit -> Decide_Credit; Verify-income_Credit -> Decide_Credit,C01-C24;C27-C30
...
```

### 4.3 Why each deviation removes exactly one pattern

| Cases | Deviation | Pattern that is **not** there | Why |
|---|---|---|---|
| C25, C26 | Check-credit by Offers | G2 | the diamond contains `Check-credit_Offers`, not `Check-credit_Credit` |
| C27, C28 | Sign-contract skipped | G4 | there is no `Sign-contract_BackOffice` node |
| C29, C30 | Notify by Credit | G5 | `Deny_Credit -> Notify-customer_Credit`: no handover to Intake |
| C15–C24, C29, C30 | denied | G3, G4 | no offer is made in a denied case |
| C01–C14, C25–C28 | approved | G5 | no denial |

The resulting expected trace × pattern matrix (1 = pattern is in the case):

| Cases | G1 | G2 | G3 | G4 | G5 |
|---|---|---|---|---|---|
| C01–C14 (V1, V2) | 1 | 1 | 1 | 1 | 0 |
| C15–C24 (V3, V4) | 1 | 1 | 0 | 0 | 1 |
| C25–C26 (V5) | 1 | 0 | 1 | 1 | 0 |
| C27–C28 (V6) | 1 | 1 | 1 | 0 | 0 |
| C29–C30 (V7) | 1 | 1 | 0 | 0 | 0 |

---

## 5. How the results are scored

Step 4 reports three levels, so we can see **where** an error comes from:

**a. Are the gold patterns in the instance graphs?** (tests steps 1 and 2: Petri net + BIG, not SUBDUE)
For every gold pattern and every case: does the pattern occur in the case's
instance graph (subgraph check with the same labels)? Compared with
`expected_cases`, this gives precision and recall per gold pattern.
**Expected: 1.0 everywhere.** If it is not 1.0, the problem is in the Petri net or BIG.

**b. Does SUBDUE find the gold patterns?** (main result)
- *Precision* = share of SUBDUE's patterns that match some gold pattern.
- *Recall* = share of gold patterns matched by at least one SUBDUE pattern.
- *F1* = combination of the two. Also *precision@k* (k = 5, 10, 20), because
  SUBDUE returns a ranked list.
- Reported with two match criteria:
  - **exact**: the SUBDUE pattern is the same graph with the same labels.
  - **containment** (headline): the SUBDUE pattern contains the gold pattern,
    or is contained in it with at least 2 edges.

  Containment is the headline figure because SUBDUE prefers large patterns
  that compress a lot. On this log it will probably find something like
  `Submit → Check-documents → diamond → Decide` (G1 and G2 glued together, 28
  cases), which is correct behaviour but never an *exact* match.

**c. Are the patterns found in the right cases?**
For each gold pattern, take the SUBDUE pattern that matches it best and
compare its column of the trace × pattern matrix with the expected column
above. That gives precision and recall per pattern.

---

## 6. Changing the data

If you add or change cases, update **in this order**: the variant table
(3.1), the CSV, `expected_cases` in the gold standard (4.2), and the expected
matrix (4.3). The gold standard must keep following from the design, never
from what SUBDUE happens to find. Otherwise the evaluation measures nothing.

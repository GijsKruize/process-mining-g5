GROUP 5 — SAFE SINGLE-CASE DEBUGGING
===================================
All commands run from your process-mining-g5 repository root with its Python 3.9 virtual environment active.

1. Existing outputs inspection; does NOT recompute BIG:
   python main.py show-graph --case Application_1691306052 --output outputs/figures/first_role.svg

2. Audit the existing role-labelled instance graphs against the EXACT XES that BIG read:
   python scripts/diagnostics/audit_group5_outputs.py --log outputs/step1_preprocessing/org_resource_roles/relabeled_log.xes --graphs outputs/step2_instance_graphs/org_resource_roles/instance_graphs.pkl --roles outputs/step1_preprocessing/org_resource_roles/resource_roles.csv --case Application_1691306052 --summary outputs/diagnostics/audit_all_cases.csv

3. Independently rerun BIG for the first case with the FULL pre-existing role-labelled Petri net (does NOT mine a new net):
   python scripts/diagnostics/test_group5_single_case.py

4. Optional activity-only reference benchmark, using the original supplied log, PNML, and BIG:
   python scripts/diagnostics/test_group5_reference_big.py

5. Existing small unit tests:
   python -m unittest discover tests -v

PASS checks: First case 33 events/nodes, same labels and order; 3,093 total graphs, 124,866 total nodes; global node IDs unique; DAG; connected; correct resource-role mapping; no loss of events.
IMPORTANT: a passing audit does NOT prove that BIG's edges are causally correct. Check alignment fitness, absent Petri net labels and branching behaviour.
IMPORTANT: `python main.py instance-graphs --max-traces 50` mines a NEW model from 50 traces. This is not the same as using the full Petri net with one case.
IMPORTANT: the provided reference .g is activity-only; do not expect the role-based model to have identical edges.
NOTICE: `pickle` should be loaded only from your own/trusted project output.

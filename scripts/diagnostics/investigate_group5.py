"""Reproducible, read-only investigation of existing step 1/2 artifacts.
Writes diagnostics separately; never replaces the production models or graphs.
Run with the project's Python 3.9 environment, from the repository root.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import argparse
import json
from collections import Counter
from itertools import zip_longest
from decimal import Decimal, InvalidOperation
from dateutil.parser import isoparse
from pathlib import Path

import networkx as nx
import pandas as pd
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.petri_net.importer import importer as pnml_importer
from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments

import BIG
from audit_group5_outputs import read_xes
from orgmining.instance_graphs import GFileConverter
from orgmining.visualization import InstanceGraphViewer

ROOT = Path(__file__).resolve().parents[2]
STEP1 = ROOT / 'outputs/step1_preprocessing/org_resource_roles'
STEP2 = ROOT / 'outputs/step2_instance_graphs/org_resource_roles'
OUT = ROOT / 'outputs/diagnostics'
CASE = 'Application_1691306052'


def edge_ids(g):
    return {(g.nodes[u]['local_id'], g.nodes[v]['local_id']) for u, v in g.edges}


def ordered_labels(g):
    return [d['label'] for _, d in sorted(g.nodes(data=True), key=lambda pair: pair[1]['local_id'])]


def shape(graphs):
    return dict(graphs=len(graphs), nodes=sum(len(g) for g in graphs),
                edges=sum(g.number_of_edges() for g in graphs),
                branching_graphs=sum(any(d > 1 for _, d in g.out_degree()) for g in graphs),
                cyclic_graphs=sum(not nx.is_directed_acyclic_graph(g) for g in graphs),
                disconnected_graphs=sum(not nx.is_weakly_connected(g) for g in graphs),
                simple_chains=sum(nx.is_directed_acyclic_graph(g) and nx.is_weakly_connected(g)
                                  and all(g.in_degree(n) <= 1 and g.out_degree(n) <= 1 for n in g)
                                  for g in graphs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT.parent / 'datasets_group5_mining_organizational_patterns')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    graphs = GFileConverter.load(STEP2 / 'instance_graphs.pkl')
    raw = GFileConverter().convert(STEP2 / 'instance_graphs.g')
    reference = GFileConverter().convert(args.data / 'BPI2017Denied.g')
    original = read_xes(args.data / 'BPI2017Denied(3).xes')
    relabeled = read_xes(STEP1 / 'relabeled_log.xes')
    errors = Counter()
    n_traces = 0
    for i, pair in enumerate(zip_longest(original, relabeled)):
        old_trace, new_trace = pair
        assert old_trace is not None and new_trace is not None, "Trace counts differ"
        case, events = old_trace
        new_case, new_events = new_trace
        n_traces += 1
        assert ordered_labels(reference[i]) == [e['concept:name'] for e in events]
        if case != new_case or len(events) != len(new_events):
            errors['case_or_event_count'] += 1
            continue
        for old, new in zip(events, new_events):
            for key, value in old.items():
                if key == 'concept:name':
                    if value != new.get('original_activity'):
                        errors['original_activity'] += 1
                elif value != new.get(key):
                    other = new.get(key)
                    if key == 'time:timestamp' and isoparse(value) == isoparse(other):
                        continue
                    try:
                        if other is not None and Decimal(value) == Decimal(other):
                            continue
                    except InvalidOperation:
                        pass
                    errors['original_attribute_changed_' + key] += 1
    assert n_traces == len(graphs) == len(raw) == len(reference)
    assert not errors, errors
    assert all(edge_ids(a) == edge_ids(b) and ordered_labels(a) == ordered_labels(b)
               for a, b in zip(raw, graphs))
    del raw
    # Exact directed paths with the SAME node labels, counted once per case for support.
    # These are examples of repetition, not SUBDUE output or MDL-ranked patterns.
    support, occurrences = Counter(), Counter()
    for g in graphs:
        seen = set()
        def visit(node, labels):
            labels = labels + (g.nodes[node]['label'],)
            if len(labels) >= 2:
                occurrences[labels] += 1
                seen.add(labels)
            if len(labels) < 5:
                for child in g.successors(node):
                    visit(child, labels)
        for n in g:
            visit(n, ())
        support.update(seen)
    rows = [dict(nodes=len(p), case_support=s, occurrences=occurrences[p],
                 labels=' -> '.join(p)) for p, s in support.most_common()]
    pd.DataFrame(rows).to_csv(OUT / 'recurring_paths.csv', index=False)
    net, im, fm = pnml_importer.apply(str(STEP2 / 'petri_net.pnml'))
    labels = pd.read_csv(STEP1 / 'label_counts.csv')
    visible = {t.label for t in net.transitions if t.label is not None}
    missing = labels[~labels.label.isin(visible)]
    missing.to_csv(OUT / 'labels_absent_from_model.csv', index=False)
    roles = pd.read_csv(STEP1 / 'resource_roles.csv')
    role_stats = dict(resources=len(roles),
                      resources_below_50pct_dominant_share=int((roles.share_in_role_pct < 50).sum()),
                      weighted_share_in_dominant_activity_group=float(roles.events_in_role_activities.sum() / roles.events.sum()),
                      role_event_totals=roles.groupby('role').events.sum().to_dict())
    from pm4py.streaming.importer.xes import importer as streaming_importer
    stream = streaming_importer.apply(str(STEP1 / 'relabeled_log.xes'),
                                       variant=streaming_importer.Variants.XES_TRACE_STREAM)
    selected_index, trace = next((i, t) for i, t in enumerate(stream)
                                 if t.attributes['concept:name'] == CASE)
    g = graphs[selected_index]
    alignment = alignments.apply_trace(trace, net, im, fm)
    moves = alignment['alignment']
    counts = dict(synchronous=sum(a == b and a != '>>' for a, b in moves),
                  log_only=sum(a != '>>' and b == '>>' for a, b in moves),
                  visible_model_only=sum(a == '>>' and b not in (None, '>>') for a, b in moves),
                  silent_model_only=sum(a == '>>' and b is None for a, b in moves))
    cr = set(BIG.find_causal_relationships(net))
    events = [(i, e['concept:name']) for i, e in enumerate(trace, 1)]
    _, pre_repair = BIG.extract_instance_graph(events, cr)
    before_edges = {(a[0], b[0]) for a, b in pre_repair}
    # Render original reference with role colours using the same per-event roles.
    comparison = reference[selected_index].copy()
    lookup = {d['local_id']: d for _, d in g.nodes(data=True)}
    for _, d in comparison.nodes(data=True):
        d.update(activity=lookup[d['local_id']]['activity'], value=lookup[d['local_id']]['value'])
    comparison.graph['case_id'] = CASE
    viewer = InstanceGraphViewer(graphs)
    viewer.plot(g, OUT / 'role_case_numbered.png')
    viewer.plot(comparison, OUT / 'reference_case_with_roles.png', title='Activity-only reference edges; roles added for comparison')
    # Minimal counterexample to a path-search bug in the supplied BIG library.
    # Keep the supplied library unchanged; this does not affect our fitting case.
    test_edges = [(1, 2), (2, 4), (1, 3), (3, 5)]
    test_nodes = [(i, str(i)) for i in range(1, 6)]
    path_bug = dict(edges=test_edges, source=1, target=4,
                    expected=nx.has_path(nx.DiGraph(test_edges), 1, 4),
                    supplied_BIG_result=BIG.is_path(1, 4, test_edges, test_nodes))
    result = dict(role_graphs=shape(graphs), reference_graphs=shape(reference),
                  original_attributes_preserved=not errors, raw_pickle_edges_and_labels_equal=True,
                  reference_labels_match_original_log=True,
                  absent_labels=missing.to_dict('records'), roles=role_stats,
                  causal_label_pairs=len(cr),
                  AND_split_transitions=[dict(label=t.label, outputs=len(t.out_arcs)) for t in net.transitions if len(t.out_arcs) > 1],
                  selected_case=dict(case_id=CASE, fitness=alignment.get('fitness'), alignment_moves=counts,
                                     nodes=len(g), edges=g.number_of_edges(),
                                     direct_extraction_without_repairs_matches=before_edges == edge_ids(g),
                                     reference_edges=sorted(edge_ids(reference[selected_index])),
                                     edges_only_in_role=sorted(edge_ids(g) - edge_ids(reference[selected_index])),
                                     edges_only_in_reference=sorted(edge_ids(reference[selected_index]) - edge_ids(g))),
                  supplied_BIG_path_search_counterexample=path_bug,
                  most_supported_paths_by_length={str(k): next(r for r in rows if r['nodes'] == k) for k in range(2, 6)})
    (OUT / 'investigation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

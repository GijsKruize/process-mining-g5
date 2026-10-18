"""Audit Group 5's existing BIG/NetworkX graphs against the XES used to create them.

Run from the project root in the project's Python 3.9 environment, e.g.:
  python audit_group5_outputs.py --log outputs/step1_preprocessing/org_resource_roles/relabeled_log.xes \
    --graphs outputs/step2_instance_graphs/org_resource_roles/instance_graphs.pkl \
    --case Application_1691306052 \
    --roles outputs/step1_preprocessing/org_resource_roles/resource_roles.csv

This program checks structural integrity and preservation of events. It does NOT
establish correctness of BIG's inferred causal relations relative to a process model.
Only load pickles created by your own group (pickle can execute arbitrary code).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import argparse
import csv
import gzip
import pickle
from collections import Counter
from pathlib import Path

import networkx as nx
from lxml import etree


def read_xes(path):
    path = Path(path)
    with (gzip.open(path, 'rb') if str(path).endswith('.gz') else open(path, 'rb')) as stream:
        for _, elem in etree.iterparse(stream, events=('end',), tag='{*}trace'):
            name = None
            events = []
            for child in elem:
                if etree.QName(child).localname == 'event':
                    attrs = {a.get('key'): a.get('value') for a in child
                             if a.get('key') is not None}
                    events.append(attrs)
                elif child.get('key') == 'concept:name':
                    name = child.get('value')
            yield name, events
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--log', required=True, help='Exact XES given to BIG (usually relabeled_log.xes)')
    parser.add_argument('--graphs', required=True, help='Instance graphs pickle created by the current code')
    parser.add_argument('--case', default='Application_1691306052', help='Case to print and inspect')
    parser.add_argument('--roles', help='Optional resource_roles.csv from Step 1')
    parser.add_argument('--summary', help='Optional CSV file for one row per case')
    args = parser.parse_args()

    with open(args.graphs, 'rb') as f:
        graphs = pickle.load(f)
    print(f'Loaded {len(graphs):,} graphs from {args.graphs}')
    role_lookup = {}
    if args.roles:
        with open(args.roles, newline='', encoding='utf-8-sig') as f:
            role_lookup = {r['resource']: r['role'] for r in csv.DictReader(f)}
        print(f'Loaded {len(role_lookup)} resource-to-role mappings')

    totals = Counter()
    errors = Counter()
    rows = []
    found = False
    read_cases = 0

    for index, (case_id, events) in enumerate(read_xes(args.log)):
        read_cases += 1
        if index >= len(graphs):
            errors['fewer_graphs_than_traces'] += 1
            continue
        graph = graphs[index]
        expected = [str(e.get('concept:name', '')) for e in events]
        local_to_node = {d.get('local_id'): node for node, d in graph.nodes(data=True)}
        actual = [graph.nodes[local_to_node[k]].get('label') for k in sorted(local_to_node)
                  if k is not None]
        ids_valid = sorted(local_to_node) == list(range(1, len(events) + 1))
        label_match = len(actual) == len(expected) and actual == expected
        if not ids_valid: errors['local_id_mismatch'] += 1
        if not label_match: errors['event_label_order_mismatch'] += 1
        if len(graph) != len(events): errors['node_count_mismatch'] += 1
        if graph.graph.get('case_id') != case_id: errors['case_id_mismatch'] += 1
        dag = nx.is_directed_acyclic_graph(graph)
        connected = len(graph) > 0 and nx.is_weakly_connected(graph)
        if not dag: errors['not_DAG'] += 1
        if not connected: errors['disconnected'] += 1
        if len(set(graph.nodes)) != len(graph): errors['duplicate_global_nodes_in_graph'] += 1
        nonforward = sum(graph.nodes[u].get('local_id', 0) >= graph.nodes[v].get('local_id', 0)
                         for u, v in graph.edges)
        if nonforward: errors['cases_with_backward_or_self_edges'] += 1
        bad_edge_labels = sum(attrs.get('label') != (graph.nodes[u].get('label','') + '__' + graph.nodes[v].get('label',''))
                              for u,v,attrs in graph.edges(data=True))
        if bad_edge_labels: errors['cases_with_invalid_edge_labels'] += 1
        # Check that every attribute copied from the XES agrees with the label value.
        incorrect_value = 0
        if role_lookup:
            for k, event in enumerate(events, start=1):
                resource = event.get('org:resource')
                mapped_role = role_lookup.get(resource)
                saved_role = event.get('selected_attribute_value')
                if mapped_role is None or saved_role != mapped_role:
                    incorrect_value += 1
                if k in local_to_node:
                    node_value = graph.nodes[local_to_node[k]].get('value')
                    if mapped_role is not None and node_value != mapped_role:
                        incorrect_value += 1
        if incorrect_value: errors['cases_with_inconsistent_role_mapping'] += 1
        totals['nodes'] += len(graph)
        totals['edges'] += graph.number_of_edges()
        totals['event_rows'] += len(events)
        totals['branching_graphs'] += int(any(degree > 1 for _, degree in graph.out_degree()))
        totals['extra_edges_above_chain'] += graph.number_of_edges() - max(0, len(graph) - 1)
        row = dict(index=index, case_id=case_id, events=len(events), nodes=len(graph),
                   edges=graph.number_of_edges(), event_labels_match=label_match,
                   ids_valid=ids_valid, dag=dag, connected=connected,
                   branching=any(d > 1 for _, d in graph.out_degree()),
                   backwards_edges=nonforward, role_mismatches=incorrect_value)
        rows.append(row)
        if case_id == args.case:
            found = True
            print('\n' + '=' * 68)
            print(f'SELECTED CASE {case_id}, index {index}')
            print(f'XES events: {len(events)} | graph nodes: {len(graph)} | graph edges: {graph.number_of_edges()}')
            print(f'Order & labels match XES: {label_match}; sequential local IDs 1..N: {ids_valid}')
            print(f'Connected: {connected}; DAG: {dag}; branching: {row["branching"]}')
            print(f'Backward edges: {nonforward}; role-mapping mismatches: {incorrect_value}')
            print('\nEvent order and the successors derived by BIG:')
            for k, e in enumerate(events, 1):
                if k in local_to_node:
                    node = local_to_node[k]
                    next_events = sorted(graph.nodes[n].get('local_id') for n in graph.successors(node))
                    print(f'  {k:>2} {e.get("concept:name", "<missing>")[:65]:<65} -> {next_events}')
            print('=' * 68 + '\n')

    if len(graphs) != read_cases:
        errors['graph_trace_count_mismatch'] += 1
    all_nodes = [node for graph in graphs for node in graph.nodes]
    if len(set(all_nodes)) != len(all_nodes):
        errors['nonunique_global_ids'] += 1
    print(f'XES traces: {read_cases:,} | graphs: {len(graphs):,}')
    print(f'XES events: {totals["event_rows"]:,} | graph nodes: {totals["nodes"]:,}')
    print(f'Edges: {totals["edges"]:,} | extra edges vs one chain per trace: {totals["extra_edges_above_chain"]:,}')
    print(f'Graphs with out-degree >1: {totals["branching_graphs"]:,} ({100*totals["branching_graphs"]/max(1,read_cases):.2f}%)')
    print(f'Selected case found: {found}')
    if errors:
        print('FAILURES / WARNING COUNTS:')
        for key, val in sorted(errors.items()): print(f'  {key}: {val}')
    else:
        print('PASS: all checked graph-event integrity invariants hold.')
    if args.summary:
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        with open(args.summary, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['index'])
            w.writeheader(); w.writerows(rows)
        print('Saved per-case summary:',args.summary)
    print('NOTE: This does NOT test whether the discovered Petri net / BIG dependency edges are semantically correct.')
    if errors or not found:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

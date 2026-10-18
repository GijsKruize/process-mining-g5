"""Rerun BIG for exactly one case, using the Petri net trained on the FULL role-labelled log.

Copy into the root of process-mining-g5, then run:

python test_group5_single_case.py

Requires your existing Python 3.9 + pm4py 2.2.16 environment and completed
Step 1 / full Step 2 output, including petri_net.pnml.

This does not rediscover a Petri net from one trace.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pathlib import Path

import networkx as nx
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import EventLog
from pm4py.objects.petri_net.importer import importer as pnml_importer
from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments

from orgmining.instance_graphs import GFileConverter, run_big_on_chunk
from orgmining.visualization import InstanceGraphViewer

CASE_ID = 'Application_1691306052'
STEP1 = Path('outputs/step1_preprocessing/org_resource_roles')
STEP2 = Path('outputs/step2_instance_graphs/org_resource_roles')
OUT = Path('outputs/diagnostics') / CASE_ID


def main():
    xes = STEP1 / 'relabeled_log.xes'
    pnml = STEP2 / 'petri_net.pnml'
    labels_csv = STEP1 / 'label_counts.csv'
    full_pickle = STEP2 / 'instance_graphs.pkl'
    for file in (xes, pnml, labels_csv):
        if not file.is_file():
            raise FileNotFoundError(f'{file} is missing. Run Steps 1 and 2 first.')

    print('Loading full preprocessed XES (NOT training a one-case model) ...')
    log = xes_importer.apply(str(xes))
    matching = [t for t in log if t.attributes.get('concept:name') == CASE_ID]
    if len(matching) != 1:
        raise ValueError(f'Expected exactly one trace {CASE_ID}, found {len(matching)}')
    trace = matching[0]
    print('Selected case:', CASE_ID, 'events:', len(trace))
    for i, event in enumerate(trace, 1):
        print(f'{i:>2} {event["concept:name"]}  resource={event.get("org:resource")}')

    OUT.mkdir(parents=True, exist_ok=True)
    one = EventLog([trace], attributes=log.attributes, extensions=log.extensions,
                   classifiers=log.classifiers, omni_present=log.omni_present)
    one_xes = OUT / 'case_relabeled.xes'
    xes_exporter.apply(one, str(one_xes))

    net, im, fm = pnml_importer.apply(str(pnml))
    print('\nChecking alignment against the FULL Petri net (may be slow for a complex model) ...')
    result = alignments.apply_trace(trace, net, im, fm)
    print('Alignment fitness:', result.get('fitness'))
    mismatches = []
    for a, b in result.get('alignment', []):
        if a == '>>' or b == '>>':
            mismatches.append((a, b))
    log_only = [(a,b) for a,b in mismatches if b == '>>' and a != '>>']
    model_only = [(a,b) for a,b in mismatches if a == '>>' and b != '>>']
    print('Alignment log-only moves:',len(log_only),'| model-only moves (including silent):',len(model_only))
    print('Silent model moves:', sum(a == '>>' and b is None for a, b in mismatches))
    print('Visible model-only moves:', sum(a == '>>' and b not in (None, '>>') for a, b in mismatches))
    print('First 15:', mismatches[:15])

    print('\nRunning BIG on exactly this case with the FULL model ...')
    # BIG.py appends to graph.g; remove the previous output before rerunning.
    (OUT / 'graph.g').unlink(missing_ok=True)
    path = run_big_on_chunk(one_xes, pnml, OUT)
    converter = GFileConverter.from_label_counts(labels_csv)
    graph = converter.convert(path, [CASE_ID])[0]
    case_pickle = OUT / 'single_case_graph.pkl'
    converter.save([graph], case_pickle)
    print('Result nodes:',graph.number_of_nodes(),'edges:',graph.number_of_edges())
    print('DAG:',nx.is_directed_acyclic_graph(graph), 'connected:',nx.is_weakly_connected(graph))
    assert nx.is_directed_acyclic_graph(graph) and nx.is_weakly_connected(graph)
    assert graph.number_of_nodes() == len(trace), 'BIG lost or added an event'
    expected = [e['concept:name'] for e in trace]
    local_to_node = {data['local_id']:node for node,data in graph.nodes(data=True)}
    actual = [graph.nodes[local_to_node[i]]['label'] for i in range(1,len(trace)+1)]
    assert actual == expected, 'BIG graph node labels/order differ from XES'

    if full_pickle.exists():
        full_graphs = converter.load(full_pickle)
        old = next((g for g in full_graphs if g.graph.get('case_id') == CASE_ID),None)
        if old is None:
            print('WARNING: could not find this case in full graph output')
        else:
            old_edges = {(old.nodes[u]['local_id'],old.nodes[v]['local_id']) for u,v in old.edges}
            new_edges = {(graph.nodes[u]['local_id'],graph.nodes[v]['local_id']) for u,v in graph.edges}
            print('Matches the saved full-run graph edges:', old_edges == new_edges)
            if old_edges != new_edges:
                print('Edges only in previous full run:',sorted(old_edges-new_edges)[:30])
                print('Edges only in single-case run:',sorted(new_edges-old_edges)[:30])
            assert old_edges == new_edges, 'Single-case edges differ from saved full run'

    viewer = InstanceGraphViewer([graph])
    print('\n' + viewer.describe(graph))
    figure = OUT / 'case_graph.svg'
    viewer.plot(graph,figure)
    print(f'\nPASS: case labels and node counts verified. Saved image: {figure}')
    print(f'BIG raw output: {path}')
    print('Note: these checks alone do not prove that graph edges reflect true causal dependencies.')


if __name__=='__main__':
    main()

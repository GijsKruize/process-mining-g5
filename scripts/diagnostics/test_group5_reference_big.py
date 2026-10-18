"""Independent reference test: BIG on the original (activity-only) first case.

Compare to the first block of BPI2017Denied.g supplied by the teacher.
Requires python 3.9 / pm4py 2.2.16 and original Canvas dataset folder.
Run from the project root: python test_group5_reference_big.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pathlib import Path
import networkx as nx
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.obj import EventLog
from orgmining.instance_graphs import GFileConverter, run_big_on_chunk
from orgmining.visualization import InstanceGraphViewer

CASE_ID='Application_1691306052'
from orgmining import config
DATA=config.DATASET_DIR
OUT=Path('outputs/diagnostics/reference_first_case')


def main():
    original=DATA/'BPI2017Denied(3).xes'
    reference=DATA/'BPI2017Denied.g'
    net=DATA/'BPI2017Denied_petriNet.pnml'
    for p in (original,reference,net):
        if not p.exists(): raise FileNotFoundError(p)
    log=xes_importer.apply(str(original))
    matches=[t for t in log if t.attributes.get('concept:name')==CASE_ID]
    if len(matches)!=1: raise RuntimeError(f'Found {len(matches)} traces for {CASE_ID}')
    trace=matches[0]
    OUT.mkdir(parents=True, exist_ok=True)
    xes_path=OUT/'original_first_case.xes'
    xes_exporter.apply(EventLog([trace], attributes=log.attributes,
                                extensions=log.extensions, classifiers=log.classifiers,
                                omni_present=log.omni_present),str(xes_path))
    (OUT/'graph.g').unlink(missing_ok=True)  # BIG appends to existing graph.g
    actual_g=run_big_on_chunk(xes_path, net, OUT)
    # Read only first reference block (avoid converting 3,093 for this small test).
    with open(reference,encoding='utf-8') as f:
        block=[]
        seen=False
        for line in f:
            if line.strip()=='XP':
                if seen: break
                seen=True
            if seen: block.append(line)
    reference_first=OUT/'reference_first.g'
    reference_first.write_text(''.join(block),encoding='utf-8')
    conv=GFileConverter()
    actual=conv.convert(actual_g,[CASE_ID])[0]
    expected=conv.convert(reference_first,[CASE_ID])[0]
    def label_order(g):
        return [d['label'] for _,d in sorted(g.nodes(data=True),key=lambda x:x[1]['local_id'])]
    def edge_order(g):
        return {(g.nodes[u]['local_id'],g.nodes[v]['local_id']) for u,v in g.edges}
    print('Reference:',expected.number_of_nodes(),'nodes,',expected.number_of_edges(),'edges')
    print('New BIG run:',actual.number_of_nodes(),'nodes,',actual.number_of_edges(),'edges')
    print('Both have exact original XES events:', label_order(actual)==label_order(expected)==
          [event['concept:name'] for event in trace])
    print('Same edge pairs?',edge_order(actual)==edge_order(expected))
    print('Extra new edges:',sorted(edge_order(actual)-edge_order(expected))[:40])
    print('Missing reference edges:',sorted(edge_order(expected)-edge_order(actual))[:40])
    print('New graph acyclic/connected?',nx.is_directed_acyclic_graph(actual),
          nx.is_weakly_connected(actual))
    assert label_order(actual) == label_order(expected) == [e['concept:name'] for e in trace]
    assert edge_order(actual) == edge_order(expected), 'Reference edges differ'
    assert nx.is_directed_acyclic_graph(actual) and nx.is_weakly_connected(actual)
    viewer=InstanceGraphViewer([actual]);viewer.plot(actual,OUT/'new_reference_case.svg')
    print('Saved graph:',OUT/'new_reference_case.svg')
    print('Note: a model or alignment tie break can cause edge differences even with valid code.')

if __name__=='__main__':main()

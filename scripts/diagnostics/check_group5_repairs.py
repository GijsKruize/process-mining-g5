"""Sample missing-label cases; compare repair with original and correct path search.
The supplied BIG.py and production graphs are preserved.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import json
from pathlib import Path
from pm4py.objects.log.importer.xes import importer
from pm4py.objects.petri_net.importer import importer as pnml
from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments
import BIG
from orgmining.instance_graphs import GFileConverter

out=Path('outputs/diagnostics')
log=importer.apply('outputs/step1_preprocessing/org_resource_roles/relabeled_log.xes')
net,im,fm=pnml.apply('outputs/step2_instance_graphs/org_resource_roles/petri_net.pnml')
visible={t.label for t in net.transitions if t.label is not None}
missing={e['concept:name'] for t in log for e in t}-visible
chosen={next(i for i,t in enumerate(log) if any(e['concept:name']==label for e in t)) for label in missing}
original=GFileConverter.load('outputs/step2_instance_graphs/org_resource_roles/instance_graphs.pkl')
cr=BIG.find_causal_relationships(net)
old_path=BIG.is_path

def correct_path(a,b,edges,nodes):
    todo=[a]
    seen=set()
    while todo:
        current=todo.pop()
        if current in seen:
            continue
        seen.add(current)
        for source,target in edges:
            if source==current:
                if target==b:
                    return True
                todo.append(target)
    return False

def build(moves,path_function):
    BIG.is_path=path_function
    aligned=[(i,b) for i,(a,b) in enumerate(moves,1)]
    actual=[(i,a) for i,(a,b) in enumerate(moves,1)]
    mapping,ins=BIG.mapping(aligned,actual)
    compliant=BIG.compliant_trace(aligned)
    nodes,edges=BIG.extract_instance_graph(compliant,cr)
    node_numbers=BIG.node_number(nodes)
    deletion=[e for e in mapping if e[1]==0]
    positions=nodes.copy()
    for e in deletion:
        positions.remove((e[2],e[0]))
    for insertion in ins:
        nodes,edges=BIG.ins_repair(nodes,edges,mapping,insertion,node_numbers,ins,positions)
    for d in deletion:
        nodes,edges=BIG.del_repair(nodes,edges,mapping,d)
    edges,nodes=BIG.update_label(edges,mapping,nodes)
    return {(a[0],b[0]) for a,b in edges}

rows=[]
for i in sorted(chosen):
    t=log[i]
    result=alignments.apply_trace(t,net,im,fm)
    moves=result['alignment']
    before=build(moves,old_path)
    after=build(moves,correct_path)
    g=original[i]
    saved={(g.nodes[u]['local_id'],g.nodes[v]['local_id']) for u,v in g.edges}
    rows.append(dict(index=i,case_id=t.attributes['concept:name'],nodes=len(t),fitness=result['fitness'],
                     log_moves=sum(a!='>>' and b=='>>' for a,b in moves),
                     visible_model_moves=sum(a=='>>' and b not in (None,'>>') for a,b in moves),
                     missing_labels_in_trace=sorted({e['concept:name'] for e in t}-visible),
                     original_repair_matches_saved=before==saved,
                     corrected_path_changes_edges=before!=after,
                     edges_removed=sorted(before-after),edges_added=sorted(after-before)))
    (out/'repair_sample.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(json.dumps(rows[-1]),flush=True)
BIG.is_path=old_path

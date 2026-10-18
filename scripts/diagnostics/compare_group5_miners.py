"""Controlled full-log discovery comparison; outputs stay in diagnostics."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import json
import argparse
import time
from collections import Counter
from pathlib import Path
import pm4py
from pm4py.algo.discovery.inductive import algorithm as inductive
from pm4py.objects.log.importer.xes import importer
from pm4py.objects.log.exporter.xes import exporter
from pm4py.objects.log.obj import EventLog
from orgmining.instance_graphs import PetriNetDiscoverer, GFileConverter, run_big_on_chunk
from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments
from pm4py.objects.petri_net.importer import importer as pnml
import BIG

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode', choices=['both', 'roles', 'activity'], default='activity')
parser.add_argument('--output-dir', type=Path, default=Path('outputs/diagnostics/miner_comparison'))
args = parser.parse_args()
OUT = args.output_dir
OUT.mkdir(parents=True,exist_ok=True)
log = importer.apply('outputs/step1_preprocessing/org_resource_roles/relabeled_log.xes')
results=[]
for label_mode, variant in [('roles','imf'), ('activity','im_clean')]:
    if args.mode != 'both' and label_mode != args.mode:
        continue
    print('Discovering full-log model:', label_mode, variant, flush=True)
    if label_mode == 'activity':
        for trace in log:
            for event in trace:
                event['concept:name'] = event['original_activity']
    folder=OUT / (label_mode+'_'+variant)
    folder.mkdir(exist_ok=True)
    started=time.time()
    if variant=='imf':
        v=inductive.Variants.IMf
        net,im,fm=inductive.apply(log, variant=v, parameters={v.value.Parameters.NOISE_THRESHOLD:0.2})
    else:
        net,im,fm=pm4py.discover_petri_net_inductive(log,noise_threshold=0.2)
    net_path=PetriNetDiscoverer.save(net, im, fm, folder/'petri_net.pnml')
    elapsed=time.time()-started
    trace=log[0]
    result=alignments.apply_trace(trace,net,im,fm)
    moves=result['alignment']
    one_xes=folder/'case.xes'
    exporter.apply(EventLog([trace],attributes=log.attributes),str(one_xes))
    (folder/'graph.g').unlink(missing_ok=True)
    raw=run_big_on_chunk(one_xes,net_path,folder)
    graph=GFileConverter().convert(raw)[0]
    row=dict(label_mode=label_mode,miner_variant=variant,noise_threshold=0.2,
             discovery_seconds=round(elapsed,2),net=PetriNetDiscoverer.describe(net),
             AND_splits=sum(len(t.out_arcs)>1 for t in net.transitions),
             causal_label_pairs=len(set(BIG.find_causal_relationships(net))),
             case_fitness=result['fitness'],
             log_moves=sum(a!='>>' and b=='>>' for a,b in moves),
             visible_model_moves=sum(a=='>>' and b not in (None,'>>') for a,b in moves),
             case_nodes=len(graph), case_edges=graph.number_of_edges(),
             case_branching=any(d>1 for _,d in graph.out_degree()))
    results.append(row)
    (OUT/'comparison.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(row,indent=2),flush=True)

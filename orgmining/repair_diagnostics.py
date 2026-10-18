"""Inspect worst-fitting/branching cases and sensitivity to supplied BIG path search."""
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd
from .artifacts import LOG, NET, GRAPHS, iter_traces, write_csv, write_json
from .graph_io import GFileConverter


def reachable(a,b,edges,nodes):
    todo=[a];seen=set()
    while todo:
        node=todo.pop()
        if node in seen:
            continue
        seen.add(node)
        for source,target in edges:
            if source==node:
                if target==b:
                    return True
                todo.append(target)
    return False


def repaired_edges(moves,net,path_function=None):
    import BIG
    original=BIG.is_path
    if path_function is not None:
        BIG.is_path=path_function
    try:
        aligned=[(i,b) for i,(a,b) in enumerate(moves,1)]
        actual=[(i,a) for i,(a,b) in enumerate(moves,1)]
        mapping,insertions=BIG.mapping(aligned,actual)
        nodes,edges=BIG.extract_instance_graph(BIG.compliant_trace(aligned),BIG.find_causal_relationships(net))
        numbers=BIG.node_number(nodes)
        deleted=[item for item in mapping if item[1]==0]
        positions=nodes.copy()
        for item in deleted:
            positions.remove((item[2],item[0]))
        for insertion in insertions:
            nodes,edges=BIG.ins_repair(nodes,edges,mapping,insertion,numbers,insertions,positions)
        for deletion in deleted:
            nodes,edges=BIG.del_repair(nodes,edges,mapping,deletion)
        edges,nodes=BIG.update_label(edges,mapping,nodes)
        return {(a[0],b[0]) for a,b in edges}
    finally:
        BIG.is_path=original


def inspect_one(task):
    from pm4py.objects.log.obj import Trace, Event
    from pm4py.objects.petri_net.importer import importer
    from pm4py.algo.conformance.alignments.petri_net import algorithm
    case,labels,saved=task
    net,im,fm=importer.apply(str(NET))
    trace=Trace([Event({'concept:name':a}) for a in labels])
    result=algorithm.apply_trace(trace,net,im,fm)
    moves=result['alignment']
    before=repaired_edges(moves,net)
    after=repaired_edges(moves,net,reachable)
    position=0;details=[]
    for step,(a,b) in enumerate(moves,1):
        if a!='>>':
            position+=1
        kind='sync' if a==b else ('silent_model' if b is None else ('log_only' if b=='>>' else 'visible_model'))
        details.append(dict(case_id=case,alignment_step=step,event_position=position if a!='>>' else '',
                            log_label=a,model_label=b,move_type=kind))
    return dict(case_id=case,fitness=result['fitness'],matches_historical_edges=before==set(map(tuple,saved)),
                corrected_path_changes_edges=before!=after,
                removed_by_path_fix=json.dumps(sorted(before-after)),
                added_by_path_fix=json.dumps(sorted(after-before))),details


def run(output='outputs/conformance/selected_cases',workers=2):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    graphs=GFileConverter.load(GRAPHS)
    table=pd.read_csv('outputs/conformance/per_case.csv')
    branches=[g.graph['case_id'] for g in graphs if any(d>1 for _,d in g.out_degree())]
    write_csv(output/'branching_cases.csv',table[table.case_id.isin(branches)].to_dict('records'))
    selected=set(branches)|set(table.sort_values('fitness').head(10).case_id)|{'Application_1691306052'}
    old=Path('outputs/diagnostics/repair_sample.json')
    if old.exists():
        selected.update(r['case_id'] for r in json.loads(old.read_text()))
    lookup={g.graph['case_id']:g for g in graphs}
    tasks=[]
    for case,events in iter_traces(LOG):
        if case in selected:
            g=lookup[case]
            saved=[(g.nodes[u]['local_id'],g.nodes[v]['local_id']) for u,v in g.edges]
            tasks.append((case,[e['concept:name'] for e in events],saved))
            write_csv(output/'events'/f'{case}.csv',[
                dict(event_position=i,label=e['concept:name'],resource=e.get('org:resource'),
                     timestamp=e.get('time:timestamp'),role=e.get('selected_attribute_value'))
                for i,e in enumerate(events,1)])
    rows=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row,details in pool.map(inspect_one,tasks):
            rows.append(row)
            write_csv(output/'alignments'/f'{row["case_id"]}.csv',details)
            print(f'Inspected {row["case_id"]}: path fix changes edges={row["corrected_path_changes_edges"]}',flush=True)
    write_csv(output/'repair_sensitivity.csv',rows)
    write_json(output/'summary.json',dict(cases=len(rows),branching_cases=len(branches),
               original_rerun_matches_historical=sum(r['matches_historical_edges'] for r in rows),
               cases_with_edges_changed_by_correct_path_search=sum(r['corrected_path_changes_edges'] for r in rows),
               scope='All eight branching cases, ten lowest-fitness cases, earlier missing-label cases and example; not all repaired cases. Supplied BIG.py and baseline graphs preserved.'))

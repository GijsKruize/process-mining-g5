"""Gold-standard scaffolding and explicit separation of human and proxy evaluation."""
import csv
import hashlib
import json
from pathlib import Path
import networkx as nx
import pandas as pd
from .artifacts import LOG, GRAPHS, iter_traces, write_csv, write_json
from .graph_io import GFileConverter
from .patterns import as_record, from_record, exact_occurrences

CANDIDATES=[
 ('GS01','Offer creation and sending','O-Create-Offer_Role_1 O-Created_Role_1 O-Sent-mail-and-online_Role_1'),
 ('GS02','Complete application suspend/resume','W-Complete-application-start_Role_1 W-Complete-application-suspend_Role_1 W-Complete-application-resume_Role_1'),
 ('GS03','Call after offers initiation','W-Call-after-offers-schedule_Role_1 W-Call-after-offers-start_Role_1 A-Complete_Role_1'),
 ('GS04','Validation initiation','W-Validate-application-schedule_Role_2 W-Validate-application-start_Role_2 A-Validating_Role_2'),
 ('GS05','Denial and refusal completion','A-Denied_Role_3 O-Refused_Role_3 W-Validate-application-complete_Role_3'),
 ('GS06','Repeated validation resume/suspend','W-Validate-application-resume_Role_3 W-Validate-application-suspend_Role_3 W-Validate-application-resume_Role_3'),
 ('GS07','Call to validation handoff','W-Call-after-offers-ate-abort_Role_2 W-Validate-application-schedule_Role_2 W-Validate-application-start_Role_2 A-Validating_Role_2'),
 ('GS08','Acceptance to offer creation','A-Accepted_Role_1 O-Create-Offer_Role_1 O-Created_Role_1')]


def metrics(actual,predicted):
    if len(actual)!=len(predicted):
        raise ValueError('Prediction and annotation lengths differ')
    if any(v not in (0,1) for v in list(actual)+list(predicted)):
        raise ValueError('Only binary labels 0/1 are accepted')
    tp=sum(a==p==1 for a,p in zip(actual,predicted))
    fp=sum(a==0 and p==1 for a,p in zip(actual,predicted))
    fn=sum(a==1 and p==0 for a,p in zip(actual,predicted))
    tn=sum(a==p==0 for a,p in zip(actual,predicted))
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,precision=precision,recall=recall,
                f1=2*precision*recall/(precision+recall) if precision+recall else 0.0,
                undefined_precision=not bool(tp+fp),undefined_recall=not bool(tp+fn))


def create_spec(path='evaluation/gold_standard_draft.json'):
    path=Path(path)
    if not path.exists():
        records=[]
        for pid,name,labels in CANDIDATES:
            graph=nx.DiGraph()
            for i,label in enumerate(labels.split(),1):
                graph.add_node(i,label=label)
            for a,b in zip(list(graph),list(graph)[1:]):
                graph.add_edge(a,b,label=graph.nodes[a]['label']+'__'+graph.nodes[b]['label'])
            records.append(as_record(graph,pid,name=name,approved=False,reviewed_by='',
                         reference_semantics='contiguous labels in original case event order'))
        write_json(path,dict(status='machine_suggested_draft_NOT_manual_gold',
            origin='Event semantics and previous exploratory audit; not independently human selected or preregistered.',
            matching='A mined pattern recovers a target when it contains the exact directed labelled target subgraph. A case is positive when any such mined pattern occurs in that case.',
            patterns=records))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def run(output='outputs/evaluation',spec_path='evaluation/gold_standard_draft.json',
        pattern_dir='outputs/step3_patterns',conformance='outputs/conformance/per_case.csv'):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    spec=create_spec(spec_path)
    targets=spec['patterns']
    definitions=json.loads((Path(pattern_dir)/'patterns.json').read_text())
    mined_matrix=pd.read_csv(Path(pattern_dir)/'trace_pattern_matrix.csv').set_index('case_id')
    graphs=GFileConverter.load(GRAPHS)
    mapping={t['pattern_id']:[p['pattern_id'] for p in definitions
                if exact_occurrences(from_record(p),from_record(t))] for t in targets}
    write_json(output/'target_to_mined_patterns.json',mapping)
    truth=[];predictions=[];comparison=[];graph_truth=[]
    reference_rows=[];prediction_rows=[]
    by_case={}
    for g,(case,events) in zip(graphs,iter_traces(LOG)):
        if case!=g.graph['case_id']:
            raise ValueError('Graph/log case ordering differs')
        labels=[e['concept:name'] for e in events]
        row={'case_id':case};predrow={'case_id':case}
        for t in targets:
            tid=t['pattern_id']
            target=from_record(t)
            order=list(nx.topological_sort(target))
            # Draft targets are paths. Branching golds require independent human
            # annotations rather than an invented ordering of parallel events.
            if any(target.out_degree(n)>1 or target.in_degree(n)>1 for n in target):
                raise ValueError('Automated raw-sequence proxy only supports path targets; use manual evaluation for branching golds.')
            sequence=[target.nodes[n]['label'] for n in order]
            starts=[i+1 for i in range(len(labels)-len(sequence)+1) if labels[i:i+len(sequence)]==sequence]
            actual=int(bool(starts))
            predicted=int(any(int(mined_matrix.loc[case,pid]) for pid in mapping[tid]))
            structural=int(bool(exact_occurrences(g,target)))
            truth.append(actual);predictions.append(predicted);graph_truth.append(structural)
            row[tid]=actual;predrow[tid]=predicted
            comparison.append(dict(case_id=case,gold_pattern_id=tid,reference_label=actual,
                        predicted_label=predicted,graph_contains_target=structural,
                        suggested_evidence_start_positions=' '.join(map(str,starts))))
        reference_rows.append(row);prediction_rows.append(predrow)
        by_case[case]=events
    write_csv(output/'automatic_reference_matrix.csv',reference_rows)
    write_csv(output/'predicted_target_matrix.csv',prediction_rows)
    write_csv(output/'automatic_reference_comparison.csv',comparison)
    per_pattern=[]
    for t in targets:
        rows=[r for r in comparison if r['gold_pattern_id']==t['pattern_id']]
        per_pattern.append(dict(gold_pattern_id=t['pattern_id'],mined_patterns=' '.join(mapping[t['pattern_id']]),
                               **metrics([r['reference_label'] for r in rows],[r['predicted_label'] for r in rows])))
    write_csv(output/'automatic_metrics_per_target.csv',per_pattern)
    write_json(output/'automatic_benchmark.json',dict(status='PROXY_NOT_HUMAN_GOLD',
                scope=f'{len(graphs)} cases x {len(targets)} machine-suggested target motifs',
                micro_metrics=metrics(truth,predictions),
                graph_representation_consistency=metrics(truth,graph_truth),
                target_count=len(targets),targets_recovered=sum(bool(v) for v in mapping.values()),
                limitation='Reference is generated by contiguous label matching in the source log. No human relevance/causality validation. Draft targets informed by prior exploratory audit. Additional mined patterns outside these targets are not scored for relevance. These are motif-detection metrics, not exhaustive pattern-set precision/recall.'))
    # Reproducible annotation sample: sample membership is based on case hash,
    # branching, poor conformance, and the known case, never on mining predictions.
    selected=sorted(by_case,key=lambda c:hashlib.sha256(c.encode()).hexdigest())[:16]
    reasons={c:'hash-selected' for c in selected}
    for g in graphs:
        if any(d>1 for _,d in g.out_degree()):
            reasons[g.graph['case_id']]='branching'
    fitness=pd.read_csv(conformance).sort_values('fitness').head(10)
    for case in fitness.case_id:
        reasons[case]='lowest-fitness'
    reasons['Application_1691306052']='example-case'
    selected=sorted(reasons)
    write_csv(output/'annotation_cases.csv',[dict(case_id=c,selection_reason=reasons[c]) for c in selected])
    form=[]
    for case in selected:
        for t in targets:
            form.append(dict(case_id=case,gold_pattern_id=t['pattern_id'],present='',reviewer='',reviewed_at='',
                             evidence_event_positions='',reason=''))
        write_csv(output/'annotation_packets'/f'{case}.csv',[
            dict(event_position=i,activity=e.get('original_activity'),role=e.get('selected_attribute_value'),
                 resource=e.get('org:resource'),timestamp=e.get('time:timestamp'),label=e['concept:name'])
            for i,e in enumerate(by_case[case],1)])
    manual=output/'manual_annotations.csv'
    if not manual.exists():
        write_csv(manual,form)
    # Keep automatic suggestions separate so the blank manual form stays usable
    # for blind review. Do not expose them during independent annotation.
    selected_comparison=[r for r in comparison if r['case_id'] in reasons]
    write_csv(output/'automatic_suggestions_NOT_manual.csv',selected_comparison)
    relevance=output/'manual_pattern_relevance.csv'
    if not relevance.exists():
        write_csv(relevance,[dict(pattern_id=p['pattern_id'],relevant='',reviewer='',reason='') for p in definitions])
    evaluate_manual(manual,spec,comparison,output)
    return output


def evaluate_manual(manual,spec,comparison,output):
    rows=list(csv.DictReader(Path(manual).open(encoding='utf-8-sig')))
    expected={(r['case_id'],r['gold_pattern_id']):r['predicted_label'] for r in comparison}
    reviewed=[];seen=set()
    for row in rows:
        key=(row['case_id'],row['gold_pattern_id'])
        if key in seen:
            raise ValueError('Duplicate manual annotation cell')
        seen.add(key)
        if key not in expected:
            raise ValueError(f'Unknown manual annotation cell: {key}')
        if row['present']!='':
            if row['present'] not in ('0','1') or not row['reviewer'].strip():
                raise ValueError('Reviewed cells need 0/1 and an identified reviewer')
            reviewed.append((int(row['present']),expected[key]))
    approved=all(t.get('approved') and t.get('reviewed_by') for t in spec['patterns'])
    stats=dict(status='pending_human_review' if not reviewed else 'partial_human_review',
               annotation_cells=len(rows),reviewed_cells=len(reviewed),pending_cells=len(rows)-len(reviewed),
               all_target_definitions_human_approved=approved,
               metrics_on_reviewed_cells=metrics([a for a,p in reviewed],[p for a,p in reviewed]) if reviewed else None,
               final_assignment_evaluation_complete=bool(rows) and len(reviewed)==len(rows) and approved,
               note='No manual labels have been invented. The stratified reviewed sample is not a probability sample; report its scope and selection.')
    relevance_path=Path(output)/'manual_pattern_relevance.csv'
    relevance_rows=list(csv.DictReader(relevance_path.open(encoding='utf-8-sig'))) if relevance_path.exists() else []
    reviewed_relevance=[]
    for row in relevance_rows:
        if row['relevant']!='':
            if row['relevant'] not in ('0','1') or not row['reviewer'].strip():
                raise ValueError('Reviewed pattern relevance needs 0/1 and a reviewer')
            reviewed_relevance.append(int(row['relevant']))
    stats['mined_patterns_for_relevance_review']=len(relevance_rows)
    stats['mined_patterns_relevance_reviewed']=len(reviewed_relevance)
    stats['precision_of_reviewed_mined_patterns']=sum(reviewed_relevance)/len(reviewed_relevance) if reviewed_relevance else None
    recovered={r['gold_pattern_id'] for r in comparison if r['predicted_label']==1}
    stats['recall_of_approved_target_types']=sum(t['pattern_id'] in recovered for t in spec['patterns'])/len(spec['patterns']) if approved else None
    stats['final_assignment_evaluation_complete'] = stats['final_assignment_evaluation_complete'] and bool(relevance_rows) and len(reviewed_relevance)==len(relevance_rows)
    if stats['final_assignment_evaluation_complete']:
        stats['status']='human_review_complete_for_declared_sample'
    write_json(Path(output)/'manual_evaluation.json',stats)

"""Focused regression tests for direction, occurrence semantics and evaluation honesty."""
import json
import tempfile
import unittest
from pathlib import Path
import networkx as nx
from orgmining.patterns import exact_occurrences, run as mine
from orgmining.graph_io import GFileConverter
from orgmining.evaluation import metrics, evaluate_manual
from orgmining.artifacts import write_csv
from orgmining.subdue_adapter import SOURCE, load_engine, indexed_operations


def path_graph(labels,start=0):
    g=nx.DiGraph()
    for i,label in enumerate(labels,start):
        g.add_node(i,label=label,local_id=i-start+1)
    for u,v in zip(list(g),list(g)[1:]):
        g.add_edge(u,v,label=g.nodes[u]['label']+'__'+g.nodes[v]['label'])
    return g


class PatternMatchingTests(unittest.TestCase):
    def test_direction_and_metadata(self):
        host=path_graph(['A','B','C'],100)
        pattern=path_graph(['A','B'],1)
        self.assertEqual(len(exact_occurrences(host,pattern)),1)
        reverse=nx.DiGraph()
        reverse.add_nodes_from(pattern.nodes(data=True))
        reverse.add_edge(2,1,label='B__A')
        self.assertEqual(exact_occurrences(host,reverse),[])

    def test_repeated_labels_keep_distinct_events_and_overlap(self):
        host=path_graph(['A','B','A','B','A'])
        motif=path_graph(['A','B','A'])
        self.assertEqual(len(exact_occurrences(host,motif)),2)
        one=path_graph(['A','B'])
        self.assertEqual(exact_occurrences(one,motif),[])

    def test_non_induced_and_case_boundaries(self):
        a=path_graph(['A','B'],0)
        b=path_graph(['B','C'],10)
        union=nx.compose(a,b)
        self.assertEqual(exact_occurrences(union,path_graph(['A','B','C'])),[])
        chain=path_graph(['A','B','C'])
        chain.add_edge(0,2,label='A__C')
        self.assertEqual(len(exact_occurrences(chain,path_graph(['A','B','C']))),1)

    @unittest.skipUnless((SOURCE/'Subdue.py').exists(),'Install the upstream SUBDUE dependency')
    def test_real_engine_renumbered_nodes_keep_their_labels(self):
        graphs=[]
        for i in range(4):
            graph=path_graph(['A','B','C'],start=100+i*10)
            graph.graph.update(case_id=f'c{i}',graph_index=i)
            graphs.append(graph)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            GFileConverter.save(graphs,root/'graphs.pkl')
            definitions=mine(root/'graphs.pkl',root/'out',beam=2,limit=20,max_edges=2,numbest=3)
            self.assertTrue(definitions)
            labels={n['label'] for n in definitions[0]['nodes']}
            self.assertEqual(labels,{'A','B','C'})
            import pandas as pd
            support=pd.read_csv(root/'out/pattern_support.csv')
            self.assertTrue((support.support_cases==4).all())
            matrix=pd.read_csv(root/'out/trace_pattern_matrix.csv')
            self.assertTrue((matrix.drop(columns=['case_id','graph_index'])==1).all().all())

    @unittest.skipUnless((SOURCE/'Subdue.py').exists(),'Install upstream')
    def test_indexed_operations_match_upstream_initial_patterns(self):
        engine=load_engine()
        import Graph,Parameters
        objects=[]
        for i in range(9):
            objects.append({'vertex':{'id':str(i),'attributes':{'label':'ABC'[i%3]}}})
        for i in range(8):
            objects.append({'edge':{'id':str(i),'source':str(i),'target':str(i+1),'directed':'true','attributes':{'label':'edge'}}})
        g=Graph.Graph();g.load_from_json(objects)
        params=Parameters.Parameters();params.overlap='vertex'
        original=engine.GetInitialPatterns(params,g)
        with indexed_operations(engine):
            optimized=engine.GetInitialPatterns(params,g)
        def signatures(patterns):
            return [[sorted(e.id for e in instance.edges) for instance in p.instances] for p in patterns]
        self.assertEqual(signatures(original),signatures(optimized))


class ConformanceTests(unittest.TestCase):
    def test_cached_empty_trace_cost_matches_pm4py_facade(self):
        import pm4py
        from pm4py.objects.log.obj import Trace, Event, EventLog
        from pm4py.objects.petri_net.exporter import exporter
        from pm4py.algo.conformance.alignments.petri_net import algorithm
        from orgmining.conformance import _initialize, _align
        train=EventLog([Trace([Event({'concept:name':a}) for a in ['A','B','C']])])
        net,im,fm=pm4py.discover_petri_net_inductive(train)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.pnml'
            exporter.apply(net,im,str(path),final_marking=fm)
            _initialize(str(path),60)
            for labels in [('A','B','C'),('A','X','C')]:
                official=algorithm.apply_trace(Trace([Event({'concept:name':a}) for a in labels]),net,im,fm)
                cached=_align((0,labels))
                self.assertEqual(cached['cost'],official['cost'])
                self.assertEqual(cached['fitness'],official['fitness'])


class EvaluationTests(unittest.TestCase):
    def test_precision_and_recall(self):
        result=metrics([1,1,0,0],[1,0,1,0])
        self.assertEqual((result['tp'],result['fp'],result['fn'],result['tn']),(1,1,1,1))
        self.assertEqual(result['precision'],.5)
        self.assertEqual(result['recall'],.5)

    def test_empty_manual_form_has_no_fabricated_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            write_csv(root/'form.csv',[dict(case_id='c',gold_pattern_id='GS01',present='',reviewer='')])
            evaluate_manual(root/'form.csv',{'patterns':[{'approved':False}]},
                            [dict(case_id='c',gold_pattern_id='GS01',predicted_label=1)],root)
            data=json.loads((root/'manual_evaluation.json').read_text())
            self.assertIsNone(data['metrics_on_reviewed_cells'])
            self.assertFalse(data['final_assignment_evaluation_complete'])


if __name__=='__main__':
    unittest.main()

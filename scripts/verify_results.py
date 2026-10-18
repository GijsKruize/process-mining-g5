"""Verify exported research artifacts against the immutable baseline."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(name,'1')
import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import networkx as nx
import pandas as pd
from lxml import etree
from pm4py.algo.evaluation.replay_fitness.variants import alignment_based
from orgmining.artifacts import GRAPHS, write_json
from orgmining.graph_io import GFileConverter


def run():
    graphs=GFileConverter.load(GRAPHS)
    index=pd.read_csv('outputs/instance_graph_exports/case_index.csv')
    assert len(index)==len(graphs)==3093
    for graph,row in zip(graphs,index.itertuples()):
        root=Path('outputs/instance_graph_exports')
        assert row.case_id==graph.graph['case_id']
        exported=nx.read_graphml(root/row.graphml)
        assert {int(n):d for n,d in exported.nodes(data=True)}==dict(graph.nodes(data=True))
        assert {(int(u),int(v),d['label']) for u,v,d in exported.edges(data=True)}=={(u,v,d['label']) for u,v,d in graph.edges(data=True)}
        etree.parse(str(root/row.svg))
    matrix=pd.read_csv('outputs/step3_patterns/trace_pattern_matrix.csv')
    support=pd.read_csv('outputs/step3_patterns/pattern_support.csv')
    occurrences=pd.read_csv('outputs/step3_patterns/occurrences.csv')
    assert matrix.case_id.tolist()==index.case_id.tolist()
    assert set(matrix.drop(columns=['graph_index','case_id']).stack().unique())<={0,1}
    for row in support.itertuples():
        assert int(matrix[row.pattern_id].sum())==row.support_cases
        assert len(occurrences[occurrences.pattern_id==row.pattern_id])==row.total_exact_occurrences
        assert row.support_cases>0
    conf=pd.read_csv('outputs/conformance/per_case.csv')
    summary=json.loads(Path('outputs/conformance/summary.json').read_text())
    assert conf.case_id.tolist()==index.case_id.tolist()
    assert (conf.synchronous_moves+conf.log_moves==conf.events).all()
    official=alignment_based.evaluate(conf.to_dict('records'))
    assert abs(official['log_fitness']-summary['log_fitness'])<1e-12
    assert abs(official['average_trace_fitness']-summary['average_trace_fitness'])<1e-12
    for archive in ['outputs/instance_graph_exports/all_instance_graphs.zip','outputs/paper/results_bundle.zip']:
        if Path(archive).exists():
            with zipfile.ZipFile(archive) as bundle:
                assert bundle.testzip() is None, archive
    report=dict(graphml_roundtrips=len(graphs),svg_documents_parsed=len(graphs),
                matrix_shape=list(matrix.drop(columns=['graph_index','case_id']).shape),
                support_and_occurrence_totals_verified=True,
                conformance_matches_official_pm4py_evaluation=True,
                archives_crc_valid=True)
    write_json('outputs/paper/artifact_verification.json',report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    run()

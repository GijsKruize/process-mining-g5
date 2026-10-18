"""Step 3: upstream SUBDUE discovery plus exact trace-level support and exports."""
import contextlib
import json
import time
from collections import Counter
from pathlib import Path
import networkx as nx
import pandas as pd
from .artifacts import GRAPHS, sha256, write_csv, write_json
from .graph_io import GFileConverter
from .subdue_adapter import load_engine, indexed_operations
from .visualization import InstanceGraphViewer


def exact_occurrences(graph, pattern):
    """Unique edge-set occurrences of a connected directed non-induced subgraph.

    Different automorphisms of the same edge set count once. Additional host
    edges are permitted; this is monomorphism, not induced subgraph matching.
    """
    need=Counter(d['label'] for _,d in pattern.nodes(data=True))
    have=Counter(d['label'] for _,d in graph.nodes(data=True))
    if any(have[label]<count for label,count in need.items()):
        return []
    matcher=nx.algorithms.isomorphism.DiGraphMatcher(
        graph,pattern,node_match=nx.algorithms.isomorphism.categorical_node_match('label',None),
        edge_match=nx.algorithms.isomorphism.categorical_edge_match('label',None))
    matches={}
    for mapping in matcher.subgraph_monomorphisms_iter():
        inverse={v:k for k,v in mapping.items()}
        edges=tuple(sorted((inverse[u],inverse[v]) for u,v in pattern.edges))
        if edges not in matches:
            matches[edges]=dict(nodes=sorted(mapping),edges=[list(e) for e in edges])
    return list(matches.values())


def as_record(graph, pattern_id, **extras):
    nodes=list(graph)
    ids={n:i+1 for i,n in enumerate(nodes)}
    return dict(pattern_id=pattern_id,nodes=[dict(id=ids[n],**graph.nodes[n]) for n in nodes],
                edges=[dict(source=ids[u],target=ids[v],**d) for u,v,d in graph.edges(data=True)],**extras)


def from_record(record):
    g=nx.DiGraph()
    for node in record['nodes']:
        g.add_node(node['id'],**{k:v for k,v in node.items() if k!='id'})
    for edge in record['edges']:
        g.add_edge(edge['source'],edge['target'],**{k:v for k,v in edge.items() if k not in ('source','target')})
    return g


def run(graphs_path=GRAPHS,output='outputs/step3_patterns',beam=4,limit=5000,max_edges=5,numbest=20):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    graphs=GFileConverter.load(graphs_path)
    objects=[]
    for graph in graphs:
        for n,d in graph.nodes(data=True):
            objects.append({'vertex':{'id':str(n),'attributes':{'label':d['label']}}})
        for u,v,d in graph.edges(data=True):
            objects.append({'edge':{'id':f'{u}-{v}','source':str(u),'target':str(v),
                                     'directed':'true','attributes':{'label':d['label']}}})
    write_json(output/'subdue_input.json',objects)
    engine=load_engine()
    import Graph
    import Parameters
    vendor_graph=Graph.Graph()
    vendor_graph.load_from_json(objects)
    del objects
    assert all(e.directed for e in vendor_graph.edges.values()), 'Edge direction was lost'
    settings=dict(beamWidth=beam,limit=limit,maxSize=max_edges,minSize=2,numBest=numbest,
                  overlap='vertex',iterations=1,prune=False,temporal=False)
    params=Parameters.Parameters()
    params.set_parameters_from_kwargs(**settings)
    params.set_defaults_for_graph(vendor_graph)
    started=time.time()
    print(f'Upstream SUBDUE: {len(vendor_graph.vertices)} vertices, {len(vendor_graph.edges)} directed edges',flush=True)
    with (output/'subdue.log').open('w',encoding='utf-8',buffering=1) as stream:
        with contextlib.redirect_stdout(stream),indexed_operations(engine):
            found=engine.DiscoverPatterns(params,vendor_graph)
    # Definitions are extracted from real upstream seed instances. Every later
    # occurrence/support value is recomputed exactly, outside approximate mining.
    metadata={d['label']:d for g in graphs for _,d in g.nodes(data=True)}
    definitions=[]
    for index,p in enumerate(found,1):
        definition=nx.DiGraph()
        for node in p.definition.vertices.values():
            attributes=dict(metadata[node.attributes['label']])
            attributes['local_id']=len(definition)+1
            definition.add_node(node.id,**attributes)
        for edge in p.definition.edges.values():
            definition.add_edge(edge.source.id,edge.target.id,**edge.attributes)
        for u,v,d in definition.edges(data=True):
            if d['label'] != definition.nodes[u]['label']+'__'+definition.nodes[v]['label']:
                raise ValueError('Upstream definition labels disagree with directed edge endpoints')
        # Upstream's approximate graph matching may return a duplicate definition.
        if any(nx.is_isomorphic(definition,from_record(r),node_match=lambda a,b:a['label']==b['label'],
                                edge_match=lambda a,b:a['label']==b['label']) for r in definitions):
            continue
        definitions.append(as_record(definition,f'P{len(definitions)+1:03d}',
                          upstream_score=p.value,upstream_selected_instances=len(p.instances)))
    write_json(output/'patterns.json',definitions)
    del vendor_graph,found
    matrix=[]
    occurrence_rows=[]
    totals=Counter()
    cases_support=Counter()
    for i,graph in enumerate(graphs):
        row={'graph_index':i,'case_id':graph.graph['case_id']}
        for record in definitions:
            pid=record['pattern_id']
            matches=exact_occurrences(graph,from_record(record))
            row[pid]=int(bool(matches))
            totals[pid]+=len(matches)
            cases_support[pid]+=int(bool(matches))
            for number,match in enumerate(matches,1):
                occurrence_rows.append(dict(case_id=graph.graph['case_id'],pattern_id=pid,occurrence=number,
                    local_node_ids=' '.join(str(graph.nodes[n]['local_id']) for n in match['nodes']),
                    global_node_ids=' '.join(map(str,match['nodes'])),
                    local_edges=json.dumps([[graph.nodes[u]['local_id'],graph.nodes[v]['local_id']] for u,v in match['edges']])))
        matrix.append(row)
        if (i+1)%250==0:
            print(f'Exact support: {i+1}/{len(graphs)} cases',flush=True)
    fields=['graph_index','case_id']+[r['pattern_id'] for r in definitions]
    write_csv(output/'trace_pattern_matrix.csv',matrix,fields)
    write_csv(output/'occurrences.csv',occurrence_rows,
              ['case_id','pattern_id','occurrence','local_node_ids','global_node_ids','local_edges'])
    support=[]
    viewer=InstanceGraphViewer(graphs)
    for record in definitions:
        pid=record['pattern_id']
        g=from_record(record)
        # Pattern ids are local; do not present an arbitrary seed's event positions.
        for n in g:
            g.nodes[n]['local_id']=n
        viewer.plot(g,output/'figures'/f'{pid}.svg',title=f'{pid}: {cases_support[pid]}/{len(graphs)} cases')
        support.append(dict(pattern_id=pid,nodes=len(g),edges=g.number_of_edges(),
                            support_cases=cases_support[pid],support_pct=100*cases_support[pid]/len(graphs),
                            total_exact_occurrences=totals[pid],upstream_score=record['upstream_score'],
                            description=' -> '.join(g.nodes[n]['label'] for n in nx.topological_sort(g))))
    if any(r['support_cases']==0 for r in support):
        raise ValueError('Mined definition has no exact occurrence in the input')
    write_csv(output/'pattern_support.csv',support,
              ['pattern_id','nodes','edges','support_cases','support_pct','total_exact_occurrences','upstream_score','description'])
    write_json(output/'summary.json',dict(cases=len(graphs),patterns=len(definitions),
               input_sha256=sha256(graphs_path),upstream_commit='f33567dea2fa7e9595c27b807f16b120a7bdebb2',
               upstream_url='https://github.com/holderlb/Subdue',settings=settings,
               elapsed_seconds=round(time.time()-started,2),
               support_semantics='Exact directed labelled non-induced subgraphs; binary case presence, independently verified. All overlapping edge-set occurrences counted separately.',
               score_semantics='Upstream edge-compression heuristic, NOT a full MDL bit-length score.',
               coverage='All cases; bounded beam search is not exhaustive; additional exact verification does not recover undiscovered patterns.'))
    print(f'Finished: {len(definitions)} patterns across {len(graphs)} traces',flush=True)
    return definitions

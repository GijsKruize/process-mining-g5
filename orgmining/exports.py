"""Lossless all-case tables, individual vector figures and text printouts for papers."""
import csv
import html
import json
import textwrap
import zipfile
from pathlib import Path
import networkx as nx
from .artifacts import GRAPHS, sha256, write_csv, write_json
from .graph_io import GFileConverter

PALETTE=['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#6250d6','#e34948']


def svg_graph(graph,title=None,columns=8):
    """Self-contained SVG with event ids, explicit arrows and role colours.

    Each row always reads left-to-right; wrap arrows connect consecutive rows.
    Positions are topological layers, so multiple concurrent graph paths share
    a layer. This routine does not infer concurrency or modify graph edges.
    """
    ordered=list(nx.lexicographical_topological_sort(graph,key=lambda n:graph.nodes[n].get('local_id',n)))
    layers={}
    grouped={}
    for n in ordered:
        depth=max((layers[p]+1 for p in graph.predecessors(n)),default=0)
        layers[n]=depth
        grouped.setdefault(depth,[]).append(n)
    max_width=max(map(len,grouped.values()),default=1)
    row_height=120*max_width+60
    n_layers=max(layers.values(),default=0)+1
    width=columns*240+80
    height=((n_layers-1)//columns+1)*row_height+100
    positions={}
    for depth,nodes in grouped.items():
        row,col=divmod(depth,columns)
        for slot,n in enumerate(nodes):
            positions[n]=(160+col*240,85+row*row_height+slot*120)
    esc=lambda s:html.escape(str(s),quote=True)
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="#777"/></marker></defs>',
        f'<text x="20" y="25" font-family="sans-serif" font-size="16">{esc(title or graph.graph.get("case_id","Pattern"))} — {len(graph)} nodes, {graph.number_of_edges()} edges</text>']
    for u,v in graph.edges:
        x1,y1=positions[u];x2,y2=positions[v]
        if layers[u]//columns!=layers[v]//columns:
            path=f'M{x1},{y1+45} C{x1},{y1+95} {x2},{y2-95} {x2},{y2-45}'
        elif x2-x1>245:
            path=f'M{x1},{y1-45} C{x1},{y1-90} {x2},{y2-90} {x2},{y2-45}'
        else:
            path=f'M{x1+105},{y1} L{x2-108},{y2}'
        parts.append(f'<path d="{path}" fill="none" stroke="#777" stroke-width="1.4" marker-end="url(#arrow)"/>')
    for n in ordered:
        x,y=positions[n];data=graph.nodes[n]
        value=data.get('value','')
        try:
            colour=PALETTE[(int(value.split('_')[-1])-1)%len(PALETTE)]
        except (ValueError,IndexError):
            colour='#777'
        label=data.get('activity',data['label'])
        lines=textwrap.wrap(label.replace('-','- '),width=28,break_long_words=True)
        lines=[line.replace('- ','-') for line in lines]
        lines=[f'#{data.get("local_id",n)}']+lines+[value]
        parts.append(f'<g><title>{esc(data["label"])}</title><rect x="{x-105}" y="{y-45}" width="210" height="90" rx="7" fill="white" stroke="{colour}" stroke-width="2"/>')
        for i,line in enumerate(lines):
            parts.append(f'<text x="{x}" y="{y-(len(lines)-1)*7+i*14}" text-anchor="middle" font-family="sans-serif" font-size="11">{esc(line)}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    return '\n'.join(parts)


def run(graphs_path=GRAPHS,output='outputs/instance_graph_exports'):
    output=Path(output)
    for folder in ['svg','text','graphml']:
        (output/folder).mkdir(parents=True,exist_ok=True)
    graphs=GFileConverter.load(graphs_path)
    node_rows=[];edge_rows=[];index=[]
    with (output/'all_graphs.jsonl').open('w',encoding='utf-8') as stream:
        for number,g in enumerate(graphs):
            case=g.graph['case_id']
            stem=f'{number:04d}_{case}'
            text=[f'{case}: {len(g)} events, {g.number_of_edges()} directed edges']
            for n,d in sorted(g.nodes(data=True),key=lambda pair:pair[1]['local_id']):
                node_rows.append(dict(case_id=case,graph_index=number,global_id=n,**d))
                text.append(f"{d['local_id']:>4} {d['label']} -> "+', '.join(map(str,sorted(g.nodes[v]['local_id'] for v in g.successors(n)))))
            for u,v,d in g.edges(data=True):
                edge_rows.append(dict(case_id=case,graph_index=number,source_global_id=u,target_global_id=v,
                                      source_local_id=g.nodes[u]['local_id'],target_local_id=g.nodes[v]['local_id'],label=d['label']))
            (output/'svg'/f'{stem}.svg').write_text(svg_graph(g),encoding='utf-8')
            (output/'text'/f'{stem}.txt').write_text('\n'.join(text),encoding='utf-8')
            nx.write_graphml(g,output/'graphml'/f'{stem}.graphml')
            stream.write(json.dumps(dict(case_id=case,graph_index=number,
                nodes=[dict(id=n,**d) for n,d in g.nodes(data=True)],
                edges=[dict(source=u,target=v,**d) for u,v,d in g.edges(data=True)]))+'\n')
            index.append(dict(graph_index=number,case_id=case,nodes=len(g),edges=g.number_of_edges(),
                has_branching=any(d>1 for _,d in g.out_degree()),
                svg=f'svg/{stem}.svg',text=f'text/{stem}.txt',graphml=f'graphml/{stem}.graphml'))
            if (number+1)%500==0:
                print(f'Exported {number+1}/{len(graphs)} graphs',flush=True)
    write_csv(output/'nodes.csv',node_rows)
    write_csv(output/'edges.csv',edge_rows)
    write_csv(output/'case_index.csv',index)
    rows='\n'.join(f'<tr><td>{r["graph_index"]}</td><td>{html.escape(r["case_id"])}</td><td>{r["nodes"]}</td><td>{r["edges"]}</td><td>{r["has_branching"]}</td><td><a href="{r["svg"]}">SVG</a> · <a href="{r["text"]}">tekst</a> · <a href="{r["graphml"]}">GraphML</a></td></tr>' for r in index)
    (output/'index.html').write_text('<!doctype html><html lang="nl"><meta charset="utf-8"><title>Alle instance graphs</title><style>body{font:16px system-ui;margin:32px}table{border-collapse:collapse}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}input{padding:10px;width:400px}</style><h1>Alle 3.093 instance graphs</h1><p>Zoek op application-id. SVG is een schaalbare figuur; tekst en GraphML bevatten dezelfde gerichte relaties. Branching bewijst geen concurrency.</p><input id="q" placeholder="Application-id zoeken"><table><thead><tr><th>Index</th><th>Case</th><th>Nodes</th><th>Edges</th><th>Branching</th><th>Bestanden</th></tr></thead><tbody>'+rows+'</tbody></table><script>document.getElementById("q").oninput=function(){for(const row of document.querySelectorAll("tbody tr"))row.hidden=!row.textContent.toLowerCase().includes(this.value.toLowerCase())}</script></html>',encoding='utf-8')
    write_json(output/'summary.json',dict(graphs=len(graphs),nodes=len(node_rows),edges=len(edge_rows),input_sha256=sha256(graphs_path)))
    with zipfile.ZipFile(output/'all_instance_graphs.zip','w',zipfile.ZIP_DEFLATED) as bundle:
        for folder in ['svg','text','graphml']:
            for path in (output/folder).iterdir():
                bundle.write(path,path.relative_to(output))
        for name in ['index.html','case_index.csv','nodes.csv','edges.csv','all_graphs.jsonl','summary.json']:
            bundle.write(output/name,name)
    print(f'All {len(graphs)} graphs exported to {output}',flush=True)

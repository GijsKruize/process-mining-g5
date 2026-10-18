"""Summarise which observed role handoffs are represented by mined motifs."""
import json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
import numpy as np
from .artifacts import GRAPHS,write_json,write_csv
from .graph_io import GFileConverter


def run(output='outputs/paper'):
    output=Path(output)
    patterns=json.loads(Path('outputs/step3_patterns/patterns.json').read_text())
    matrix=pd.read_csv('outputs/step3_patterns/trace_pattern_matrix.csv')
    graphs=GFileConverter.load(GRAPHS)
    cross=[]
    for pattern in patterns:
        nodes={n['id']:n for n in pattern['nodes']}
        pairs=sorted({(nodes[e['source']]['value'],nodes[e['target']]['value']) for e in pattern['edges']
                      if nodes[e['source']]['value']!=nodes[e['target']]['value']})
        if pairs:
            cross.append(dict(pattern_id=pattern['pattern_id'],role_handoffs=pairs))
    edge_counts=Counter();case_counts=Counter()
    for graph in graphs:
        seen=set()
        for u,v in graph.edges:
            pair=graph.nodes[u]['value'],graph.nodes[v]['value']
            if pair[0]!=pair[1]:
                edge_counts[pair]+=1
                seen.add(pair)
        case_counts.update(seen)
    rows=[]
    for pair,count in edge_counts.most_common():
        ids=[p['pattern_id'] for p in cross if list(pair) in p['role_handoffs'] or pair in p['role_handoffs']]
        covered=int(matrix[ids].any(axis=1).sum()) if ids else 0
        rows.append(dict(source=pair[0],target=pair[1],edges=count,cases=case_counts[pair],
                         mined_patterns=' '.join(ids),cases_with_selected_motif=covered))
    cross_ids=[p['pattern_id'] for p in cross]
    write_json(output/'role_handoff_analysis.json',dict(cases=len(graphs),patterns=len(patterns),
        cross_role_patterns=cross,cases_with_any_cross_role_pattern=int(matrix[cross_ids].any(axis=1).sum()) if cross_ids else 0,
        observed_cross_role_edge_types=len(rows),observed_cross_role_pairs=rows,
        caveat='Inferred resource profiles, not confirmed departments. Coverage describes the selected motifs on the existing graph representation; it is not manual-gold recall or proof of real-world handoffs.'))
    write_csv(output/'role_handoff_coverage.csv',rows)
    roles=sorted({r['source'] for r in rows}|{r['target'] for r in rows},key=lambda v:int(v.split('_')[-1]))
    data=np.zeros((len(roles),len(roles)),dtype=int)
    for row in rows:
        data[roles.index(row['source']),roles.index(row['target'])]=row['cases']
    fig,ax=plt.subplots(figsize=(9,7))
    image=ax.imshow(data,cmap='Blues')
    for i in range(len(roles)):
        for j in range(len(roles)):
            ax.text(j,i,str(data[i,j]) if data[i,j] else '-',ha='center',va='center',
                    color='white' if data[i,j]>data.max()/2 else '#222',fontsize=9)
    pairs={tuple(pair) for pattern in cross for pair in pattern['role_handoffs']}
    for a,b in pairs:
        ax.add_patch(Rectangle((roles.index(b)-.5,roles.index(a)-.5),1,1,fill=False,edgecolor='#d62728',linewidth=3))
    ax.set(xticks=range(len(roles)),yticks=range(len(roles)),xticklabels=roles,yticklabels=roles,
           xlabel='Target inferred role',ylabel='Source inferred role',
           title='Observed graph handoffs: cases per role pair\nRed outline: represented in selected SUBDUE motifs')
    fig.colorbar(image,ax=ax,label='Number of cases containing a directed role-changing edge')
    fig.tight_layout()
    for suffix in ['png','pdf']:
        fig.savefig(output/f'role_handoff_coverage.{suffix}',dpi=200)
    plt.close(fig)
    return rows

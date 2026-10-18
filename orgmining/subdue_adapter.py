"""Adapter to the assignment's upstream SUBDUE, with equivalent set-index optimizations.

Do not use upstream nx_subdue: its loader passes a method/bool where its JSON
loader expects the string 'true', losing edge direction. Only labels are matched.
Upstream's bounded approximate matcher is retained for discovery. Support and
occurrences are independently verified with exact NetworkX monomorphism.
"""
import contextlib
import importlib
import sys
from collections import defaultdict
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'vendor/subdue/src'


def load_engine():
    if not (SOURCE/'Subdue.py').exists():
        raise FileNotFoundError('Download holderlb/Subdue into vendor/subdue first.')
    sys.path.insert(0,str(SOURCE))
    return importlib.import_module('Subdue')


@contextlib.contextmanager
def indexed_operations(engine):
    """Keep upstream search/scoring/matching; replace quadratic list membership.

    One-edge grouping applies to our directed, labelled simple graphs, without
    self-loops. Greedy instance order and upstream overlap rules are preserved.
    """
    import Graph
    import Pattern
    old_initial=engine.GetInitialPatterns
    old_insert=Pattern.InsertNewInstance
    old_overlap=Pattern.InstancesOverlap
    old_extend=Pattern.ExtendPattern
    indices={}
    overlaps={}

    def signature(instance):
        return frozenset(e.id for e in instance.edges)

    def insert(items, instance):
        key=id(items)
        if key not in indices or indices[key][0] is not items:
            indices[key]=(items,{signature(i) for i in items})
        seen=indices[key][1]
        sig=signature(instance)
        if sig not in seen:
            items.append(instance)
            seen.add(sig)

    def overlap(mode,items,instance):
        key=(mode,id(items))
        if key not in overlaps or overlaps[key][0] is not items:
            overlaps[key]=[items,0,set()]
        entry=overlaps[key]
        for i in items[entry[1]:]:
            if mode=='edge':
                entry[2].add(signature(i))
            elif mode=='vertex':
                entry[2].update(e.id for e in i.edges)
            else:
                entry[2].update(v.id for v in i.vertices)
        entry[1]=len(items)
        if mode=='edge':
            return signature(instance) in entry[2]
        candidates=(e.id for e in instance.edges) if mode=='vertex' else (v.id for v in instance.vertices)
        return any(x in entry[2] for x in candidates)

    def initial(parameters,graph):
        groups={}
        for edge in graph.edges.values():
            if not edge.directed or edge.source==edge.target:
                raise ValueError('Indexed discovery expects directed loop-free input')
            key=(tuple(sorted(edge.source.attributes.items())),
                 tuple(sorted(edge.target.attributes.items())),tuple(sorted(edge.attributes.items())))
            groups.setdefault(key,[]).append(edge)
        patterns=[]
        for edges in groups.values():
            remaining=edges
            while remaining:
                selected=[]
                rejected=[]
                for edge in remaining:
                    instance=Pattern.CreateInstanceFromEdge(edge)
                    if not overlap(parameters.overlap,selected,instance):
                        selected.append(instance)
                    else:
                        rejected.append(edge)
                if len(selected)>1:
                    pattern=Pattern.Pattern()
                    pattern.definition=Graph.CreateGraphFromEdge(next(iter(selected[0].edges)))
                    pattern.instances=selected
                    pattern.evaluate(graph)
                    patterns.append(pattern)
                remaining=rejected
        overlaps.clear()
        return patterns

    def extend(parameters,pattern):
        try:
            return old_extend(parameters,pattern)
        finally:
            indices.clear()
            overlaps.clear()

    engine.GetInitialPatterns=initial
    Pattern.InsertNewInstance=insert
    Pattern.InstancesOverlap=overlap
    Pattern.ExtendPattern=extend
    try:
        yield
    finally:
        engine.GetInitialPatterns=old_initial
        Pattern.InsertNewInstance=old_insert
        Pattern.InstancesOverlap=old_overlap
        Pattern.ExtendPattern=old_extend

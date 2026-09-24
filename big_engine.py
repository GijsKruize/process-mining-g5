"""Native, dependency-light port of the BIG "instance graph" algorithm.

The JM0211 assignment says to "leverage the provided BIG library" for step 2.
No jar/binary/source was actually distributed for this course run, but BIG
itself is open source: its GUI wrapper (Docker + Spark + Tkinter) and its
underlying algorithm, "newbig2.py", are published by the same research group
that set this assignment (Diamantini, Genga, Mircoli, Potena) at
https://github.com/a-mircoli/big-gui — see app/BIG2/BigSpark/newbig2.py there.

That algorithm's core (function ``big_partitioned`` in the original file) does
not actually depend on Spark: Spark is only used to fan the per-trace work
out across a cluster for very large logs. It aligns each trace against the
Petri net (pm4py, alignment-based conformance checking), derives the causal
relation of the net (which transition can directly enable which), builds a
provisional instance graph from the aligned trace, and then repairs it to
remove/relink the alignment's synthetic "skip"/"insert" steps.

The functions below are ported from that algorithm (same logic, same output
format), with the Spark driver, the Tkinter GUI, the IPython/graphviz live
preview, and the hard-coded "/home/jovyan/work/..." project paths removed,
since none of that is needed to run BIG's actual graph-construction algorithm
as a plain library call against a log this size. Everything here is
attributable to the original authors; only the plumbing around it is new.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments
from pm4py.objects.log.obj import Trace
from pm4py.objects.petri_net.obj import PetriNet

Node = Tuple[int, str]
Edge = Tuple[Node, Node]


def find_successors_of_transition(net: PetriNet, transition: PetriNet.Transition) -> set:
    sources = {transition}
    targets = set()
    visited = set()
    while sources:
        source = sources.pop()
        if not (isinstance(source, PetriNet.Transition) and source.label is not None):
            visited.add(source)
        for arc in source.out_arcs:
            if arc.target in visited:
                continue
            if isinstance(arc.target, PetriNet.Transition) and arc.target.label is not None:
                targets.add(arc.target)
            else:
                sources.add(arc.target)
    return targets


def find_successors(net: PetriNet) -> Dict[PetriNet.Transition, set]:
    return {
        transition: find_successors_of_transition(net, transition)
        for transition in net.transitions
        if transition.label is not None
    }


def find_causal_relationships(net: PetriNet) -> List[Tuple[str, str]]:
    """Pairs (a, b) of activity labels such that a can directly enable b."""
    dict_succ = find_successors(net)
    result = []
    for key, item in dict_succ.items():
        for s in item:
            result.append((key.label, s.label))
    return result


def pick_aligned_trace(trace: Trace, net, initial_marking, final_marking):
    aligned_traces = alignments.apply_trace(trace, net, initial_marking, final_marking)

    model_side = [(i + 1, edge[1]) for i, edge in enumerate(aligned_traces["alignment"])]
    log_side = [(i + 1, edge[0]) for i, edge in enumerate(aligned_traces["alignment"])]
    return [model_side], [log_side]


def mapping(l1: List[Node], l2: List[Node]):
    """Align model-side and log-side alignment steps; flag insertions."""
    result_map = [0] * len(l1)
    id1 = 0
    id2 = 0
    ins: List[Node] = []

    for i in range(len(l1)):
        e1 = l1[i]
        e2 = l2[i]
        if e1[1] == e2[1]:
            id1 += 1
            id2 += 1
            result_map[i] = (e1[1], id1, id2)
        elif e1[1] == ">>":  # log move with no matching model move
            id1 += 1
            result_map[i] = (e2[1], id1, 0)
        elif e2[1] == ">>":  # model move with no matching log event
            id2 += 1
            result_map[i] = (e1[1], 0, id2)

    for j in range(len(l1)):
        e1 = l1[j]
        e3 = result_map[j]
        if e1[1] == ">>":
            id2 += 1
            result_map[j] = (e3[0], e3[1], id2)
            ins.append((e3[0], e3[1], id2))

    return result_map, ins


def compliant_trace(trace: List[Node]) -> List[Node]:
    t = []
    node_id = 0
    for event in trace:
        if event[1] == ">>":
            continue
        node_id += 1
        t.append((node_id, event[1]))
    return t


def extract_instance_graph(
    trace: List[Node], causal_relations: List[Tuple[str, str]]
) -> Tuple[List[Node], List[Edge]]:
    v = list(trace)
    w: List[Edge] = []
    for i in range(len(v)):
        for k in range(i + 1, len(v)):
            e1 = v[i]
            e2 = v[k]
            if (e1[1], e2[1]) in causal_relations:
                flag_e1 = True
                for s in range(i + 1, k):
                    if (e1[1], v[s][1]) in causal_relations:
                        flag_e1 = False
                        break
                flag_e2 = True
                for s in range(i + 1, k):
                    if (v[s][1], e2[1]) in causal_relations:
                        flag_e2 = False
                        break
                if flag_e1 or flag_e2:
                    w.append((e1, e2))
    return v, w


def edge_number(w: List[Edge]) -> List[Tuple[int, int]]:
    return [(arc[0][0], arc[1][0]) for arc in w]


def node_number(v: List[Node]) -> List[int]:
    return [node[0] for node in v]


def isolated(node: int, w_num: List[Tuple[int, int]]) -> bool:
    return not any(arc[0] == node or arc[1] == node for arc in w_num)


def is_path(a: int, b: int, w_num: List[Tuple[int, int]], v: List[Node]) -> bool:
    if (a, b) in w_num:
        return True
    for node in v:
        if (a, node[0]) in w_num:
            if is_path(node[0], b, w_num, v):
                return True
    return False


def del_repair(v: List[Node], w: List[Edge], result_map, deletion):
    """Remove a model-only (e.g. silent-transition) node, relinking around it."""
    e_rem_pred: List[Edge] = []
    e_rem_succ: List[Edge] = []
    pred: List[Node] = []
    succ: List[Node] = []

    to_del = (deletion[2], deletion[0])
    for arc in w:
        if arc[1] == to_del:
            e_rem_pred.append((arc[0], to_del))
        if arc[0] == to_del:
            e_rem_succ.append((to_del, arc[1]))

    for a in e_rem_pred:
        pred.append(a[0])
    for b in e_rem_succ:
        succ.append(b[1])

    for arc in e_rem_pred:
        w.remove(arc)
    for arc in e_rem_succ:
        w.remove(arc)

    v.remove(to_del)

    for p in pred:
        for s in succ:
            if (p, s) not in w:
                w.append((p, s))

    return v, w


def ins_repair(v: List[Node], w: List[Edge], result_map, insertion, v_n, ins_list, v_pos):
    """Splice a log-only node (an event the model didn't predict) into the graph."""
    pred: List[Node] = []
    succ: List[Node] = []
    e_rem: List[Edge] = []

    v.insert(insertion[1] - 1, (insertion[2], insertion[0]))
    v_pos.insert(insertion[1] - 1, (insertion[2], insertion[0]))
    pos_t = [insertion[1]]

    w_num = edge_number(w)

    for p in pos_t:
        if p < len(v_pos):
            position = v_pos[p]
        else:
            position = v[-1]
        pos = position[0]
        pos_pred = v_pos[p - 2][0]

        if is_path(pos_pred, pos, w_num, v):
            for arc in w:
                if pos == arc[1][0] and arc not in e_rem:
                    e_rem.append(arc)
                    pred.append(arc[0])
            for n in pred:
                for arc in w:
                    if arc[0] == n and arc not in e_rem:
                        e_rem.append(arc)
        else:
            for arc in w:
                if pos_pred == arc[0][0] and arc not in e_rem:
                    e_rem.append(arc)
                    pred.append(arc[0])
                elif pos_pred == arc[1][0] and pos_pred == v_n[-1]:
                    pred.append(arc[1])
                elif isolated(pos_pred, w_num):
                    pass

    for arc in e_rem:
        if arc[1] not in succ:
            succ.append(arc[1])

    for arc in e_rem:
        if arc in w:
            w.remove(arc)

    new_node = (insertion[2], insertion[0])
    for p in pred:
        if (p, new_node) not in w:
            w.append((p, new_node))
    for s in succ:
        if (new_node, s) not in w:
            w.append((new_node, s))

    return v, w


def relabel(w: List[Edge], result_map, v: List[Node]) -> Tuple[List[Edge], List[Node]]:
    """Map internal (mapping-id, label) node keys back to (event-id, label)."""
    w1: List[Edge] = []
    v1: List[Node] = []

    for arc in w:
        a0, a1 = arc
        for e in result_map:
            if a0 == (e[2], e[0]):
                for f in result_map:
                    if a1 == (f[2], f[0]):
                        w1.append(((e[1], e[0]), (f[1], f[0])))

    for node in v:
        for e in result_map:
            if node == (e[2], e[0]):
                v1.append((e[1], e[0]))

    return w1, v1


def build_instance_graph(
    trace: Trace, net: PetriNet, initial_marking, final_marking, causal_relations
) -> Tuple[List[Node], List[Edge]]:
    """Run BIG's alignment + repair algorithm for a single trace.

    Returns (nodes, edges): nodes are (event_id, activity_label) pairs,
    numbered 1..n in trace order; edges are the derived causal relations
    between them, exactly as BIG's own ``.g`` output encodes them.
    """
    aligned, actual = pick_aligned_trace(trace, net, initial_marking, final_marking)
    result_map, ins = mapping(aligned[0], actual[0])

    compliant = compliant_trace(aligned[0])
    v, w = extract_instance_graph(compliant, causal_relations)

    v_n = node_number(v)
    v_pos = list(v)
    for el in result_map:
        if el[1] == 0:
            v_pos.remove((el[2], el[0]))

    for insertion in ins:
        v, w = ins_repair(v, w, result_map, insertion, v_n, ins, v_pos)

    deletions = [el for el in result_map if el[1] == 0]
    for deletion in deletions:
        v, w = del_repair(v, w, result_map, deletion)

    w1, v1 = relabel(w, result_map, v)
    v1.sort()
    w1.sort()
    return v1, w1

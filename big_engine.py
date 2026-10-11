"""BIG's instance-graph algorithm as plain Python functions.

This is the course-provided ``BIG.py`` (Diamantini, Genga, Mircoli, Potena)
with the plumbing around it replaced: it is called per trace instead of
writing ``graph.g`` itself. The algorithm is unchanged:

1. align the trace with the Petri net (cost-based conformance checking),
2. build the instance graph of the model-compliant part of the alignment
   with the instance-ordering rule (Definition 6 of Diamantini et al., 2016),
3. repair the graph around inserted and deleted events (Algorithm 1).

Changes with respect to the provided ``BIG.py`` and why they are safe
---------------------------------------------------------------------
* The work is split into ``align_labels`` (step 1) and
  ``instance_graph_from_alignment`` (steps 2-3). The graph structure depends
  only on the sequence of activity labels, so the caller can compute it once
  per distinct label sequence and can run the alignments in parallel.
* The causal relations are a ``set`` instead of a ``list``. They are only
  ever used for membership tests inside a triple loop, where a list scan was
  the main avoidable cost. The result is identical.
* ``is_path`` gives the same answers as the original but no longer recurses
  into every successor (see its docstring). A correct reachability test is
  available as an option, off by default so that the output stays comparable
  with the provided library.
* Alignments are computed with Dijkstra search by default instead of A*
  (see ``ALIGNMENT_VARIANTS``). Both return an optimal alignment, and the
  paper notes that the repair procedure does not depend on the conformance
  checking technique as long as it reports kind and position of each anomaly.
* Alignments are made repeatable (see ``determinism.py``).

Checks that were run on this module
-----------------------------------
* ``tests/test_big_engine.py``: the worked examples of the paper (Figures 5,
  8 and 9) come out as published.
* Given the same alignments, steps 2-3 produce exactly the graphs of the
  previous, line-by-line port of ``BIG.py`` (1,000 distinct label sequences
  of the BPI 2017 log, on the course-provided net and on a discovered one).
* With the course-provided Petri net and ``astar`` alignments, all 3,093
  graphs have the same nodes and the same number of edges as the provided
  ``BPI2017Denied.g``, and 1,113 are identical edge for edge. No trace fits
  that net, so every trace has several optimal alignments; the remaining
  differences are consistent with a different choice among them.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Set, Tuple

import determinism  # noqa: F401  (must be imported before Petri net objects are created)
from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments
from pm4py.objects.log.obj import Event, Trace
from pm4py.objects.petri_net.obj import PetriNet

Node = Tuple[int, str]
Edge = Tuple[Node, Node]
AlignmentMove = Tuple[Optional[str], Optional[str]]  # (log label, model label)

SKIP = ">>"

# Both variants return an *optimal* alignment (fewest insertions and deletions).
# "dijkstra" is the default because it is much faster on the loop-heavy nets the
# Inductive Miner discovers for this kind of log: on the BPI 2017 log with role
# labels it needed 0.12s per trace against 1.9s for "astar", with the same number
# of insertions and deletions on every trace we compared. "astar" (A* with the
# state-equation heuristic) is what pm4py and the provided BIG.py use by default;
# it can be the faster one on nets with a lot of concurrency.
ALIGNMENT_VARIANTS = {
    "dijkstra": alignments.Variants.VERSION_DIJKSTRA_LESS_MEMORY,
    "astar": alignments.Variants.VERSION_STATE_EQUATION_A_STAR,
}
DEFAULT_ALIGNMENT_VARIANT = "dijkstra"


# --------------------------------------------------------------------------
# Causal relations from the Petri net
# --------------------------------------------------------------------------

def find_successors_of_transition(net: PetriNet, transition: PetriNet.Transition) -> set:
    """Labelled transitions reachable from ``transition`` through places and silent transitions."""
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


def find_causal_relationships(net: PetriNet) -> Set[Tuple[str, str]]:
    """Pairs ``(a, b)`` of labels such that ``a`` can directly enable ``b`` in the net.

    This is the causal relation CR of the paper (Definition 5). Because the
    net is discovered on the labels produced by step 1, the pairs are
    activity-attribute pairs, i.e. the paper's entity specifications.

    Returned as a set: the original returned a list, and every later use is a
    membership test.
    """
    relations = set()
    for transition in net.transitions:
        if transition.label is None:
            continue
        for successor in find_successors_of_transition(net, transition):
            relations.add((transition.label, successor.label))
    return relations


# --------------------------------------------------------------------------
# Step 1: alignment
# --------------------------------------------------------------------------

def align_labels(labels: Sequence[str], net: PetriNet, initial_marking, final_marking,
                 max_seconds: Optional[float] = None,
                 variant: str = DEFAULT_ALIGNMENT_VARIANT) -> Optional[List[AlignmentMove]]:
    """Optimal alignment of a label sequence with the net, or ``None`` on timeout.

    The trace is rebuilt from its labels alone so that this function has the
    same input, and therefore the same output, whether it is called in the
    main process or in a worker process.

    The hash counter is reset first: this pins down which of several equally
    good alignments is returned and makes the answer independent of the
    traces aligned before (see ``determinism.py``).

    The variant's own ``apply`` is called instead of pm4py's ``apply_trace``
    wrapper. The wrapper returns the same alignment but first aligns the
    empty trace on every call (to compute a fitness value BIG never uses) and
    fails with a TypeError when the search times out.
    """
    trace = Trace()
    for label in labels:
        trace.append(Event({"concept:name": label}))

    variant_module = ALIGNMENT_VARIANTS[variant].value
    parameters = {}
    if max_seconds is not None:
        parameters[variant_module.Parameters.PARAM_MAX_ALIGN_TIME_TRACE] = max_seconds

    determinism.reset_counter(determinism.ALIGNMENT_BASE)
    result = variant_module.apply(trace, net, initial_marking, final_marking, parameters=parameters)
    if result is None:
        return None
    return [(move[0], move[1]) for move in result["alignment"]]


def count_irregular_moves(alignment: Sequence[AlignmentMove]) -> Tuple[int, int]:
    """Number of (insertions, deletions) in an alignment.

    An insertion is a log move (an event the model does not allow at that
    position). A deletion is a model move on a *labelled* transition (an
    activity the model requires but the trace lacks). Model moves on silent
    transitions are routing steps, not irregularities.
    """
    insertions = sum(1 for log_label, model_label in alignment if model_label == SKIP)
    deletions = sum(
        1 for log_label, model_label in alignment
        if log_label == SKIP and model_label is not None
    )
    return insertions, deletions


# --------------------------------------------------------------------------
# Steps 2-3: instance graph and repair (logic of the provided BIG.py)
# --------------------------------------------------------------------------

def mapping(l1: List[Node], l2: List[Node]):
    """Pair up model-side and log-side alignment steps; list the insertions.

    Each entry is ``(label, log position, model position)``. A deletion has
    log position 0. Insertions get model positions after the last real one.
    """
    result_map = [0] * len(l1)
    id1 = 0
    id2 = 0
    ins: List[Tuple[str, int, int]] = []

    for i in range(len(l1)):
        e1 = l1[i]
        e2 = l2[i]
        if e1[1] == e2[1]:
            id1 += 1
            id2 += 1
            result_map[i] = (e1[1], id1, id2)
        elif e1[1] == SKIP:  # log move: event with no matching model step
            id1 += 1
            result_map[i] = (e2[1], id1, 0)
        elif e2[1] == SKIP:  # model move: model step with no matching event
            id2 += 1
            result_map[i] = (e1[1], 0, id2)

    for j in range(len(l1)):
        e1 = l1[j]
        e3 = result_map[j]
        if e1[1] == SKIP:
            id2 += 1
            result_map[j] = (e3[0], e3[1], id2)
            ins.append((e3[0], e3[1], id2))

    return result_map, ins


def compliant_trace(trace: List[Node]) -> List[Node]:
    """The model side of the alignment without the skip symbols."""
    t = []
    node_id = 0
    for event in trace:
        if event[1] == SKIP:
            continue
        node_id += 1
        t.append((node_id, event[1]))
    return t


def extract_instance_graph(trace: List[Node], causal_relations) -> Tuple[List[Node], List[Edge]]:
    """Instance ordering of Definition 6.

    There is an edge from event i to a later event k if their labels are
    causally related and either no event in between is a causal successor of
    i or no event in between is a causal predecessor of k.
    """
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


def is_path(a: int, b: int, w_num, v: List[Node], strict: bool = False) -> bool:
    """Is there a path from node ``a`` to node ``b``?

    ``strict=False`` (default) reproduces the provided ``BIG.py`` exactly.
    That implementation returns True for a direct edge and otherwise
    recurses into *every* successor of ``a`` but keeps only the answer of the
    last one (in the order of ``v``). So its answer is "is ``b`` reachable by
    always following the last successor". We follow that chain directly:
    same answer, linear instead of exponential time, and it cannot loop
    forever. We keep this behaviour as the default because the output is then
    comparable with the library the course provides.

    ``strict=True`` is a real reachability test (a path through *any*
    successor counts). The two differ only when the path to ``b`` does not go
    through the last successor, which makes the original treat a sequential
    insertion as an insertion inside a parallel block.
    """
    edges = w_num if isinstance(w_num, (set, frozenset)) else set(w_num)

    if strict:
        stack = [a]
        seen = {a}
        while stack:
            current = stack.pop()
            if (current, b) in edges:
                return True
            for node in v:
                if (current, node[0]) in edges and node[0] not in seen:
                    seen.add(node[0])
                    stack.append(node[0])
        return False

    seen = set()
    current = a
    while current not in seen:
        if (current, b) in edges:
            return True
        seen.add(current)
        last_successor = None
        for node in v:
            if (current, node[0]) in edges:
                last_successor = node[0]
        if last_successor is None:
            return False
        current = last_successor
    return False


def del_repair(v: List[Node], w: List[Edge], result_map, deletion):
    """Deletion repair: remove a model-only node and link its predecessors to its successors."""
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
            w.append((p, s))

    return v, w


def ins_repair(v: List[Node], w: List[Edge], result_map, insertion, v_n, ins_list, v_pos,
               strict_path_check: bool = False):
    """Insertion repair: splice a log-only event between its neighbours in the trace."""
    pred: List[Node] = []
    succ: List[Node] = []
    e_rem: List[Edge] = []

    v.insert(insertion[1] - 1, (insertion[2], insertion[0]))
    v_pos.insert(insertion[1] - 1, (insertion[2], insertion[0]))
    pos_t = [insertion[1]]

    w_num = set(edge_number(w))

    for p in pos_t:
        if p < len(v_pos):
            position = v_pos[p]
        else:
            position = v[-1]
        pos = position[0]
        pos_pred = v_pos[p - 2][0]

        if is_path(pos_pred, pos, w_num, v, strict=strict_path_check):
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
    """Replace the internal (model position, label) keys by (log position, label).

    After this step the node id is the 1-based position of the event in the
    trace, which is what lets the caller attach per-event information.
    """
    by_internal_key = {}
    for entry in result_map:
        # setdefault keeps the first entry for a key, as the original nested
        # loops did; keys are unique in practice because model positions are.
        by_internal_key.setdefault((entry[2], entry[0]), (entry[1], entry[0]))

    w1: List[Edge] = []
    for source, target in w:
        if source in by_internal_key and target in by_internal_key:
            w1.append((by_internal_key[source], by_internal_key[target]))

    v1: List[Node] = [by_internal_key[node] for node in v if node in by_internal_key]
    return w1, v1


def instance_graph_from_alignment(alignment: Sequence[AlignmentMove], causal_relations,
                                  strict_path_check: bool = False) -> Tuple[List[Node], List[Edge]]:
    """Build and repair the instance graph for one aligned trace.

    Returns ``(nodes, edges)``. Nodes are ``(event position, label)`` pairs
    numbered 1..n in trace order; edges are pairs of nodes.
    """
    model_side = [(i + 1, move[1]) for i, move in enumerate(alignment)]
    log_side = [(i + 1, move[0]) for i, move in enumerate(alignment)]
    result_map, ins = mapping(model_side, log_side)

    compliant = compliant_trace(model_side)
    v, w = extract_instance_graph(compliant, causal_relations)

    v_n = node_number(v)
    v_pos = list(v)
    for el in result_map:
        if el[1] == 0:
            v_pos.remove((el[2], el[0]))

    for insertion in ins:
        v, w = ins_repair(v, w, result_map, insertion, v_n, ins, v_pos,
                          strict_path_check=strict_path_check)

    deletions = [el for el in result_map if el[1] == 0]
    for deletion in deletions:
        v, w = del_repair(v, w, result_map, deletion)

    w1, v1 = relabel(w, result_map, v)
    v1.sort()
    w1.sort()
    return v1, w1


def build_instance_graph(trace: Trace, net: PetriNet, initial_marking, final_marking,
                         causal_relations, strict_path_check: bool = False,
                         variant: str = DEFAULT_ALIGNMENT_VARIANT):
    """Align one pm4py trace and return its repaired instance graph (convenience wrapper)."""
    labels = [event["concept:name"] for event in trace]
    alignment = align_labels(labels, net, initial_marking, final_marking, variant=variant)
    return instance_graph_from_alignment(alignment, causal_relations,
                                         strict_path_check=strict_path_check)

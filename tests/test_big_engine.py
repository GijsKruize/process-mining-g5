"""Checks big_engine against the worked examples of Diamantini, Genga & Potena (2016).

Run from the repository root with:  python -m unittest discover -s tests -v

The process is the software-development example of the paper (Fig. 1) with
the entity specifications used in section 5.1:

    M3WR -> M4RR -> (M1WD || M2WD) -> M5RD -> M4WC -> M1TC
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import big_engine  # noqa: E402
from pm4py.objects.petri_net.obj import Marking, PetriNet  # noqa: E402
from pm4py.objects.petri_net.utils import petri_utils  # noqa: E402

SKIP = big_engine.SKIP


def software_process_net():
    """Petri net for M3WR -> M4RR -> AND(M1WD, M2WD) -> M5RD -> M4WC -> M1TC."""
    net = PetriNet("software development")
    places = {name: PetriNet.Place(name) for name in
              ["start", "p1", "p2", "a1", "a2", "b1", "b2", "p3", "p4", "p5", "end"]}
    for place in places.values():
        net.places.add(place)

    def transition(name, label=None):
        new = PetriNet.Transition(name, label)
        net.transitions.add(new)
        return new

    def arc(source, target):
        petri_utils.add_arc_from_to(source, target, net)

    wr, rr = transition("wr", "M3WR"), transition("rr", "M4RR")
    split, join = transition("split"), transition("join")  # silent AND split/join
    wd1, wd2 = transition("wd1", "M1WD"), transition("wd2", "M2WD")
    rd, wc, tc = transition("rd", "M5RD"), transition("wc", "M4WC"), transition("tc", "M1TC")

    arc(places["start"], wr); arc(wr, places["p1"])
    arc(places["p1"], rr); arc(rr, places["p2"])
    arc(places["p2"], split)
    arc(split, places["a1"]); arc(split, places["a2"])
    arc(places["a1"], wd1); arc(wd1, places["b1"])
    arc(places["a2"], wd2); arc(wd2, places["b2"])
    arc(places["b1"], join); arc(places["b2"], join)
    arc(join, places["p3"])
    arc(places["p3"], rd); arc(rd, places["p4"])
    arc(places["p4"], wc); arc(wc, places["p5"])
    arc(places["p5"], tc); arc(tc, places["end"])

    return net, Marking({places["start"]: 1}), Marking({places["end"]: 1})


class CausalRelationTest(unittest.TestCase):
    def test_causal_relations_skip_silent_transitions(self):
        net, _, _ = software_process_net()
        relations = big_engine.find_causal_relationships(net)
        self.assertEqual(relations, {
            ("M3WR", "M4RR"),
            ("M4RR", "M1WD"), ("M4RR", "M2WD"),      # through the silent AND split
            ("M1WD", "M5RD"), ("M2WD", "M5RD"),      # through the silent AND join
            ("M5RD", "M4WC"), ("M4WC", "M1TC"),
        })


class PaperExamplesTest(unittest.TestCase):
    def setUp(self):
        self.net, self.initial, self.final = software_process_net()
        self.relations = big_engine.find_causal_relationships(self.net)

    def graph(self, labels):
        alignment = big_engine.align_labels(labels, self.net, self.initial, self.final)
        nodes, edges = big_engine.instance_graph_from_alignment(alignment, self.relations)
        return alignment, nodes, edges

    def test_regular_trace_shows_parallelism(self):
        """Fig. 5: the two WriteDocuments events are parallel, not sequential."""
        labels = ["M3WR", "M4RR", "M1WD", "M2WD", "M5RD", "M4WC", "M1TC"]
        alignment, nodes, edges = self.graph(labels)
        self.assertEqual(big_engine.count_irregular_moves(alignment), (0, 0))
        self.assertEqual(nodes, list(enumerate(labels, start=1)))
        self.assertEqual(set(edges), {
            ((1, "M3WR"), (2, "M4RR")),
            ((2, "M4RR"), (3, "M1WD")), ((2, "M4RR"), (4, "M2WD")),
            ((3, "M1WD"), (5, "M5RD")), ((4, "M2WD"), (5, "M5RD")),
            ((5, "M5RD"), (6, "M4WC")), ((6, "M4WC"), (7, "M1TC")),
        })

    def test_same_graph_for_other_interleaving(self):
        """Section 4.2: swapping the parallel events gives the same graph structure."""
        _, _, edges_a = self.graph(["M3WR", "M4RR", "M1WD", "M2WD", "M5RD", "M4WC", "M1TC"])
        _, _, edges_b = self.graph(["M3WR", "M4RR", "M2WD", "M1WD", "M5RD", "M4WC", "M1TC"])
        by_label = lambda edges: {(source[1], target[1]) for source, target in edges}
        self.assertEqual(by_label(edges_a), by_label(edges_b))

    def test_insertion_repair(self):
        """Fig. 8: an extra M4RR after the design phase is spliced in before M5RD."""
        labels = ["M3WR", "M4RR", "M1WD", "M2WD", "M4RR", "M5RD", "M4WC", "M1TC"]
        alignment, nodes, edges = self.graph(labels)
        self.assertEqual(big_engine.count_irregular_moves(alignment), (1, 0))
        self.assertEqual(nodes, list(enumerate(labels, start=1)))
        self.assertEqual(set(edges), {
            ((1, "M3WR"), (2, "M4RR")),
            ((2, "M4RR"), (3, "M1WD")), ((2, "M4RR"), (4, "M2WD")),
            ((3, "M1WD"), (5, "M4RR")), ((4, "M2WD"), (5, "M4RR")),   # added
            ((5, "M4RR"), (6, "M5RD")),                                 # added
            ((6, "M5RD"), (7, "M4WC")), ((7, "M4WC"), (8, "M1TC")),
        })

    def test_deletion_repair(self):
        """Fig. 9: a missing M5RD is bridged from both WriteDocuments events to M4WC."""
        labels = ["M3WR", "M4RR", "M1WD", "M2WD", "M4WC", "M1TC"]
        alignment, nodes, edges = self.graph(labels)
        self.assertEqual(big_engine.count_irregular_moves(alignment), (0, 1))
        self.assertEqual(nodes, list(enumerate(labels, start=1)))
        self.assertEqual(set(edges), {
            ((1, "M3WR"), (2, "M4RR")),
            ((2, "M4RR"), (3, "M1WD")), ((2, "M4RR"), (4, "M2WD")),
            ((3, "M1WD"), (5, "M4WC")), ((4, "M2WD"), (5, "M4WC")),   # added
            ((5, "M4WC"), (6, "M1TC")),
        })


class PathCheckTest(unittest.TestCase):
    """Documents the difference between the provided library's is_path and a real one."""

    def test_last_successor_rule_versus_reachability(self):
        nodes = [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
        edges = {(1, 2), (1, 3), (2, 4)}  # 1 -> 2 -> 4 and a dead end 1 -> 3
        # A path 1 -> 4 exists, but not through 1's last successor (3).
        self.assertFalse(big_engine.is_path(1, 4, edges, nodes))
        self.assertTrue(big_engine.is_path(1, 4, edges, nodes, strict=True))
        # Both agree when the path runs through the last successor.
        self.assertTrue(big_engine.is_path(1, 4, {(1, 2), (2, 4)}, nodes))
        self.assertTrue(big_engine.is_path(1, 4, {(1, 2), (2, 4)}, nodes, strict=True))


if __name__ == "__main__":
    unittest.main()

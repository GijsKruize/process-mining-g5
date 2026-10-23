"""Unit tests for the evaluation against the gold standard.

Run from the project root:  python -m unittest discover tests -v
"""
import unittest

import networkx as nx

from orgmining.evaluation import (FrequentPathBaseline, GoldStandard, GoldPattern, contains,
                                  evaluate, parse_edges)


def labelled_chain(*labels):
    graph = nx.DiGraph()
    for index, label in enumerate(labels):
        graph.add_node(index, label=label)
    graph.add_edges_from((i, i + 1) for i in range(len(labels) - 1))
    return graph


GOLD = GoldStandard([GoldPattern("G1", "ab", parse_edges("A -> B")),
                     GoldPattern("G2", "cd", parse_edges("C -> D; D -> E"))])


class ContainsTest(unittest.TestCase):
    def test_labels_and_direction_must_match(self):
        self.assertTrue(contains(labelled_chain("X", "A", "B"), parse_edges("A -> B")))
        self.assertFalse(contains(labelled_chain("B", "A"), parse_edges("A -> B")))
        self.assertFalse(contains(labelled_chain("A", "X", "B"), parse_edges("A -> B")))


class EvaluateTest(unittest.TestCase):
    def test_precision_and_recall(self):
        discovered = [("P1", labelled_chain("X", "A", "B")),   # contains G1 -> correct
                      ("P2", labelled_chain("D", "E")),        # part of G2 -> correct
                      ("P3", labelled_chain("Y", "Z"))]        # unrelated -> wrong
        result = evaluate("test", discovered, GOLD)
        self.assertAlmostEqual(result.precision, 2 / 3)
        self.assertEqual(result.recall, 0.5)                   # G1 found, G2 only partly
        self.assertEqual(result.found, ["G1"])
        self.assertAlmostEqual(result.edge_recall, 2 / 3)      # A->B and D->E of 3 gold edges


class BaselineTest(unittest.TestCase):
    def test_most_frequent_paths_first(self):
        graphs = [labelled_chain("A", "B", "C"), labelled_chain("A", "B", "C"),
                  labelled_chain("X", "B", "C")]
        patterns = FrequentPathBaseline(length=1).discover(graphs, top=2)
        first = patterns[0][1]
        self.assertEqual([first.nodes[n]["label"] for n in first], ["B", "C"])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for reading and plotting instance graphs.

Run from the project root:  python -m unittest discover tests -v
"""
import tempfile
import unittest
from pathlib import Path

import networkx as nx

from orgmining.visualization import InstanceGraphViewer, short_tag, wrap_label


def parallel_graph():
    """start -> (A || B) -> end, roles Role_1 and Role_2."""
    graph = nx.DiGraph(graph_index=0, case_id="case_1")
    for node, (activity, role) in enumerate([("start", "Role_1"), ("A", "Role_1"),
                                             ("B", "Role_2"), ("end", "Role_2")]):
        graph.add_node(node, label=f"{activity}_{role}", activity=activity, value=role,
                       local_id=node + 1)
    graph.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
    return graph


class InstanceGraphViewerTest(unittest.TestCase):
    def setUp(self):
        self.viewer = InstanceGraphViewer([parallel_graph()])

    def test_find_by_case_and_index(self):
        self.assertIs(self.viewer.find(case_id="case_1"), self.viewer.find(index=0))
        with self.assertRaises(KeyError):
            self.viewer.find(case_id="unknown")

    def test_describe_lists_nodes_in_order_with_successors(self):
        text = self.viewer.describe(parallel_graph())
        self.assertIn("with parallel branches", text)
        self.assertIn("start", text.splitlines()[3])
        self.assertIn("-> 2, 3", text.splitlines()[3])

    def test_parallel_nodes_share_a_layer(self):
        positions, n_layers = self.viewer.layout(parallel_graph())
        self.assertEqual(n_layers, 3)
        self.assertEqual(positions[1][0], positions[2][0])     # same column
        self.assertNotEqual(positions[1][1], positions[2][1])  # different height

    def test_long_chain_snakes_back(self):
        chain = nx.DiGraph(nx.path_graph(5, create_using=nx.DiGraph))
        for node in chain:
            chain.nodes[node].update(label=f"X{node}", local_id=node + 1)
        positions, _ = self.viewer.layout(chain, columns=3)
        self.assertEqual(positions[2][0], positions[3][0])     # row change goes straight down
        self.assertGreater(positions[3][0], positions[4][0])   # second row runs right to left

    def test_plot_writes_an_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.png"
            self.viewer.plot(parallel_graph(), path)
            self.assertGreater(path.stat().st_size, 0)

    def test_label_helpers(self):
        self.assertEqual(wrap_label("W-Complete-application-start"),
                         "W-Complete-\napplication-start")
        for line in wrap_label("W-Complete-application-suspend").splitlines():
            self.assertLessEqual(len(line), 18)
        self.assertEqual(short_tag("Role_12"), "R12")


if __name__ == "__main__":
    unittest.main()

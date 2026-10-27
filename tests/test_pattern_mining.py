"""Unit tests for step 3: SUBDUE input, the speed-ups, support and the trace x pattern matrix.

Run from the project root:  python -m unittest discover tests -v
"""
import contextlib
import io
import random
import unittest

import networkx as nx

from orgmining.pattern_mining import (PatternMiner, SubdueAccelerator, SubdueSettings,
                                          build_subdue_graph, describe_pattern, subdue,
                                          subdue_pattern)


def chain(case_id, labels, first_node):
    """Instance graph that is a simple sequence of the given labels."""
    graph = nx.DiGraph(case_id=case_id)
    for offset, label in enumerate(labels):
        activity, role = label.split("_", 1)
        graph.add_node(first_node + offset, label=label, activity=activity, value=role)
    graph.add_edges_from((first_node + i, first_node + i + 1) for i in range(len(labels) - 1))
    return graph


def example_graphs():
    """Four traces; 'A_R1 -> B_R1 -> C_R2' occurs in three of them."""
    return [chain("c1", ["A_R1", "B_R1", "C_R2", "D_R2"], 0),
            chain("c2", ["A_R1", "B_R1", "C_R2"], 10),
            chain("c3", ["X_R3", "A_R1", "B_R1", "C_R2"], 20),
            chain("c4", ["X_R3", "D_R2"], 30)]


def random_graphs(seed, n_graphs=25):
    """Random DAGs over a few labels, with some parallel branches."""
    rng = random.Random(seed)
    labels = [f"{a}_R{r}" for a in "ABCD" for r in (1, 2)]
    graphs, next_node = [], 0
    for index in range(n_graphs):
        graph = nx.DiGraph(case_id=f"c{index}")
        nodes = list(range(next_node, next_node + rng.randint(3, 8)))
        next_node += len(nodes)
        for node in nodes:
            graph.add_node(node, label=rng.choice(labels))
        for i, node in enumerate(nodes[1:], start=1):
            for predecessor in rng.sample(nodes[:i], k=min(i, rng.choice([1, 1, 2]))):
                graph.add_edge(predecessor, node)
        graphs.append(graph)
    return graphs


def run(graphs, accelerated, **settings):
    """Run SUBDUE quietly; return a comparable summary of every pattern and instance."""
    subdue_input, _ = build_subdue_graph(graphs)
    parameters = SubdueSettings(**settings).to_parameters(n_initial_patterns=50)
    parameters.set_defaults_for_graph(subdue_input)
    accelerator = SubdueAccelerator() if accelerated else contextlib.nullcontext()
    with contextlib.redirect_stdout(io.StringIO()), accelerator:
        iterations = subdue.Subdue(parameters, subdue_input)
    return [[(round(p.value, 12),
              sorted(v.attributes["label"] for v in p.definition.vertices.values()),
              [sorted(v.id for v in i.vertices.list_container) for i in p.instances])
             for p in iteration] for iteration in iterations]


class SubdueInputTest(unittest.TestCase):
    def test_all_graphs_become_one_directed_graph(self):
        subdue_input, vertex_to_graph = build_subdue_graph(example_graphs())
        self.assertEqual(len(subdue_input.vertices), 13)
        self.assertEqual(len(subdue_input.edges), 9)
        self.assertTrue(all(edge.directed for edge in subdue_input.edges.values()))
        self.assertEqual(vertex_to_graph["20"], 2)


class AcceleratorTest(unittest.TestCase):
    def test_same_result_as_original_subdue(self):
        for seed in range(3):
            graphs = random_graphs(seed)
            # Overlapping instances only with 1 iteration: SUBDUE's compression
            # assumes non-overlapping instances and fails otherwise.
            for settings in ({"beam_width": 4, "num_best": 5, "iterations": 1},
                             {"beam_width": 2, "num_best": 3, "iterations": 3},
                             {"beam_width": 4, "num_best": 5, "overlap": "vertex", "iterations": 1}):
                with self.subTest(seed=seed, **settings):
                    self.assertEqual(run(graphs, False, **settings),
                                     run(graphs, True, **settings))

    def test_original_functions_are_restored(self):
        original = (subdue.GetInitialPatterns, subdue_pattern.ExtendPattern)
        with SubdueAccelerator():
            self.assertIsNot(subdue.GetInitialPatterns, original[0])
        self.assertEqual((subdue.GetInitialPatterns, subdue_pattern.ExtendPattern), original)


class StatisticsTest(unittest.TestCase):
    def setUp(self):
        self.graphs = example_graphs()
        subdue_input, vertex_to_graph = build_subdue_graph(self.graphs)
        miner = PatternMiner("unused/instance_graphs.pkl",
                             settings=SubdueSettings(num_best=5, min_size=2))
        miner.label_parts = {label: tuple(label.split("_", 1))
                             for label in ("A_R1", "B_R1", "C_R2", "D_R2", "X_R3")}
        with contextlib.redirect_stdout(io.StringIO()):
            parameters = miner.settings.to_parameters(n_initial_patterns=10)
            parameters.set_defaults_for_graph(subdue_input)
            with SubdueAccelerator():
                iterations = subdue.Subdue(parameters, subdue_input)
        self.patterns = miner.collect(iterations, vertex_to_graph)

    def best(self):
        return self.patterns[0]

    def test_best_pattern_and_its_traces(self):
        self.assertEqual(describe_pattern(self.best().definition),
                         "A_R1 -> B_R1; B_R1 -> C_R2")
        self.assertEqual(self.best().graph_positions, [0, 1, 2])
        self.assertEqual(self.best().roles, ["R1", "R2"])

    def test_support_and_matrix(self):
        table = PatternMiner.pattern_table(self.patterns, self.graphs)
        self.assertEqual(table.loc[0, "traces"], 3)
        self.assertEqual(table.loc[0, "trace_support_pct"], 75.0)
        matrix = PatternMiner.trace_pattern_matrix(self.patterns, self.graphs)
        self.assertEqual(list(matrix.index), ["c1", "c2", "c3", "c4"])
        self.assertEqual(list(matrix["P1"]), [1, 1, 1, 0])


if __name__ == "__main__":
    unittest.main()

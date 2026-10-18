"""Unit tests for step 2: converting BIG's .g output to networkx.

Run from the project root:  python -m unittest discover tests -v
"""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import Event, EventLog, Trace

from orgmining.instance_graphs import BigRunner, GFileConverter, PetriNetDiscoverer

# Two graphs in BIG's format. Graph 1 has a parallel split (A -> B, A -> C)
# and a duplicated edge line, as BIG sometimes writes.
EXAMPLE_G = """XP
v 1 A_Role_1
v 2 B_Role_2
v 3 C_Role_2
e 1 2 A_Role_1__B_Role_2
e 1 3 A_Role_1__C_Role_2
e 1 3 A_Role_1__C_Role_2

XP
v 1 A_Role_1
v 2 B_Role_1
e 1 2 A_Role_1__B_Role_1

"""


class GFileConverterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.g_path = Path(self.tmp.name) / "example.g"
        self.g_path.write_text(EXAMPLE_G, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_graph_per_block_with_case_ids(self):
        graphs = GFileConverter().convert(self.g_path, case_ids=["case_a", "case_b"])
        self.assertEqual(len(graphs), 2)
        self.assertEqual([g.graph["case_id"] for g in graphs], ["case_a", "case_b"])
        self.assertEqual([g.number_of_nodes() for g in graphs], [3, 2])
        self.assertEqual([g.number_of_edges() for g in graphs], [2, 1])   # duplicate kept once

    def test_node_ids_are_unique_and_edges_preserved(self):
        first, second = GFileConverter().convert(self.g_path)
        all_ids = list(first.nodes) + list(second.nodes)
        self.assertEqual(len(all_ids), len(set(all_ids)))
        # Both graphs have a local node 1, but they get different global ids.
        self.assertEqual(sorted(all_ids), [0, 1, 2, 3, 4])
        labels = {(first.nodes[u]["label"], first.nodes[v]["label"]) for u, v in first.edges}
        self.assertEqual(labels, {("A_Role_1", "B_Role_2"), ("A_Role_1", "C_Role_2")})
        self.assertEqual(second.nodes[3]["local_id"], 1)

    def test_label_parts_from_step1_are_attached(self):
        converter = GFileConverter({"A_Role_1": ("A", "Role_1")})
        node = GFileConverter.convert(converter, self.g_path)[0].nodes[0]
        self.assertEqual((node["activity"], node["value"]), ("A", "Role_1"))

    def test_summary_detects_parallelism(self):
        table = GFileConverter.summarise(GFileConverter().convert(self.g_path))
        self.assertEqual(list(table["has_branching"]), [True, False])
        self.assertTrue(table["connected"].all())

    def test_case_id_count_must_match(self):
        with self.assertRaises(ValueError):
            GFileConverter().convert(self.g_path, case_ids=["only_one"])

    def test_unknown_node_in_edge_is_an_error(self):
        self.g_path.write_text("XP\nv 1 A\ne 1 9 A__X\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            GFileConverter().convert(self.g_path)

    def test_save_and_load_round_trip(self):
        graphs = GFileConverter().convert(self.g_path)
        path = GFileConverter.save(graphs, Path(self.tmp.name) / "graphs.pkl")
        loaded = GFileConverter.load(path)
        self.assertEqual([sorted(g.edges) for g in loaded], [sorted(g.edges) for g in graphs])


class SplitLogTest(unittest.TestCase):
    def test_chunks_keep_every_trace_in_order(self):
        traces = [Trace([Event({"concept:name": "A"})], attributes={"concept:name": f"c{i}"})
                  for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            paths = BigRunner(tmp, workers=2).split_log(EventLog(traces), Path(tmp) / "chunks")
            case_ids = [trace.attributes["concept:name"]
                        for path in paths for trace in xes_importer.apply(str(path))]
        self.assertGreater(len(paths), 1)
        self.assertEqual(case_ids, [f"c{i}" for i in range(10)])



class DiscoveryAndValidationTest(unittest.TestCase):
    def test_default_preserves_existing_discovery_api(self):
        with patch("orgmining.instance_graphs.pm4py.discover_petri_net_inductive") as discover:
            PetriNetDiscoverer(0.2).discover("log")
            discover.assert_called_once_with("log", noise_threshold=0.2)

    def test_imf_uses_its_own_noise_parameter(self):
        from pm4py.algo.discovery.inductive import algorithm as inductive
        variant = inductive.Variants.IMf
        with patch.object(inductive, "apply") as discover:
            PetriNetDiscoverer(0.3, "imf").discover("log")
            discover.assert_called_once_with("log", variant=variant, parameters={
                variant.value.Parameters.NOISE_THRESHOLD: 0.3})

    def test_integrity_validation_rejects_wrong_labels_and_backwards_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.g"
            path.write_text(EXAMPLE_G)
            graphs = GFileConverter().convert(path, ["case_a", "case_b"])
        log = EventLog([Trace([Event({"concept:name": d["label"]})
                               for _, d in g.nodes(data=True)],
                              attributes={"concept:name": g.graph["case_id"]}) for g in graphs])
        GFileConverter.validate_against_log(graphs, log)
        graphs[0].nodes[0]["label"] = "wrong"
        with self.assertRaisesRegex(ValueError, "labels differ"):
            GFileConverter.validate_against_log(graphs, log)
        graphs[0].nodes[0]["label"] = "A_Role_1"
        graphs[0].remove_edge(0, 1)
        graphs[0].add_edge(1, 0, label="B_Role_2__A_Role_1")
        with self.assertRaisesRegex(ValueError, "event order"):
            GFileConverter.validate_against_log(graphs, log)

if __name__ == "__main__":
    unittest.main()

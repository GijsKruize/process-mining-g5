"""Step 2: instance graph generation.

Discovers a Petri net from the relabelled log (Inductive Miner), runs BIG's
alignment-and-repair algorithm (big_engine.py) on every trace to build one
instance graph per trace, and parses BIG's textual .g output into a list of
networkx.DiGraph objects for step 3.
"""
import argparse
import pickle
from pathlib import Path

import networkx as nx
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.petri_net.exporter import exporter as pnml_exporter

import big_engine

# above this many distinct activity labels, Inductive Miner discovery gets
# very slow -- pick a coarser attribute in step 1 if you hit this
MANY_LABELS_WARNING = 200


class InstanceGraphBuilder:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def discover_petri_net(self, log):
        net, im, fm = inductive_miner.apply(log)
        pnml_exporter.apply(net, im, str(self.output_dir / "petri_net.pnml"), final_marking=fm)
        return net, im, fm

    def run_big(self, log, net, im, fm):
        """Runs BIG on every trace and writes its textual .g output."""
        causal_relations = big_engine.find_causal_relationships(net)
        g_path = self.output_dir / "instance_graphs.g"
        with open(g_path, "w", encoding="utf-8") as f:
            for trace in log:
                nodes, edges = big_engine.build_instance_graph(trace, net, im, fm, causal_relations)
                f.write("XP\n")
                for node_id, label in nodes:
                    f.write(f"v {node_id} {label}\n")
                for (src_id, src_label), (dst_id, dst_label) in edges:
                    f.write(f"e {src_id} {dst_id} {src_label}__{dst_label}\n")
                f.write("\n")
        return g_path

    @staticmethod
    def parse_g_file(path):
        """Parses a BIG .g file into a list of DiGraphs (one per 'XP' block).

        BIG's own node ids restart at 1 for every graph, so they are
        remapped to ids that are unique across the whole collection.
        """
        graphs = []
        graph = None
        local_to_global = {}
        next_id = 0
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                tag, _, rest = line.partition(" ")
                if tag == "XP":
                    graph = nx.DiGraph()
                    graphs.append(graph)
                    local_to_global = {}
                elif tag == "v":
                    local_id, _, label = rest.partition(" ")
                    local_to_global[local_id] = next_id
                    graph.add_node(next_id, label=label)
                    next_id += 1
                elif tag == "e":
                    src, dst, label = rest.split(" ", 2)
                    graph.add_edge(local_to_global[src], local_to_global[dst], label=label)
        return graphs

    def run(self, log_path):
        log = xes_importer.apply(str(log_path))

        n_labels = len({event["concept:name"] for trace in log for event in trace})
        if n_labels > MANY_LABELS_WARNING:
            print(f"Warning: {n_labels} distinct activity labels -- Inductive Miner may be slow. "
                  "Consider a coarser attribute in step 1.")

        net, im, fm = self.discover_petri_net(log)
        print(f"Petri net discovered ({len(net.transitions)} transitions), "
              f"saved to '{self.output_dir}/petri_net.pnml'")

        g_path = self.run_big(log, net, im, fm)
        print(f"BIG instance graphs written to '{g_path}'")

        graphs = self.parse_g_file(g_path)
        n_nodes = sum(graph.number_of_nodes() for graph in graphs)
        n_edges = sum(graph.number_of_edges() for graph in graphs)
        print(f"Parsed {len(graphs)} instance graphs ({n_nodes} nodes, {n_edges} edges total)")

        pkl_path = self.output_dir / "instance_graphs.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(graphs, f)
        print(f"Saved parsed instance graphs to '{pkl_path}'")
        return graphs


def main():
    parser = argparse.ArgumentParser(description="Step 2: generate instance graphs with BIG.")
    parser.add_argument("--log-path", default="output/relabeled_log.xes",
                         help="Relabelled log produced by step 1")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    InstanceGraphBuilder(args.output_dir).run(args.log_path)


if __name__ == "__main__":
    main()

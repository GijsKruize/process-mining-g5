"""Step 2: instance graph generation.

Discovers a Petri net from the relabelled log (Inductive Miner), runs BIG's
alignment-and-repair algorithm (big_engine.py) on every trace to build one
instance graph per trace, and parses BIG's textual .g output into a list of
networkx.DiGraph objects for step 3.
"""
import argparse
import copy
import json
from collections import Counter
import pickle
from pathlib import Path

import networkx as nx
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.objects.log.obj import EventLog, Trace
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

    @staticmethod
    def clone_log_metadata(log):
        return {
            "attributes": copy.copy(log.attributes),
            "extensions": copy.copy(log.extensions),
            "omni_present": copy.copy(log.omni_present),
            "classifiers": copy.copy(log.classifiers),
            "properties": copy.copy(log.properties),
        }

    @staticmethod
    def trace_for_model(trace, model_activity_attribute="original_activity"):
        """Copy a trace and replace concept:name by the activity used for the process model."""
        model_trace = Trace(attributes=copy.copy(trace.attributes))
        for event in trace:
            model_event = copy.copy(event)
            model_event["concept:name"] = event.get(
                model_activity_attribute,
                event.get("concept:name", "UNKNOWN"),
            )
            model_trace.append(model_event)
        return model_trace

    @classmethod
    def log_for_model(cls, log, model_activity_attribute="original_activity"):
        """Return a copy of log where concept:name is model-level activity, not resource label."""
        model_log = EventLog(**cls.clone_log_metadata(log))
        for trace in log:
            model_log.append(cls.trace_for_model(trace, model_activity_attribute))
        return model_log

    @staticmethod
    def trace_variant(trace, variant_attribute="original_activity"):
        """Return the activity sequence used to identify a trace variant."""
        return tuple(
            event.get(variant_attribute, event.get("concept:name", "UNKNOWN"))
            for event in trace
        )

    @classmethod
    def filter_by_variant_coverage(cls, log, coverage=0.80, variant_attribute="original_activity"):
        """Keep the most frequent trace variants until coverage of cases is reached.

        This is the behavior-preserving log filter suggested before Inductive
        Miner: sort variants by frequency, keep whole variants until they cover
        the requested fraction of traces, and discard the remaining rare
        variants. For example, coverage=0.80 keeps the most frequent variants
        explaining at least 80% of the cases.
        """
        if coverage is None or coverage >= 1.0:
            return log, {
                "enabled": False,
                "coverage": 1.0,
                "kept_traces": len(log),
                "total_traces": len(log),
                "kept_variants": len({cls.trace_variant(trace, variant_attribute) for trace in log}),
                "total_variants": len({cls.trace_variant(trace, variant_attribute) for trace in log}),
                "variant_attribute": variant_attribute,
            }
        if coverage <= 0:
            raise ValueError("--variant-coverage must be greater than 0")

        variant_counts = Counter(cls.trace_variant(trace, variant_attribute) for trace in log)
        total_traces = len(log)
        target_traces = total_traces * coverage
        kept_variants = set()
        kept_trace_count = 0

        for variant, count in variant_counts.most_common():
            kept_variants.add(variant)
            kept_trace_count += count
            if kept_trace_count >= target_traces:
                break

        filtered_log = EventLog(**cls.clone_log_metadata(log))
        for trace in log:
            if cls.trace_variant(trace, variant_attribute) in kept_variants:
                filtered_log.append(trace)

        actual_coverage = len(filtered_log) / total_traces if total_traces else 0.0
        return filtered_log, {
            "enabled": True,
            "coverage": actual_coverage,
            "requested_coverage": coverage,
            "kept_traces": len(filtered_log),
            "total_traces": total_traces,
            "kept_variants": len(kept_variants),
            "total_variants": len(variant_counts),
            "variant_attribute": variant_attribute,
        }

    @staticmethod
    def output_label_by_event_id(trace):
        """Map BIG's 1-based event ids to the resource-enriched labels we want to mine."""
        return {
            event_id: event.get("concept:name", "UNKNOWN")
            for event_id, event in enumerate(trace, start=1)
        }

    @staticmethod
    def apply_output_labels(nodes, edges, output_labels):
        relabelled_nodes = [
            (node_id, output_labels.get(node_id, label))
            for node_id, label in nodes
        ]
        relabelled_edges = [
            (
                (src_id, output_labels.get(src_id, src_label)),
                (dst_id, output_labels.get(dst_id, dst_label)),
            )
            for (src_id, src_label), (dst_id, dst_label) in edges
        ]
        return relabelled_nodes, relabelled_edges

    def run_big(self, log, net, im, fm, model_activity_attribute="original_activity"):
        """Runs BIG on every trace and writes its textual .g output."""
        causal_relations = big_engine.find_causal_relationships(net)
        g_path = self.output_dir / "instance_graphs.g"
        with open(g_path, "w", encoding="utf-8") as f:
            for index, trace in enumerate(log, start=1):
                model_trace = self.trace_for_model(trace, model_activity_attribute)
                nodes, edges = big_engine.build_instance_graph(
                    model_trace,
                    net,
                    im,
                    fm,
                    causal_relations,
                )
                nodes, edges = self.apply_output_labels(
                    nodes,
                    edges,
                    self.output_label_by_event_id(trace),
                )
                f.write("XP\n")
                for node_id, label in nodes:
                    f.write(f"v {node_id} {label}\n")
                for (src_id, src_label), (dst_id, dst_label) in edges:
                    f.write(f"e {src_id} {dst_id} {src_label}__{dst_label}\n")
                f.write("\n")
                if index % 10 == 0 or index == len(log):
                    f.flush()
                    print(f"  BIG processed {index}/{len(log)} traces", flush=True)
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

    def run(self, log_path, variant_coverage=0.80, variant_attribute="original_activity",
            model_activity_attribute="original_activity"):
        log = xes_importer.apply(str(log_path))

        output_labels = len({event["concept:name"] for trace in log for event in trace})
        model_labels = len({
            event.get(model_activity_attribute, event["concept:name"])
            for trace in log
            for event in trace
        })
        if output_labels > MANY_LABELS_WARNING:
            print(f"Resource-enriched output labels: {output_labels}.")
        print(f"Process model labels using '{model_activity_attribute}': {model_labels}.")

        mining_log, filter_stats = self.filter_by_variant_coverage(
            log,
            variant_coverage,
            variant_attribute=variant_attribute,
        )
        if filter_stats["enabled"]:
            print("Variant filter before Inductive Miner: "
                  f"kept {filter_stats['kept_traces']}/{filter_stats['total_traces']} traces "
                  f"({filter_stats['coverage']:.1%}) and "
                  f"{filter_stats['kept_variants']}/{filter_stats['total_variants']} variants "
                  f"using '{filter_stats['variant_attribute']}' "
                  f"for requested coverage {filter_stats['requested_coverage']:.0%}.")
        else:
            print("Variant filter before Inductive Miner: disabled.")
        filter_stats["model_activity_attribute"] = model_activity_attribute
        filter_stats["model_label_count"] = model_labels
        filter_stats["resource_output_label_count"] = output_labels
        with open(self.output_dir / "variant_filter_stats.json", "w", encoding="utf-8") as f:
            json.dump(filter_stats, f, indent=2)

        model_log = self.log_for_model(mining_log, model_activity_attribute)
        net, im, fm = self.discover_petri_net(model_log)
        print(f"Petri net discovered ({len(net.transitions)} transitions), "
              f"saved to '{self.output_dir}/petri_net.pnml'")

        g_path = self.run_big(
            mining_log,
            net,
            im,
            fm,
            model_activity_attribute=model_activity_attribute,
        )
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
    parser.add_argument("--variant-coverage", type=float, default=0.80,
                        help="Keep most frequent trace variants covering this fraction before IM; use 1.0 to disable")
    parser.add_argument("--variant-attribute", default="original_activity",
                        help="Event attribute used to define trace variants for filtering")
    parser.add_argument("--model-activity-attribute", default="original_activity",
                        help="Event attribute used for Petri net discovery and BIG alignment")
    args = parser.parse_args()
    InstanceGraphBuilder(args.output_dir).run(
        args.log_path,
        variant_coverage=args.variant_coverage,
        variant_attribute=args.variant_attribute,
        model_activity_attribute=args.model_activity_attribute,
    )


if __name__ == "__main__":
    main()

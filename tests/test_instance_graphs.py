"""Tests for step 2: Petri net discovery and .g -> networkx instance graph parsing."""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

import instance_graphs as ig
from generate_synthetic_log import build_synthetic_log
from preprocess import EventLogRepository

SAMPLE_G_FILE = Path(__file__).parent / "data" / "sample_instance_graphs.g"

# A minimal two-graph .g fixture that deliberately reuses local vertex ids
# (1, 2, 3) across graphs, mirroring how BIG resets ids per instance.
TINY_G_TEXT = """\
XP
v 1 start
v 2 A
v 3 end
e 1 2 start__A
e 2 3 A__end

XP
v 1 start
v 2 B
v 3 end
e 1 2 start__B
e 2 3 B__end
"""


# ---------------------------------------------------------------------------
# InstanceGraphParser
# ---------------------------------------------------------------------------


def test_parse_lines_produces_one_graph_per_header() -> None:
    graphs = ig.InstanceGraphParser().parse_lines(TINY_G_TEXT.splitlines())
    assert len(graphs) == 2
    assert all(isinstance(graph, nx.DiGraph) for graph in graphs)
    assert all(graph.number_of_nodes() == 3 for graph in graphs)
    assert all(graph.number_of_edges() == 2 for graph in graphs)


def test_parse_lines_assigns_globally_unique_node_ids() -> None:
    graphs = ig.InstanceGraphParser().parse_lines(TINY_G_TEXT.splitlines())
    all_node_ids = [node for graph in graphs for node in graph.nodes]
    assert len(all_node_ids) == len(set(all_node_ids)), "node ids must be unique across graphs"
    # Local (per-graph) ids do repeat across graphs, as in the raw .g file.
    local_ids_first = sorted(data["local_id"] for _, data in graphs[0].nodes(data=True))
    local_ids_second = sorted(data["local_id"] for _, data in graphs[1].nodes(data=True))
    assert local_ids_first == local_ids_second == [1, 2, 3]


def test_parse_lines_preserves_edge_relations_and_labels() -> None:
    graphs = ig.InstanceGraphParser().parse_lines(TINY_G_TEXT.splitlines())
    first, second = graphs

    def label_of(node_id: int, graph: nx.DiGraph) -> str:
        return graph.nodes[node_id]["label"]

    for graph, middle_label in ((first, "A"), (second, "B")):
        start_id = next(n for n, d in graph.nodes(data=True) if d["label"] == "start")
        middle_id = next(n for n, d in graph.nodes(data=True) if d["label"] == middle_label)
        end_id = next(n for n, d in graph.nodes(data=True) if d["label"] == "end")
        assert graph.has_edge(start_id, middle_id)
        assert graph.has_edge(middle_id, end_id)
        assert graph[start_id][middle_id]["label"] == f"start__{middle_label}"
        assert graph[middle_id][end_id]["label"] == f"{middle_label}__end"


def test_parse_rejects_vertex_line_without_graph_header() -> None:
    with pytest.raises(ValueError, match="before any graph header"):
        ig.InstanceGraphParser().parse_lines(["v 1 start"])


def test_parse_rejects_unrecognized_line() -> None:
    with pytest.raises(ValueError, match="Unrecognized line"):
        ig.InstanceGraphParser().parse_lines(["XP", "z 1 2 nonsense"])


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    graphs = ig.InstanceGraphParser().parse_lines(TINY_G_TEXT.splitlines())
    pickle_path = tmp_path / "graphs.pkl"
    ig.InstanceGraphParser.save(graphs, pickle_path)
    reloaded = ig.InstanceGraphParser.load(pickle_path)
    assert len(reloaded) == len(graphs)
    assert [g.number_of_nodes() for g in reloaded] == [g.number_of_nodes() for g in graphs]
    assert [g.number_of_edges() for g in reloaded] == [g.number_of_edges() for g in graphs]


def test_summarize() -> None:
    graphs = ig.InstanceGraphParser().parse_lines(TINY_G_TEXT.splitlines())
    stats = ig.InstanceGraphParser.summarize(graphs)
    assert stats == {
        "n_graphs": 2,
        "n_nodes": 6,
        "n_edges": 4,
        "avg_nodes_per_graph": 3.0,
        "avg_edges_per_graph": 2.0,
    }


def test_parse_real_big_output_sample() -> None:
    """Regression test against a real excerpt of BIG's own output format."""
    graphs = ig.InstanceGraphParser().parse(SAMPLE_G_FILE)
    assert len(graphs) == 2
    assert graphs[0].number_of_nodes() == 33
    assert graphs[1].number_of_nodes() == 34
    all_node_ids = [node for graph in graphs for node in graph.nodes]
    assert len(all_node_ids) == len(set(all_node_ids))
    start_id = next(n for n, d in graphs[0].nodes(data=True) if d["label"] == "start")
    end_id = next(n for n, d in graphs[0].nodes(data=True) if d["label"] == "end")
    assert nx.has_path(graphs[0], start_id, end_id)


# ---------------------------------------------------------------------------
# PetriNetDiscoverer
# ---------------------------------------------------------------------------


def test_discover_and_export_petri_net(tmp_path: Path) -> None:
    log = build_synthetic_log()
    net, initial_marking, final_marking = ig.PetriNetDiscoverer.discover(log)
    assert net.transitions
    assert net.places

    pnml_path = tmp_path / "petri_net.pnml"
    ig.PetriNetDiscoverer.export(net, initial_marking, final_marking, pnml_path)
    assert pnml_path.exists()
    assert pnml_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# BigRunner
# ---------------------------------------------------------------------------


def test_big_runner_raises_clear_error_when_unconfigured(tmp_path: Path) -> None:
    runner = ig.BigRunner(command_template=None)
    with pytest.raises(RuntimeError, match="not configured"):
        runner.run(tmp_path / "log.xes", tmp_path / "net.pnml", tmp_path / "out.g")


def test_big_runner_invokes_configured_command(tmp_path: Path) -> None:
    log_path = tmp_path / "log.xes"
    net_path = tmp_path / "net.pnml"
    out_path = tmp_path / "out.g"
    # A trivial shell command standing in for the real BIG invocation.
    runner = ig.BigRunner(command_template="echo XP > {output}")
    runner.run(log_path, net_path, out_path)
    assert out_path.read_text().strip() == "XP"


def test_big_runner_raises_on_nonzero_exit(tmp_path: Path) -> None:
    runner = ig.BigRunner(command_template="exit 1")
    with pytest.raises(RuntimeError, match="BIG failed"):
        runner.run(tmp_path / "log.xes", tmp_path / "net.pnml", tmp_path / "out.g")


# ---------------------------------------------------------------------------
# InstanceGraphConfig
# ---------------------------------------------------------------------------


def test_instance_graph_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "custom.yaml"
    config_path.write_text(
        "log_path: some_log.xes\n"
        "output_dir: some_output\n"
        "activity_key: concept:name\n"
        "big_command: 'echo {log} {petri_net} {output}'\n"
    )
    config = ig.InstanceGraphConfig.from_yaml(config_path)
    assert config.log_path == Path("some_log.xes")
    assert config.output_dir == Path("some_output")
    assert config.activity_key == "concept:name"
    assert config.big_command == "echo {log} {petri_net} {output}"
    assert config.discovery_log_path == Path("some_output/discovery_log.xes")
    assert config.petri_net_path == Path("some_output/petri_net.pnml")
    assert config.graphs_path == Path("some_output/instance_graphs.g")


def test_instance_graph_config_default_activity_key() -> None:
    assert ig.InstanceGraphConfig().activity_key == "original_activity"


def test_build_discovery_log_rejects_unknown_activity_key(tmp_path: Path) -> None:
    log_path = tmp_path / "synthetic_log.xes"
    from generate_synthetic_log import write_synthetic_log

    write_synthetic_log(log_path)

    config = ig.InstanceGraphConfig(
        log_path=log_path,
        output_dir=tmp_path / "output",
        activity_key="does_not_exist",
    )
    log = EventLogRepository().load(log_path)
    with pytest.raises(ValueError, match="not found"):
        ig.InstanceGraphPipeline(config)._build_discovery_log(log)


# ---------------------------------------------------------------------------
# End-to-end pipeline (Petri net discovery + a stand-in BIG command)
# ---------------------------------------------------------------------------


def test_pipeline_end_to_end_with_stub_big(tmp_path: Path) -> None:
    log_path = tmp_path / "synthetic_log.xes"
    from generate_synthetic_log import write_synthetic_log

    write_synthetic_log(log_path)

    output_dir = tmp_path / "output"
    config = ig.InstanceGraphConfig(
        log_path=log_path,
        output_dir=output_dir,
        # The synthetic log has no 'original_activity' (that's added by
        # step 1's relabelling), so discover directly from 'concept:name'.
        activity_key="concept:name",
        # Stand-in for BIG: just copies the real sample .g file so the
        # rest of the pipeline (parsing, summarizing, saving) is exercised.
        big_command=f"cp {SAMPLE_G_FILE} {{output}}",
    )
    graphs = ig.InstanceGraphPipeline(config).run()

    assert len(graphs) == 2
    assert config.discovery_log_path.exists()
    assert config.petri_net_path.exists()
    assert config.graphs_path.exists()
    assert config.parsed_graphs_path.exists()

    reloaded = ig.InstanceGraphParser.load(config.parsed_graphs_path)
    assert len(reloaded) == 2


def test_pipeline_reuses_existing_graphs_file_without_force(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "instance_graphs.g").write_text("XP\nv 1 start\nv 2 end\ne 1 2 start__end\n")

    config = ig.InstanceGraphConfig(
        log_path=tmp_path / "does_not_exist.xes",  # would fail to load
        output_dir=output_dir,
        big_command=None,  # would fail if actually invoked
    )
    graphs = ig.InstanceGraphPipeline(config).run()
    assert len(graphs) == 1


def test_missing_log_repository_error_surfaces(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        EventLogRepository().load(tmp_path / "no_such_log.xes")

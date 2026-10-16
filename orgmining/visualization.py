"""Reading and plotting instance graphs (and later the patterns of step 3).

No Graphviz is needed: the layout is computed here and drawn with matplotlib.

Layout: every node is placed in the *layer* of its longest path from a start
node, so parallel branches end up above each other. Long graphs wrap after
``columns`` layers in a "snake": the first row reads left to right, the second
right to left, and so on, so the step to the next row is a short arrow down.
Nodes show the activity; the role (or other attribute value) is shown both by
the colour of the node border and by a short tag such as ``R2``, so that the
plot can also be read without colour.
"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # write image files; no window needed
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from .instance_graphs import GFileConverter  # noqa: E402

# Categorical colours, assigned to roles in a fixed order (Role_1 always gets
# the first colour). Colour-blind safe palette from the dataviz guidelines.
CATEGORICAL_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                       "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER_COLOUR = "#8a8a85"
TEXT_COLOUR = "#1f1f1e"
EDGE_COLOUR = "#9a9a94"
DEFAULT_COLUMNS = 8
COLUMN_WIDTH = 2.6   # horizontal distance between two layers (data units)


def natural_sort_key(text):
    """'Role_10' after 'Role_2': compare the numbers in a string as numbers."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(text))]


def wrap_label(text, width=18):
    """Break a label after '-' into lines of about ``width`` characters.

    'W-Complete-application-suspend' -> 'W-Complete-\\napplication-suspend', so
    the end of the name (often the lifecycle step) stays visible.
    """
    lines, current = [], ""
    for part in re.split(r"(?<=-)", str(text)):
        if current and len(current) + len(part) > width:
            lines.append(current)
            current = part
        else:
            current += part
    lines.append(current)
    return "\n".join(lines)


def short_tag(value):
    """'Role_3' -> 'R3'; other values are cut to 6 characters."""
    match = re.fullmatch(r"Role_(\d+)", str(value))
    return f"R{match.group(1)}" if match else str(value)[:6]


class InstanceGraphViewer:
    """Look up, print and plot instance graphs produced by step 2.

    Usage::

        viewer = InstanceGraphViewer.from_pickle("outputs/.../instance_graphs.pkl")
        graph = viewer.find(case_id="Application_1691306052")   # or index=0
        print(viewer.describe(graph))
        viewer.plot(graph, "graph.png")
    """

    def __init__(self, graphs):
        self.graphs = graphs
        self._by_case = {g.graph.get("case_id"): g for g in graphs}
        values = {data.get("value") for g in graphs for _, data in g.nodes(data=True)}
        ordered = sorted((v for v in values if v is not None), key=natural_sort_key)
        self.colours = {value: CATEGORICAL_COLOURS[i] if i < len(CATEGORICAL_COLOURS)
                        else OTHER_COLOUR for i, value in enumerate(ordered)}

    @classmethod
    def from_pickle(cls, path):
        return cls(GFileConverter.load(path))

    def find(self, case_id=None, index=None):
        """Return the graph of a case id, or the graph at a position (0-based)."""
        if case_id is not None:
            if case_id not in self._by_case:
                raise KeyError(f"No instance graph for case '{case_id}'.")
            return self._by_case[case_id]
        if index is None or not 0 <= index < len(self.graphs):
            raise IndexError(f"Index must be between 0 and {len(self.graphs) - 1}.")
        return self.graphs[index]

    # -- reading ------------------------------------------------------------

    @staticmethod
    def node_order(graph):
        """Nodes in a topological order (BIG's local ids break ties)."""
        return list(nx.lexicographical_topological_sort(
            graph, key=lambda node: graph.nodes[node].get("local_id", node)))

    def describe(self, graph):
        """The graph as readable text: one line per node with its successors."""
        order = self.node_order(graph)
        local = {node: graph.nodes[node].get("local_id", node) for node in graph}
        parallel = any(degree > 1 for _, degree in graph.out_degree())
        lines = [f"Instance graph {graph.graph.get('graph_index')} - case "
                 f"{graph.graph.get('case_id')}: {graph.number_of_nodes()} nodes, "
                 f"{graph.number_of_edges()} edges, "
                 f"{'with' if parallel else 'no'} parallel branches", ""]
        lines.append(f"{'id':>4}  {'activity':<38} {'role':<8} next")
        for node in order:
            data = graph.nodes[node]
            successors = ", ".join(str(local[s]) for s in sorted(graph.successors(node),
                                                                 key=local.get))
            lines.append(f"{local[node]:>4}  {data.get('activity', data['label']):<38} "
                         f"{str(data.get('value', '')):<8} -> {successors or '(end)'}")
        return "\n".join(lines)

    # -- plotting -----------------------------------------------------------

    def layout(self, graph, columns=DEFAULT_COLUMNS):
        """Positions {node: (x, y)}: layer = longest path from a start node, snake-wrapped."""
        layer = {}
        for node in self.node_order(graph):
            layer[node] = max((layer[p] + 1 for p in graph.predecessors(node)), default=0)
        n_layers = max(layer.values(), default=0) + 1
        per_layer = {}
        for node in self.node_order(graph):
            per_layer.setdefault(layer[node], []).append(node)
        max_width = max((len(nodes) for nodes in per_layer.values()), default=1)

        positions = {}
        row_height = max_width * 1.1 + 1.0
        for depth in range(n_layers):
            nodes = per_layer.get(depth, [])
            row, column = divmod(depth, columns)
            if row % 2 == 1:                      # odd rows run right to left
                column = columns - 1 - column
            for slot, node in enumerate(nodes):
                offset = (slot - (len(nodes) - 1) / 2) * 1.1
                positions[node] = (column * COLUMN_WIDTH, -(row * row_height) - offset)
        return positions, n_layers

    def plot(self, graph, path=None, columns=DEFAULT_COLUMNS, title=None):
        """Draw ``graph``; save to ``path`` (PNG/SVG/PDF) when given. Returns the figure."""
        positions, _ = self.layout(graph, columns)
        xs = [x for x, _ in positions.values()] or [0]
        ys = [y for _, y in positions.values()] or [0]
        width = max(6.0, (max(xs) - min(xs) + COLUMN_WIDTH) * 0.95)
        height = max(2.5, (max(ys) - min(ys) + 1.8) * 0.8)
        fig, ax = plt.subplots(figsize=(width, height))
        ax.set_xlim(min(xs) - 1.4, max(xs) + 1.4)
        ax.set_ylim(min(ys) - 0.9, max(ys) + 0.9)

        boxes = {}
        for node, (x, y) in positions.items():
            data = graph.nodes[node]
            value = data.get("value")
            text = wrap_label(data.get("activity", data["label"]))
            if value is not None:
                text = f"{text}\n{short_tag(value)}"
            boxes[node] = ax.text(
                x, y, text, ha="center", va="center", fontsize=7, color=TEXT_COLOUR,
                zorder=3, bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                                    edgecolor=self.colours.get(value, OTHER_COLOUR), linewidth=2))

        # Draw once so the boxes have their final size, then let every arrow
        # start and end at the border of its boxes instead of their centres.
        fig.canvas.draw()
        for source, target in graph.edges:
            (x1, y1), (x2, y2) = positions[source], positions[target]
            # Edges that skip over nodes in the same row bend, so they do not hide them.
            # (1.5 columns, not 1, so rounding errors do not bend neighbouring arrows.)
            skips = abs(y2 - y1) < 1e-9 and abs(x2 - x1) > 1.5 * COLUMN_WIDTH
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1), zorder=2, arrowprops=dict(
                arrowstyle="-|>", color=EDGE_COLOUR, lw=1.0, mutation_scale=10,
                shrinkA=2, shrinkB=2, patchA=boxes[source].get_bbox_patch(),
                patchB=boxes[target].get_bbox_patch(),
                connectionstyle=f"arc3,rad={0.25 if skips else 0.0}"))

        used = sorted({graph.nodes[n].get("value") for n in graph} - {None}, key=natural_sort_key)
        if used:
            ax.legend(handles=[Patch(facecolor="white", edgecolor=self.colours[v], linewidth=2,
                                     label=f"{short_tag(v)} = {v}") for v in used],
                      loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False, fontsize=8)
        ax.set_title(title or f"Instance graph of case {graph.graph.get('case_id')} "
                              f"({graph.number_of_nodes()} events)",
                     fontsize=10, color=TEXT_COLOUR, loc="left")
        ax.axis("off")
        fig.tight_layout()
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
        return fig

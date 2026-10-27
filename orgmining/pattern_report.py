"""Figures and tables for the report on the patterns of step 3.

PatternReport makes, from the outputs of steps 1-3:

    pattern_<id>.png          every pattern, drawn like the instance graphs
    pattern_support.png       share of traces in which each pattern occurs
    pattern_overlap.png       how often two patterns occur in the same traces
    role_handover.png         how often work passes from one role to another
    role_handover.csv         the numbers behind role_handover.png

Roles keep the same colour in every figure (Role_1 is always blue).
"""
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from .instance_graphs import GFileConverter  # noqa: E402
from .model_views import SEQUENTIAL_BLUES  # noqa: E402
from .visualization import (CATEGORICAL_COLOURS, TEXT_COLOUR, InstanceGraphViewer,  # noqa: E402
                            natural_sort_key)

MUTED_COLOUR = "#6b6b66"
GRID_COLOUR = "#e4e4df"


def _style_axes(ax):
    """Recessive axes: no box, light grid, muted ticks."""
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID_COLOUR)
    ax.tick_params(colors=MUTED_COLOUR, labelsize=8, length=0)


def _heatmap(ax, table, value_format, vmax, label_threshold):
    """Sequential one-hue heatmap with values written in the cells."""
    cmap = LinearSegmentedColormap.from_list("sequential_blues", SEQUENTIAL_BLUES)
    image = ax.imshow(table.values, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
    for row in range(table.shape[0]):
        for col in range(table.shape[1]):
            value = table.values[row, col]
            if value >= label_threshold:
                ax.text(col, row, value_format.format(value), ha="center", va="center",
                        fontsize=7, color="white" if value >= 0.55 * vmax else TEXT_COLOUR)
    ax.set_xticks(range(table.shape[1]))
    ax.set_xticklabels(table.columns, fontsize=8, color=TEXT_COLOUR)
    ax.set_yticks(range(table.shape[0]))
    ax.set_yticklabels(table.index, fontsize=8, color=TEXT_COLOUR)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return image


class PatternReport:
    """Builds the report figures from the step 3 output folder."""

    def __init__(self, step3_dir, graphs_path, figures_dir=None):
        self.step3_dir = Path(step3_dir)
        self.figures_dir = Path(figures_dir) if figures_dir else self.step3_dir / "figures"
        self.table = pd.read_csv(self.step3_dir / "patterns.csv")
        self.matrix = pd.read_csv(self.step3_dir / "trace_pattern_matrix.csv", index_col=0)
        with open(self.step3_dir / "patterns.pkl", "rb") as file:
            self.patterns = pickle.load(file)
        self.graphs = GFileConverter.load(graphs_path)
        all_roles = {d.get("value") for g in self.graphs for _, d in g.nodes(data=True)}
        self.viewer = InstanceGraphViewer(self.graphs, values=all_roles)

    # -- individual patterns ------------------------------------------------

    def plot_patterns(self, top=None, columns=5):
        """One figure per pattern; returns the paths."""
        paths = []
        rows = self.table.set_index("pattern")
        for pattern in self.patterns[:top]:
            row = rows.loc[pattern.pattern_id]
            title = (f"{pattern.pattern_id}: in {row.trace_support_pct:.1f}% of the traces "
                     f"({row.traces:,}), {row.instances:,} instances, roles {row.roles}")
            path = self.figures_dir / f"pattern_{pattern.pattern_id}.png"
            self.viewer.plot(pattern.definition, path, columns=columns, title=title)
            paths.append(path)
        return paths

    # -- support ------------------------------------------------------------

    def plot_support(self, top=20):
        """Horizontal bars: share of traces in which each pattern occurs."""
        data = self.table.head(top).iloc[::-1]
        fig, ax = plt.subplots(figsize=(7.5, 0.6 + 0.32 * len(data)))
        ax.barh(range(len(data)), data["trace_support_pct"], height=0.6,
                color=CATEGORICAL_COLOURS[0])
        for y, row in enumerate(data.itertuples()):
            ax.text(row.trace_support_pct + 0.8, y, f"{row.trace_support_pct:.0f}%",
                    va="center", fontsize=7.5, color=TEXT_COLOUR)
        ax.set_yticks(range(len(data)))
        ax.set_yticklabels([f"{r.pattern}  ({r.edges} edges, {r.n_roles} role"
                            f"{'s' if r.n_roles != 1 else ''})" for r in data.itertuples()],
                           fontsize=8, color=TEXT_COLOUR)
        ax.set_xlim(0, 105)
        ax.set_xlabel("% of traces containing the pattern", fontsize=8, color=MUTED_COLOUR)
        ax.xaxis.grid(True, color=GRID_COLOUR, linewidth=0.8)
        ax.set_axisbelow(True)
        _style_axes(ax)
        ax.set_title("Support of the discovered patterns", fontsize=10, color=TEXT_COLOUR,
                     loc="left")
        return self._save(fig, "pattern_support.png")

    # -- overlap between patterns -------------------------------------------

    def overlap_table(self, top=20):
        """Jaccard similarity of the trace sets of two patterns, in %."""
        matrix = self.matrix.iloc[:, :top].astype(bool)
        columns = matrix.columns
        table = pd.DataFrame(0.0, index=columns, columns=columns)
        for a in columns:
            for b in columns:
                union = (matrix[a] | matrix[b]).sum()
                table.loc[a, b] = 100 * (matrix[a] & matrix[b]).sum() / union if union else 0
        return table

    def plot_overlap(self, top=20):
        table = self.overlap_table(top)
        size = 1.2 + 0.38 * len(table)
        fig, ax = plt.subplots(figsize=(size + 1.2, size))
        image = _heatmap(ax, table.round(0), "{:.0f}", vmax=100, label_threshold=1)
        ax.xaxis.tick_top()
        bar = fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02)
        bar.set_label("% of traces shared (Jaccard)", fontsize=8, color=TEXT_COLOUR)
        bar.ax.tick_params(labelsize=7)
        ax.set_title("Which patterns occur in the same traces", fontsize=10,
                     color=TEXT_COLOUR, loc="left", pad=24)
        return self._save(fig, "pattern_overlap.png")

    # -- handover of work between roles -------------------------------------

    def handover_table(self):
        """Edges of all instance graphs counted per (from role, to role)."""
        counts = {}
        for graph in self.graphs:
            for source, target in graph.edges:
                pair = (graph.nodes[source].get("value"), graph.nodes[target].get("value"))
                counts[pair] = counts.get(pair, 0) + 1
        table = pd.Series(counts).unstack(fill_value=0)
        roles = sorted(set(table.index) | set(table.columns), key=natural_sort_key)
        return table.reindex(index=roles, columns=roles, fill_value=0)

    def plot_handover(self):
        counts = self.handover_table()
        counts.to_csv(self.step3_dir / "role_handover.csv")
        # Share of the outgoing edges of each role, so small roles are readable too.
        shares = counts.div(counts.sum(axis=1).replace(0, 1), axis=0) * 100
        shares.index = [f"{role}  ({counts.loc[role].sum():,})" for role in shares.index]
        fig, ax = plt.subplots(figsize=(7.2, 5.2))
        image = _heatmap(ax, shares.round(0), "{:.0f}", vmax=100, label_threshold=1)
        ax.xaxis.tick_top()
        ax.set_xlabel("to role (next event)", fontsize=8, color=MUTED_COLOUR)
        ax.xaxis.set_label_position("top")
        ax.set_ylabel("from role (outgoing edges in brackets)", fontsize=8, color=MUTED_COLOUR)
        bar = fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02)
        bar.set_label("% of the role's outgoing edges", fontsize=8, color=TEXT_COLOUR)
        bar.ax.tick_params(labelsize=7)
        ax.set_title("Handover of work between roles (all instance graphs)", fontsize=10,
                     color=TEXT_COLOUR, loc="left", pad=34)
        return self._save(fig, "role_handover.png")

    # -- all ----------------------------------------------------------------

    def build(self, top=20):
        paths = self.plot_patterns(top)
        paths += [self.plot_support(top), self.plot_overlap(top), self.plot_handover()]
        return paths

    def _save(self, fig, name):
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        path = self.figures_dir / name
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

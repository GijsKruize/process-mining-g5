"""Views to check the intermediate results by eye: Petri nets and roles.

PetriNetRenderer   draws a Petri net (.pnml, or discovered from a log) with
                   pm4py's visualiser. This needs the Graphviz program 'dot'
                   (not only the Python package 'graphviz'); see README.md.
RoleActivityMatrix shows, for every activity, which share of its events is
                   performed by each role (heatmap + CSV). If the roles make
                   sense, most activities are dominated by one or two roles.
"""
import os
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # write image files; no window needed
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pm4py  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from pm4py.objects.log.importer.xes import importer as xes_importer  # noqa: E402
from pm4py.objects.petri_net.importer import importer as pnml_importer  # noqa: E402
from pm4py.visualization.petri_net import visualizer as pn_visualizer  # noqa: E402

from .visualization import TEXT_COLOUR, natural_sort_key  # noqa: E402

# Where the Windows installer (winget install Graphviz.Graphviz) puts 'dot'.
GRAPHVIZ_WINDOWS_DIRS = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Graphviz" / "bin",
                         Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Graphviz" / "bin"]

# One-hue sequential ramp (light -> dark blue) from the dataviz guidelines.
SEQUENTIAL_BLUES = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
                    "#256abf", "#184f95", "#0d366b"]


def ensure_graphviz():
    """Make sure the Graphviz program 'dot' can be found; raise a clear error if not.

    A freshly installed Graphviz is often not yet on the PATH of an open
    terminal, so its standard install folders are added when needed.
    """
    if shutil.which("dot"):
        return
    for folder in GRAPHVIZ_WINDOWS_DIRS:
        if (folder / "dot.exe").is_file():
            os.environ["PATH"] = f"{folder}{os.pathsep}{os.environ.get('PATH', '')}"
            return
    raise RuntimeError(
        "The Graphviz program 'dot' was not found. 'pip install graphviz' only installs the "
        "Python wrapper; install the program itself, e.g. on Windows: "
        "winget install --id Graphviz.Graphviz -e  (then open a new terminal).")


class PetriNetRenderer:
    """Loads or discovers a Petri net, describes it and draws it."""

    @staticmethod
    def load(pnml_path):
        """Return (net, initial_marking, final_marking) from a .pnml file."""
        return pnml_importer.apply(str(pnml_path))

    @staticmethod
    def discover(log_path, noise_threshold):
        """Discover a net with the (infrequent) Inductive Miner, exactly as step 2 does."""
        log = xes_importer.apply(str(log_path))
        return pm4py.discover_petri_net_inductive(log, noise_threshold=noise_threshold)

    @staticmethod
    def describe(net):
        """Size of the net and its parallel constructs, as text."""
        visible = [t for t in net.transitions if t.label is not None]
        and_splits = [t for t in net.transitions if len(t.out_arcs) > 1]
        and_joins = [t for t in net.transitions if len(t.in_arcs) > 1]
        lines = [f"{len(visible)} visible transitions, "
                 f"{len(net.transitions) - len(visible)} silent transitions, "
                 f"{len(net.places)} places, {len(net.arcs)} arcs",
                 f"{len(and_splits)} AND-split(s), {len(and_joins)} AND-join(s)"]
        for split in and_splits:
            branches = sorted(PetriNetRenderer._first_visible_after(arc.target)
                              for arc in split.out_arcs)
            lines.append(f"  AND-split after '{split.label or 'silent'}': parallel branches "
                         f"start with {', '.join(branches)}")
        return "\n".join(lines)

    @staticmethod
    def _first_visible_after(place, limit=50):
        """Label of the first visible transition reachable from ``place`` (for describe)."""
        frontier, seen = [place], set()
        while frontier and len(seen) < limit:
            node = frontier.pop(0)
            if node in seen:
                continue
            seen.add(node)
            for arc in node.out_arcs:
                label = getattr(arc.target, "label", None)
                if label is not None:
                    return label
                frontier.append(arc.target)
        return "?"

    @staticmethod
    def render(net, initial_marking, final_marking, path, rankdir="LR"):
        """Draw the net to ``path``; the format follows the extension (.svg, .png, .pdf)."""
        ensure_graphviz()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        gviz = pn_visualizer.apply(net, initial_marking, final_marking, parameters={
            pn_visualizer.Variants.WO_DECORATION.value.Parameters.FORMAT: path.suffix.lstrip("."),
            pn_visualizer.Variants.WO_DECORATION.value.Parameters.RANKDIR: rankdir,
        })
        pn_visualizer.save(gviz, str(path))
        return path


class RoleActivityMatrix:
    """Activity x role table: which share of an activity's events each role performs."""

    def __init__(self, label_counts):
        """``label_counts``: DataFrame of step 1's label_counts.csv."""
        counts = label_counts.pivot_table(index="original_activity",
                                          columns="selected_attribute_value",
                                          values="events", aggfunc="sum", fill_value=0)
        counts = counts[sorted(counts.columns, key=natural_sort_key)]
        self.counts = counts
        self.shares = counts.div(counts.sum(axis=1), axis=0) * 100

    @classmethod
    def from_step1(cls, step1_dir):
        return cls(pd.read_csv(Path(step1_dir) / "label_counts.csv"))

    def ordered_activities(self):
        """Group activities by their main role, so each role's work forms a block."""
        main_role = self.shares.idxmax(axis=1)
        role_rank = {role: i for i, role in enumerate(self.shares.columns)}
        return sorted(self.shares.index,
                      key=lambda act: (role_rank[main_role[act]], -self.shares.loc[act].max(), act))

    def summary(self):
        """Per activity: total events, main role and its share, number of roles >= 10%."""
        table = pd.DataFrame({
            "events": self.counts.sum(axis=1),
            "main_role": self.shares.idxmax(axis=1),
            "main_role_pct": self.shares.max(axis=1).round(1),
            "roles_with_10pct_or_more": (self.shares >= 10).sum(axis=1),
        })
        return table.loc[self.ordered_activities()]

    def plot(self, path):
        """Heatmap of the shares; cells of 5% or more are labelled with their value."""
        shares = self.shares.loc[self.ordered_activities()]
        n_rows, n_cols = shares.shape
        fig, ax = plt.subplots(figsize=(2.8 + 0.75 * n_cols, 1.2 + 0.24 * n_rows))
        cmap = LinearSegmentedColormap.from_list("sequential_blues", SEQUENTIAL_BLUES)
        image = ax.imshow(shares.values, cmap=cmap, vmin=0, vmax=100, aspect="auto")

        for row in range(n_rows):
            for col in range(n_cols):
                value = shares.values[row, col]
                if value >= 5:
                    ax.text(col, row, f"{value:.0f}", ha="center", va="center", fontsize=6.5,
                            color="white" if value >= 55 else TEXT_COLOUR)

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(shares.columns, fontsize=8, color=TEXT_COLOUR)
        ax.xaxis.tick_top()
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels([f"{act}  ({self.counts.loc[act].sum():,})" for act in shares.index],
                           fontsize=7, color=TEXT_COLOUR)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        colorbar = fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
        colorbar.set_label("% of the activity's events", fontsize=8, color=TEXT_COLOUR)
        colorbar.ax.tick_params(labelsize=7)
        ax.set_title("Share of each activity's events per role (events per activity in brackets)",
                     fontsize=9, color=TEXT_COLOUR, loc="left", pad=22)
        fig.tight_layout()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

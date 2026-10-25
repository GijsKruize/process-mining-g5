"""Evaluation on synthetic logs: run the whole pipeline and compare with the injected patterns.

For every noise level the experiment
    1. generates a synthetic log (``synthetic/`` in the repository, seeded),
    2. runs step 1 (roles), step 2 (Inductive Miner + BIG) and step 3 (SUBDUE),
    3. maps the discovered roles to the true departments (via the employees),
    4. translates the gold standard to the discovered role names and computes
       precision / recall / F1, also for the frequent-path baseline.

Results: ``outputs/synthetic/results.csv`` and ``results.png``.
"""
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402
from .evaluation import (FrequentPathBaseline, GoldPattern, GoldStandard, evaluate,  # noqa: E402
                         parse_edges)
from .instance_graphs import DEFAULT_NOISE_THRESHOLD, GFileConverter, InstanceGraphBuilder  # noqa: E402
from .log_io import write_dataframe_as_xes  # noqa: E402
from .pattern_mining import PatternMiner, SubdueSettings  # noqa: E402
from .pattern_report import GRID_COLOUR, MUTED_COLOUR, _style_axes  # noqa: E402
from .preprocessing import GROUPING_ROLES, EventLogPreprocessor  # noqa: E402
from .roles import DEFAULT_ROLES_THRESHOLD  # noqa: E402
from .synthetic import (SyntheticLogGenerator, employees, gold_standard_table,  # noqa: E402
                        match_roles_to_departments, translate_gold)
from .visualization import CATEGORICAL_COLOURS, TEXT_COLOUR  # noqa: E402

SYNTHETIC_DATA_DIR = config.PROJECT_ROOT / "synthetic"
SYNTHETIC_OUTPUT_DIR = config.OUTPUT_DIR / "synthetic"
DEFAULT_NOISE_LEVELS = (0.0, 0.1, 0.2, 0.3)
DEFAULT_SYNTHETIC_SETTINGS = SubdueSettings(iterations=5, num_best=3)


def gold_from_table(table):
    return GoldStandard([GoldPattern(row.id, row.name, parse_edges(row.edges))
                         for row in table.itertuples()])


class SyntheticExperiment:
    def __init__(self, noise_levels=DEFAULT_NOISE_LEVELS, n_cases=500, seed=42,
                 settings=DEFAULT_SYNTHETIC_SETTINGS, roles_threshold=DEFAULT_ROLES_THRESHOLD,
                 top_k=None, miner_noise=DEFAULT_NOISE_THRESHOLD, workers=4,
                 data_dir=SYNTHETIC_DATA_DIR, output_root=SYNTHETIC_OUTPUT_DIR):
        self.noise_levels = noise_levels
        self.n_cases = n_cases
        self.seed = seed
        self.settings = settings
        self.roles_threshold = roles_threshold
        self.top_k = top_k
        self.miner_noise = miner_noise
        self.workers = workers
        self.data_dir = Path(data_dir)
        self.output_root = Path(output_root)

    @staticmethod
    def level_name(noise):
        return f"noise{round(noise * 100):02d}"

    def write_ground_truth(self):
        """Gold standard and employee -> department table, next to the logs."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        gold_standard_table().to_csv(self.data_dir / "gold_standard.csv", index=False)
        pd.Series(employees(), name="department").rename_axis("employee").to_csv(
            self.data_dir / "employees.csv")

    def generate(self, noise):
        """Write the synthetic log of one noise level; returns its path."""
        log, cases = SyntheticLogGenerator(self.n_cases, noise, self.seed).generate()
        name = f"synthetic_{self.level_name(noise)}"
        cases.to_csv(self.data_dir / f"{name}_cases.csv", index=False)
        return write_dataframe_as_xes(log, self.data_dir / f"{name}.xes")

    def run_one(self, noise):
        out = self.output_root / self.level_name(noise)
        print(f"\n===== Synthetic log, noise {noise:.0%} =====")
        timings = {}
        xes_path = self.generate(noise)

        started = time.time()
        step1 = EventLogPreprocessor.from_xes(xes_path, out / "step1").run(
            "org:resource", GROUPING_ROLES, self.roles_threshold, self.top_k)
        timings["step1_s"] = time.time() - started

        started = time.time()
        step2 = InstanceGraphBuilder(step1.output_dir, out / "step2", self.miner_noise,
                                     self.workers).run()
        timings["step2_s"] = time.time() - started

        started = time.time()
        miner = PatternMiner(step2.graphs_path, step1.output_dir / "label_counts.csv",
                             out / "step3", self.settings)
        patterns, _, _ = miner.run()
        timings["step3_s"] = time.time() - started

        resource_roles = pd.read_csv(step1.output_dir / "resource_roles.csv")
        department_to_role, purity = match_roles_to_departments(resource_roles)
        gold_table = translate_gold(gold_standard_table(), department_to_role)
        gold_table.to_csv(out / "gold_standard_translated.csv", index=False)
        gold = gold_from_table(gold_table)

        discovered = [(p.pattern_id, p.definition) for p in patterns]
        result = evaluate("SUBDUE", discovered, gold)
        graphs = GFileConverter.load(step2.graphs_path)
        baseline = evaluate("frequent paths", FrequentPathBaseline(3).discover(
            graphs, len(discovered)), gold)
        result.per_pattern.to_csv(out / "evaluation_per_pattern.csv", index=False)
        step2_summary = json.loads((step2.output_dir / "summary.json").read_text())

        return {
            "noise": noise,
            "cases": self.n_cases,
            "roles": resource_roles["role"].nunique(),
            "role_purity": round(purity, 3),
            "role_mapping": ", ".join(f"{d}->{r}" for d, r in sorted(department_to_role.items())),
            "labels": step1.n_labels,
            "parallel_graphs_pct": step2_summary["graphs_with_parallelism_pct"],
            "patterns": result.n_patterns,
            "precision": round(result.precision, 3),
            "recall": round(result.recall, 3),
            "f1": round(result.f1, 3),
            "edge_precision": round(result.edge_precision, 3),
            "edge_recall": round(result.edge_recall, 3),
            "gold_found": ", ".join(result.found),
            "baseline_precision": round(baseline.precision, 3),
            "baseline_recall": round(baseline.recall, 3),
            "baseline_f1": round(baseline.f1, 3),
            "baseline_gold_found": ", ".join(baseline.found),
            **{key: round(value, 1) for key, value in timings.items()},
        }

    def sweep(self, noise, beams=(2, 4, 10), iterations=(1, 3, 5, 10), top_ks=(None, 3, 2)):
        """Parameter study on one synthetic log: role top-k x beam width x iterations.

        Steps 1 and 2 run once per top-k; SUBDUE runs for every combination.
        Writes ``sweep.csv`` with the scores and SUBDUE's run time.
        """
        self.write_ground_truth()
        xes_path = self.generate(noise)
        rows = []
        for top_k in top_ks:
            out = self.output_root / "sweep" / f"top{top_k or 'all'}"
            step1 = EventLogPreprocessor.from_xes(xes_path, out / "step1").run(
                "org:resource", GROUPING_ROLES, self.roles_threshold, top_k)
            step2 = InstanceGraphBuilder(step1.output_dir, out / "step2", self.miner_noise,
                                         self.workers).run()
            mapping, purity = match_roles_to_departments(
                pd.read_csv(step1.output_dir / "resource_roles.csv"))
            gold = gold_from_table(translate_gold(gold_standard_table(), mapping))
            for beam in beams:
                for n_iterations in iterations:
                    settings = SubdueSettings(beam_width=beam, iterations=n_iterations,
                                              num_best=self.settings.num_best)
                    started = time.time()
                    patterns, _, _ = PatternMiner(
                        step2.graphs_path, step1.output_dir / "label_counts.csv",
                        out / f"step3_beam{beam}_it{n_iterations}", settings).run()
                    seconds = time.time() - started
                    result = evaluate("SUBDUE", [(p.pattern_id, p.definition) for p in patterns],
                                      gold)
                    rows.append({"noise": noise, "top_k_roles": top_k or "all",
                                 "roles": len(set(mapping.values())),
                                 "role_purity": round(purity, 3), "labels": step1.n_labels,
                                 "beam": beam, "iterations": n_iterations,
                                 "patterns": result.n_patterns,
                                 "precision": round(result.precision, 3),
                                 "recall": round(result.recall, 3), "f1": round(result.f1, 3),
                                 "gold_found": ", ".join(result.found),
                                 "subdue_s": round(seconds, 1)})
        table = pd.DataFrame(rows)
        self.output_root.mkdir(parents=True, exist_ok=True)
        table.to_csv(self.output_root / "sweep.csv", index=False)
        return table

    def run(self):
        self.write_ground_truth()
        self.output_root.mkdir(parents=True, exist_ok=True)
        rows = [self.run_one(noise) for noise in self.noise_levels]
        table = pd.DataFrame(rows)
        table.to_csv(self.output_root / "results.csv", index=False)
        self.plot(table, self.output_root / "results.png")
        return table

    @staticmethod
    def plot(table, path):
        """Precision, recall and F1 of SUBDUE (solid) and F1 of the baseline (dashed) per noise level."""
        fig, ax = plt.subplots(figsize=(6.4, 3.6))
        x = table["noise"] * 100
        for i, (column, label) in enumerate([("precision", "Precision"), ("recall", "Recall"),
                                             ("f1", "F1")]):
            ax.plot(x, table[column], marker="o", markersize=6, linewidth=2,
                    color=CATEGORICAL_COLOURS[i], label=f"SUBDUE {label}")
        ax.plot(x, table["baseline_f1"], marker="s", markersize=6, linewidth=2, linestyle="--",
                color=CATEGORICAL_COLOURS[3], label="Frequent paths F1")
        ax.set_xlabel("noise (% of cases with one disturbance)", fontsize=8, color=MUTED_COLOUR)
        ax.set_ylim(0, 1.05)
        ax.set_xticks(x)
        ax.yaxis.grid(True, color=GRID_COLOUR, linewidth=0.8)
        ax.set_axisbelow(True)
        _style_axes(ax)
        ax.legend(frameon=False, fontsize=8, loc="lower left")
        ax.set_title("Synthetic logs: injected patterns recovered", fontsize=10,
                     color=TEXT_COLOUR, loc="left")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

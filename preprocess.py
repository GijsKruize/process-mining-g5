"""Step 1 of the organizational process mining pipeline: event log preprocessing.

Loads an XES event log, lets the user pick an attribute to fuse with the
activity name for resource-task assignment, relabels every event, and
exports the result as XES + CSV so it can feed the later Inductive Miner,
BIG, and SUBDUE pipeline steps.

Run ``python preprocess.py --help`` for the command line options, or see
README.md for full usage instructions.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import pandas as pd
import yaml
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import EventLog

# Standard pm4py/XES attribute keys used throughout the pipeline.
ACTIVITY_KEY = "concept:name"
CASE_KEY = "case:concept:name"
UNKNOWN_LABEL = "UNKNOWN"

# Characters that would break downstream graph tooling (BIG/SUBDUE, XES, DOT, ...).
_INVALID_CHARS_RE = re.compile(r"[\s,'\"<>]+")

DEFAULT_CONFIG_PATH = Path("config.yaml")


@dataclass
class PipelineConfig:
    """Adjustable pipeline parameters.

    Values come from ``config.yaml`` by default and can be overridden with
    command line flags (see :func:`parse_args`). Keeping these out of the
    code means the pipeline can be tuned per run without editing source.
    """

    input_path: Path = field(default_factory=lambda: Path("data"))
    output_dir: Path = field(default_factory=lambda: Path("output"))
    n_examples: int = 3
    top_n_labels: int = 10

    @classmethod
    def from_yaml(cls, path: Path) -> "PipelineConfig":
        """Load a config from a YAML file, falling back to defaults for any missing key."""
        with open(path, "r", encoding="utf-8") as config_file:
            raw = yaml.safe_load(config_file) or {}
        defaults = cls()
        return cls(
            input_path=Path(raw.get("input_path", defaults.input_path)),
            output_dir=Path(raw.get("output_dir", defaults.output_dir)),
            n_examples=int(raw.get("n_examples", defaults.n_examples)),
            top_n_labels=int(raw.get("top_n_labels", defaults.top_n_labels)),
        )


@dataclass
class ColumnInfo:
    """Distinct-value statistics for one DataFrame column."""

    name: str
    n_distinct: int
    examples: List[str]


class EventLogRepository:
    """Handles reading an XES log and writing the relabelled result back out."""

    @staticmethod
    def resolve_input_path(path: Path) -> Path:
        """Resolve *path* to a concrete XES file.

        If *path* is a directory, it must contain exactly one ``*.xes`` file.
        """
        if path.is_dir():
            candidates = sorted(path.glob("*.xes"))
            if not candidates:
                raise FileNotFoundError(f"No .xes file found in directory '{path}'.")
            if len(candidates) > 1:
                names = ", ".join(candidate.name for candidate in candidates)
                raise FileNotFoundError(
                    f"Multiple .xes files found in '{path}' ({names}); "
                    "pass the exact file path as a command line argument."
                )
            return candidates[0]
        return path

    def load(self, path: Path) -> EventLog:
        """Import an XES event log from *path*, raising a clear error if unreadable."""
        resolved = self.resolve_input_path(path)
        if not resolved.exists():
            raise FileNotFoundError(
                f"Input log not found: '{resolved}'. Pass the path as a command line "
                f"argument or place an .xes file in '{path}/'."
            )
        try:
            return xes_importer.apply(str(resolved))
        except Exception as exc:  # pm4py can raise several different exception types
            raise RuntimeError(f"Could not parse XES file at '{resolved}': {exc}") from exc

    @staticmethod
    def to_dataframe(log: EventLog) -> pd.DataFrame:
        """Convert a pm4py EventLog into a flat pandas DataFrame."""
        return log_converter.apply(log, variant=log_converter.Variants.TO_DATA_FRAME)

    @staticmethod
    def to_event_log(df: pd.DataFrame) -> EventLog:
        """Convert a pandas DataFrame back into a pm4py EventLog."""
        return log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)

    @staticmethod
    def export_xes(log: EventLog, path: Path) -> None:
        """Export *log* to XES at *path*, creating parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        xes_exporter.apply(log, str(path))

    @staticmethod
    def export_csv(df: pd.DataFrame, path: Path) -> None:
        """Save *df* as CSV at *path*, creating parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)


class LogReporter:
    """Prints log summaries, column overviews, and relabelling statistics."""

    def __init__(self, n_examples: int = 3, top_n_labels: int = 10) -> None:
        self.n_examples = n_examples
        self.top_n_labels = top_n_labels

    @staticmethod
    def summarize(df: pd.DataFrame) -> dict:
        """Compute trace/event/activity counts for *df*."""
        return {
            "n_traces": df[CASE_KEY].nunique(),
            "n_events": len(df),
            "n_activities": df[ACTIVITY_KEY].nunique(),
        }

    def print_summary(self, df: pd.DataFrame) -> None:
        """Print number of traces, events, and distinct activities."""
        stats = self.summarize(df)
        print("Event log summary")
        print(f"  traces:     {stats['n_traces']}")
        print(f"  events:     {stats['n_events']}")
        print(f"  activities: {stats['n_activities']}")

    def describe_columns(self, df: pd.DataFrame) -> List[ColumnInfo]:
        """Build per-column stats: distinct value count and a few example values."""
        columns_info = []
        for column in df.columns:
            non_null = df[column].dropna()
            examples = [str(value) for value in non_null.unique()[: self.n_examples]]
            columns_info.append(
                ColumnInfo(name=column, n_distinct=int(non_null.nunique()), examples=examples)
            )
        return columns_info

    @staticmethod
    def print_column_overview(columns_info: List[ColumnInfo]) -> None:
        """Print every column, numbered, with distinct count and example values."""
        print("\nAvailable attributes:")
        for index, column in enumerate(columns_info, start=1):
            examples = ", ".join(column.examples)
            print(
                f"  {index:2d}. {column.name}  "
                f"(distinct={column.n_distinct}; examples: {examples})"
            )

    def print_relabel_stats(self, df_before: pd.DataFrame, df_after: pd.DataFrame) -> None:
        """Print distinct-label counts before/after and the top-N new labels."""
        n_before = df_before[ACTIVITY_KEY].nunique()
        n_after = df_after[ACTIVITY_KEY].nunique()
        print(f"\nDistinct activity labels before relabelling: {n_before}")
        print(f"Distinct activity labels after relabelling:  {n_after}")
        print(f"\nTop {self.top_n_labels} new labels:")
        top_labels = df_after[ACTIVITY_KEY].value_counts().head(self.top_n_labels)
        for label, count in top_labels.items():
            print(f"  {label}: {count}")


class AttributeSelector:
    """Interactively selects which attribute to fuse into the activity label."""

    def choose(
        self, columns_info: List[ColumnInfo], input_func: Callable[[str], str] = input
    ) -> str:
        """Prompt for an attribute (by number or name), re-prompting until valid."""
        names = [column.name for column in columns_info]
        while True:
            raw = input_func(
                "\nChoose an attribute (by number or name) for resource-task assignment: "
            ).strip()
            if not raw:
                print("Please enter a value.")
                continue
            if raw.isdigit():
                index = int(raw)
                if 1 <= index <= len(names):
                    return names[index - 1]
                print(f"Number out of range (1-{len(names)}). Try again.")
                continue
            if raw in names:
                return raw
            print(f"'{raw}' is not a valid column name. Try again.")


class MissingValueHandler:
    """Counts and resolves missing/empty values for the chosen attribute."""

    STRATEGIES = ("drop", "unknown")

    @staticmethod
    def _is_missing(series: pd.Series) -> pd.Series:
        missing = series.isna()
        if series.dtype == object:
            # Treat blank strings ("") the same as a real NaN.
            missing = missing | (series.astype(str).str.strip() == "")
        return missing

    def count_missing(self, df: pd.DataFrame, column: str) -> int:
        """Count events with a missing/empty value for *column*."""
        return int(self._is_missing(df[column]).sum())

    def prompt_strategy(
        self, n_missing: int, input_func: Callable[[str], str] = input
    ) -> str:
        """Ask whether to 'drop' missing events or relabel them as 'unknown'."""
        if n_missing == 0:
            return "unknown"
        while True:
            raw = input_func(
                f"{n_missing} events have a missing value. Drop them or relabel as "
                f"{UNKNOWN_LABEL}? [drop/unknown]: "
            ).strip().lower()
            if raw in self.STRATEGIES:
                return raw
            print("Please answer 'drop' or 'unknown'.")

    def apply(self, df: pd.DataFrame, column: str, strategy: str) -> pd.DataFrame:
        """Drop or relabel events with a missing value for *column*."""
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy!r} (expected 'drop' or 'unknown')")
        df = df.copy()
        missing = self._is_missing(df[column])
        if strategy == "drop":
            return df.loc[~missing].reset_index(drop=True)
        df.loc[missing, column] = UNKNOWN_LABEL
        return df


class ActivityRelabeler:
    """Builds ``<activity>_<attribute value>`` labels and installs them as the activity key."""

    @staticmethod
    def sanitize_label_part(value: object) -> str:
        """Strip/replace characters that would break downstream graph tooling."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return UNKNOWN_LABEL
        text = _INVALID_CHARS_RE.sub("_", str(value)).strip("_")
        return text or UNKNOWN_LABEL

    def relabel(self, df: pd.DataFrame, attribute: str) -> pd.DataFrame:
        """Return a copy of *df* whose activity key is ``<activity>_<attribute value>``.

        The original activity is preserved in an ``original_activity`` column.
        """
        df = df.copy()
        new_labels = [
            f"{self.sanitize_label_part(activity)}_{self.sanitize_label_part(value)}"
            for activity, value in zip(df[ACTIVITY_KEY], df[attribute])
        ]
        df["original_activity"] = df[ACTIVITY_KEY]
        df[ACTIVITY_KEY] = new_labels
        return df


class PreprocessingPipeline:
    """Orchestrates the full event log preprocessing step.

    Each stage (I/O, reporting, prompting, missing-value handling,
    relabelling) is delegated to its own collaborator class so that later
    pipeline steps can reuse or subclass individual pieces instead of the
    whole flow.
    """

    def __init__(
        self,
        config: PipelineConfig,
        repository: Optional[EventLogRepository] = None,
        reporter: Optional[LogReporter] = None,
        selector: Optional[AttributeSelector] = None,
        missing_handler: Optional[MissingValueHandler] = None,
        relabeler: Optional[ActivityRelabeler] = None,
    ) -> None:
        self.config = config
        self.repository = repository or EventLogRepository()
        self.reporter = reporter or LogReporter(
            n_examples=config.n_examples, top_n_labels=config.top_n_labels
        )
        self.selector = selector or AttributeSelector()
        self.missing_handler = missing_handler or MissingValueHandler()
        self.relabeler = relabeler or ActivityRelabeler()

    def run(self, input_func: Callable[[str], str] = input) -> None:
        """Run the full interactive preprocessing pipeline end to end."""
        log = self.repository.load(self.config.input_path)
        df = self.repository.to_dataframe(log)
        self.reporter.print_summary(df)

        columns_info = self.reporter.describe_columns(df)
        self.reporter.print_column_overview(columns_info)

        attribute = self.selector.choose(columns_info, input_func=input_func)

        n_missing = self.missing_handler.count_missing(df, attribute)
        print(f"\n{n_missing} events have a missing/empty value for '{attribute}'.")
        strategy = self.missing_handler.prompt_strategy(n_missing, input_func=input_func)

        df_handled = self.missing_handler.apply(df, attribute, strategy)
        df_after = self.relabeler.relabel(df_handled, attribute)
        self.reporter.print_relabel_stats(df, df_after)

        relabeled_log = self.repository.to_event_log(df_after)
        xes_out = self.config.output_dir / "relabeled_log.xes"
        csv_out = self.config.output_dir / "relabeled_log.csv"
        self.repository.export_xes(relabeled_log, xes_out)
        self.repository.export_csv(df_after, csv_out)
        print(f"\nExported relabelled XES log to '{xes_out}'")
        print(f"Exported relabelled DataFrame CSV to '{csv_out}'")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments; unset flags fall back to the YAML config."""
    parser = argparse.ArgumentParser(
        description="Preprocess an XES event log for organizational pattern mining."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=None,
        help="Path to the input XES file, or a directory containing exactly one .xes "
        "file. Overrides 'input_path' in the config file.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write output files to. Overrides 'output_dir' in the config file.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to the YAML config file (default: '{DEFAULT_CONFIG_PATH}').",
    )
    parser.add_argument(
        "--n-examples",
        type=int,
        default=None,
        help="Number of example values to show per attribute. Overrides the config file.",
    )
    parser.add_argument(
        "--top-n-labels",
        type=int,
        default=None,
        help="Number of top new labels to print after relabelling. Overrides the config file.",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> PipelineConfig:
    """Build a PipelineConfig from the YAML config file, overridden by any CLI flags."""
    config_path = Path(args.config)
    config = PipelineConfig.from_yaml(config_path) if config_path.exists() else PipelineConfig()

    if args.input_path is not None:
        config.input_path = Path(args.input_path)
    if args.output_dir is not None:
        config.output_dir = Path(args.output_dir)
    if args.n_examples is not None:
        config.n_examples = args.n_examples
    if args.top_n_labels is not None:
        config.top_n_labels = args.top_n_labels
    return config


def main(argv: Optional[List[str]] = None, input_func: Callable[[str], str] = input) -> None:
    """Single entry point: parse arguments, build the pipeline, and run it."""
    args = parse_args(argv)
    config = build_config(args)
    pipeline = PreprocessingPipeline(config)
    try:
        pipeline.run(input_func=input_func)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

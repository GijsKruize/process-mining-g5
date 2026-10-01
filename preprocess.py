"""Step 1: event log preprocessing.

Loads an XES event log, shows the user all attributes, lets them pick one
(e.g. "resource") to fuse into the activity label, and writes out the
relabelled log for step 2.
"""
import argparse
import re
from pathlib import Path

import pandas as pd
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer

ACTIVITY_KEY = "concept:name"
CASE_KEY = "case:concept:name"
ATTRIBUTE_EXCLUDE = {
    ACTIVITY_KEY,
    CASE_KEY,
    "time:timestamp",
    "EventID",
    "OfferID",
    "original_activity",
}


class Preprocessor:
    """Relabels every event as ``<activity>_<selected attribute value>``."""

    def __init__(self, log_path):
        self.log_path = Path(log_path)

    def load_dataframe(self):
        log = xes_importer.apply(str(self.log_path))
        return log_converter.apply(log, variant=log_converter.Variants.TO_DATA_FRAME)

    @staticmethod
    def show_attributes(df):
        print(f"\nLog loaded: {df[CASE_KEY].nunique()} traces, {len(df)} events")
        print("\nAvailable attributes:")
        for column in df.columns:
            n_distinct = df[column].nunique(dropna=True)
            examples = df[column].dropna().astype(str).unique()[:3]
            print(f"  {column}  (distinct={n_distinct}, examples: {', '.join(examples)})")

    @staticmethod
    def recommend_attributes(df, max_distinct=50, min_coverage=0.50):
        """Suggest attributes worth trying before high-cardinality org:resource."""
        rows = []
        priority = {
            "EventOrigin": "coarse work stream / department-like grouping",
            "Action": "event action type, useful for work-practice variants",
            "lifecycle:transition": "schedule/start/complete handoff granularity",
            "org:group": "organizational group with lower cardinality than resource",
            "org:role": "role-level organizational attribute",
        }

        for column in df.columns:
            if column in ATTRIBUTE_EXCLUDE:
                continue
            series = df[column]
            n_distinct = int(series.nunique(dropna=True))
            coverage = float(series.notna().mean())
            if n_distinct < 2:
                continue

            reason = None
            if column in priority:
                reason = priority[column]
            elif column.startswith("org:") and n_distinct <= max_distinct:
                reason = "organizational attribute at manageable granularity"
            elif column.startswith("case:") and n_distinct <= max_distinct:
                reason = "case-level context for validation slices"
            elif n_distinct <= max_distinct and coverage >= min_coverage:
                reason = "low-cardinality event attribute"

            if reason:
                examples = series.dropna().astype(str).unique()[:5]
                rows.append({
                    "attribute": column,
                    "distinct_values": n_distinct,
                    "coverage": round(coverage, 3),
                    "examples": " | ".join(examples),
                    "reason": reason,
                })

        rows.sort(key=lambda row: (
            0 if row["attribute"] in priority else 1,
            row["distinct_values"],
            row["attribute"],
        ))
        return rows

    @staticmethod
    def show_recommended_attributes(rows):
        if not rows:
            return
        print("\nRecommended lower-granularity attributes to try before org:resource:")
        for row in rows[:10]:
            print(f"  {row['attribute']}  (distinct={row['distinct_values']}, "
                  f"coverage={row['coverage']:.0%}) - {row['reason']}")

    @staticmethod
    def choose_attribute(df, attribute=None):
        if attribute is not None:
            if attribute not in df.columns:
                raise ValueError(f"'{attribute}' is not a column in the log")
            return attribute
        while True:
            attribute = input("\nAttribute to fuse into the activity label: ").strip()
            if attribute in df.columns:
                return attribute
            print(f"'{attribute}' is not a column in the log, try again.")

    @staticmethod
    def relabel(df, attribute):
        """Return a copy of df whose activity is <activity>_<attribute value>."""
        df = df.copy()
        df["original_activity"] = df[ACTIVITY_KEY]
        values = df[attribute].fillna("UNKNOWN").astype(str)
        # spaces would break the .g file format used in step 2
        values = values.apply(lambda v: re.sub(r"\s+", "", v))
        df[ACTIVITY_KEY] = df[ACTIVITY_KEY].astype(str) + "_" + values
        return df

    def run(self, attribute=None, output_dir="output"):
        df = self.load_dataframe()
        self.show_attributes(df)
        recommendations = self.recommend_attributes(df)
        self.show_recommended_attributes(recommendations)
        attribute = self.choose_attribute(df, attribute)

        df = self.relabel(df, attribute)
        print(f"\n{df[ACTIVITY_KEY].nunique()} distinct activity labels after fusing '{attribute}' "
              f"(was {df['original_activity'].nunique()}).")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(recommendations).to_csv(output_dir / "attribute_recommendations.csv", index=False)
        relabeled_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
        xes_path = output_dir / "relabeled_log.xes"
        xes_exporter.apply(relabeled_log, str(xes_path))
        df.to_csv(output_dir / "relabeled_log.csv", index=False)
        print(f"Saved relabelled log to '{xes_path}'")
        return xes_path


def main():
    parser = argparse.ArgumentParser(description="Step 1: preprocess the event log.")
    parser.add_argument("input_path", help="Path to the input .xes file")
    parser.add_argument("--attribute", default=None,
                         help="Attribute to fuse into the activity label (skips the interactive prompt)")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    Preprocessor(args.input_path).run(attribute=args.attribute, output_dir=args.output_dir)


if __name__ == "__main__":
    main()

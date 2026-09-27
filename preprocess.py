"""Step 1: event log preprocessing.

Loads an XES event log, shows the user all attributes, lets them pick one
(e.g. "resource") to fuse into the activity label, and writes out the
relabelled log for step 2.
"""
import argparse
import re
from pathlib import Path

from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer

ACTIVITY_KEY = "concept:name"
CASE_KEY = "case:concept:name"


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
        attribute = self.choose_attribute(df, attribute)

        df = self.relabel(df, attribute)
        print(f"\n{df[ACTIVITY_KEY].nunique()} distinct activity labels after fusing '{attribute}' "
              f"(was {df['original_activity'].nunique()}).")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
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

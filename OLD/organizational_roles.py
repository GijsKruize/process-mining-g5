"""Step 5 (optional, fast): discover organizational roles with pm4py.

A role is a group of activities performed by a similar set of resources.
This is pm4py's own implementation of:
Burattin, Sperduti, Veluscek. "Business models enhancement through
discovery of roles." IEEE Symposium on Computational Intelligence and Data
Mining (CIDM), 2013.

Our professor suggested this as a fast complement to steps 2-3: BIG instance
graphs + SUBDUE pattern mining can take a long time on the full log, while
role discovery is a single pass over (resource, activity) counts and runs
in seconds. It works directly on the original log (no relabeling needed).

    python organizational_roles.py data/BPI2017Denied(3).xes
"""
import argparse
from pathlib import Path

import pandas as pd
from pm4py.algo.organizational_mining.roles import algorithm as roles_algorithm
from pm4py.algo.organizational_mining.roles.variants.pandas import Parameters
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.importer.xes import importer as xes_importer

DEFAULT_ACTIVITY_KEY = "concept:name"
DEFAULT_RESOURCE_KEY = "org:resource"
DEFAULT_THRESHOLD = 0.65


class RoleMiner:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_dataframe(log_path):
        log = xes_importer.apply(str(log_path))
        return log_converter.apply(log, variant=log_converter.Variants.TO_DATA_FRAME)

    @staticmethod
    def roles_to_rows(roles):
        rows = []
        for role_id, (activities, resource_counts) in enumerate(roles):
            resources_by_count = sorted(resource_counts.items(), key=lambda kv: -kv[1])
            rows.append({
                "role_id": role_id,
                "num_activities": len(activities),
                "num_resources": len(resource_counts),
                "total_events": sum(resource_counts.values()),
                "activities": "; ".join(sorted(activities)),
                "resources": "; ".join(f"{res}:{count}" for res, count in resources_by_count),
            })
        rows.sort(key=lambda row: -row["total_events"])
        return rows

    def run(self, log_path, activity_key=DEFAULT_ACTIVITY_KEY, resource_key=DEFAULT_RESOURCE_KEY,
            threshold=DEFAULT_THRESHOLD):
        df = self.load_dataframe(log_path)
        if resource_key not in df.columns:
            raise ValueError(f"'{resource_key}' is not a column in the log")
        if activity_key not in df.columns:
            raise ValueError(f"'{activity_key}' is not a column in the log")

        roles = roles_algorithm.apply(df, parameters={
            Parameters.ACTIVITY_KEY: activity_key,
            Parameters.RESOURCE_KEY: resource_key,
            Parameters.ROLES_THRESHOLD_PARAMETER: threshold,
        })

        rows = self.roles_to_rows(roles)
        roles_df = pd.DataFrame(rows)
        out_path = self.output_dir / "organizational_roles.csv"
        roles_df.to_csv(out_path, index=False)

        print(f"Discovered {len(rows)} organizational role(s) (threshold={threshold}), "
              f"saved to '{out_path}'")
        for row in rows:
            print(f"  role {row['role_id']}: {row['num_activities']} activities, "
                  f"{row['num_resources']} resources, {row['total_events']} events "
                  f"-- {row['activities']}")
        return roles


def main():
    parser = argparse.ArgumentParser(description="Step 5: discover organizational roles.")
    parser.add_argument("input_path", help="Path to a .xes event log")
    parser.add_argument("--activity-key", default=DEFAULT_ACTIVITY_KEY)
    parser.add_argument("--resource-key", default=DEFAULT_RESOURCE_KEY,
                         help="Attribute identifying the resource/originator of each event")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                         help="Similarity threshold for merging roles (0-1, default 0.65)")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    RoleMiner(args.output_dir).run(
        args.input_path,
        activity_key=args.activity_key,
        resource_key=args.resource_key,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    main()

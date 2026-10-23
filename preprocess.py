"""Step 1: event log preprocessing.

Loads an XES event log, shows the user all attributes, lets them pick one
(e.g. ``org:resource``) and relabels every event as
``<activity>_<attribute group>`` for step 2.

Why there is a grouping step
----------------------------
The assignment asks for the label ``activity_selectedAttribute`` and for the
Petri net to be discovered on that label. With ``org:resource`` on the
BPI 2017 log this gives 3,338 distinct labels (54 activities, 134 users),
and both the Inductive Miner and the alignments in step 2 then run for many
hours. The teacher's advice was to reduce the number of resources, in two
ways that are both implemented here:

* ``--grouping roles``: discover organisational roles with pm4py's role
  discovery (Burattin, Sperduti & Veluscek, 2013) and use the role in place
  of the single user.
* ``--grouping frequency``: keep the most frequent attribute values that
  together cover a share of the events (default 80%) and put the rest in one
  ``OTHER`` category.

``--grouping auto`` (default) uses ``roles`` when the chosen attribute has
more than ``AUTO_GROUPING_MAX_VALUES`` distinct values and no grouping
otherwise, so a coarse attribute such as ``org:group`` is used as it is.

How a role is assigned to a resource
------------------------------------
pm4py's role discovery returns *groups of activities* that are performed by
similar sets of resources, each with the resources that performed them. A
resource therefore usually appears in several roles. Labelling an event with
"the role its activity belongs to" would add nothing, because that role is
determined by the activity alone. Instead every resource is assigned to one
role, the one in which it performs most of its events (its dominant role).
The label ``<activity>_<role>`` then says which kind of worker performed the
activity, including the informative cases where someone works outside their
usual role.

Measured on the BPI 2017 log (54 activities, 134 users, 124,866 events),
whole pipeline with default settings on a 2-core machine:

==============================  =================  ======================
grouping                        distinct labels    whole pipeline
==============================  =================  ======================
none                            3,338              5+ hours (earlier runs)
frequency, 80% of events        1,675 (56 users)   not measured
frequency, 50% of events          670 (24 users)   about 23 minutes
roles (threshold 0.65)            225 (8 roles)    about 8 minutes
==============================  =================  ======================
"""
import argparse
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from pm4py.algo.organizational_mining.roles import algorithm as roles_discovery
from pm4py.algo.organizational_mining.roles.variants.pandas import Parameters as RolesParameters
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
    "attribute_group",
}

GROUPING_CHOICES = ("auto", "none", "roles", "frequency")
# 'auto' groups an attribute by roles when it has more distinct values than this.
AUTO_GROUPING_MAX_VALUES = 20
DEFAULT_GROUPING_COVERAGE = 0.80
# pm4py's own default: two roles are merged while their resource profiles are
# more similar than this.
DEFAULT_ROLES_THRESHOLD = 0.65
OTHER_GROUP = "OTHER"
MISSING_VALUE = "UNKNOWN"


def resolve_input_path(path):
    """Resolve tiny pointer files that contain the real dataset path.

    ``data/BPI2017Denied(3).xes`` is a symbolic link in the repository. Git on
    Windows checks such a link out as a small text file holding the target
    path, which this function follows.
    """
    path = Path(path)
    if path.is_file() and path.stat().st_size < 512:
        content = path.read_text(encoding="utf-8").strip()
        candidate = (path.parent / content).resolve()
        if candidate.is_file():
            print(f"Resolved pointer file '{path}' to '{candidate}'")
            return candidate
    return path


def strip_whitespace(value):
    """Labels must not contain whitespace: BIG's ``.g`` format is space separated."""
    return re.sub(r"\s+", "", str(value))


class Preprocessor:
    """Relabels every event as ``<activity>_<group of the selected attribute>``."""

    def __init__(self, log_path):
        self.log_path = resolve_input_path(log_path)

    def load_dataframe(self):
        log = xes_importer.apply(str(self.log_path))
        return log_converter.apply(log, variant=log_converter.Variants.TO_DATA_FRAME)

    # ----------------------------------------------------------------------
    # Attribute selection (assignment step 1)
    # ----------------------------------------------------------------------

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
        """Attributes with few distinct values, as an overview for the user.

        Note that a low-cardinality attribute is not automatically useful: in
        the BPI 2017 log ``EventOrigin`` is fully determined by the activity
        (each activity has exactly one origin), so fusing it adds nothing.
        The column ``values_per_activity`` exposes this: 1.0 means the
        attribute never varies within an activity.
        """
        rows = []
        priority = {
            "org:resource": "individual resources (use a grouping, see --grouping)",
            "org:group": "organizational group",
            "org:role": "role-level organizational attribute",
            "lifecycle:transition": "schedule/start/complete handoff granularity",
            "Action": "event action type",
            "EventOrigin": "coarse work stream",
        }
        for column in df.columns:
            if column in ATTRIBUTE_EXCLUDE:
                continue
            series = df[column]
            n_distinct = int(series.nunique(dropna=True))
            coverage = float(series.notna().mean())
            if n_distinct < 2:
                continue
            if column not in priority and not (n_distinct <= max_distinct and coverage >= min_coverage):
                continue
            values_per_activity = float(df.groupby(ACTIVITY_KEY)[column].nunique().mean())
            examples = series.dropna().astype(str).unique()[:5]
            rows.append({
                "attribute": column,
                "distinct_values": n_distinct,
                "coverage": round(coverage, 3),
                "values_per_activity": round(values_per_activity, 2),
                "examples": " | ".join(examples),
                "reason": priority.get(column, "low-cardinality attribute"),
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
        print("\nCandidate organisational attributes "
              "(values/activity = 1.0 means the attribute adds no information):")
        for row in rows[:10]:
            print(f"  {row['attribute']}  (distinct={row['distinct_values']}, "
                  f"coverage={row['coverage']:.0%}, values/activity={row['values_per_activity']}) "
                  f"- {row['reason']}")

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

    # ----------------------------------------------------------------------
    # Grouping of attribute values (see module docstring)
    # ----------------------------------------------------------------------

    @staticmethod
    def attribute_values(df, attribute):
        """The attribute as strings, with missing values made explicit."""
        return df[attribute].fillna(MISSING_VALUE).astype(str)

    @staticmethod
    def resolve_grouping(grouping, n_distinct):
        """Turn ``auto`` into a concrete choice."""
        if grouping != "auto":
            return grouping
        return "roles" if n_distinct > AUTO_GROUPING_MAX_VALUES else "none"

    @classmethod
    def group_by_frequency(cls, df, attribute, coverage=DEFAULT_GROUPING_COVERAGE):
        """Keep the most frequent values covering ``coverage`` of the events; rest -> OTHER.

        Returns ``(mapping value -> group, description rows)``.
        """
        if not 0 < coverage <= 1:
            raise ValueError("--grouping-coverage must be in (0, 1]")
        counts = cls.attribute_values(df, attribute).value_counts()
        # value_counts sorts by count; sort ties by name so the selection does
        # not depend on the order of the events in the file.
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        total = int(counts.sum())
        mapping = {}
        rows = []
        covered = 0
        for value, count in ordered:
            keep = covered < coverage * total
            mapping[value] = value if keep else OTHER_GROUP
            if keep:
                covered += count
            rows.append({"value": value, "group": mapping[value], "events": int(count),
                         "share_of_events": round(count / total, 4)})
        return mapping, rows

    @classmethod
    def group_by_roles(cls, df, attribute, threshold=DEFAULT_ROLES_THRESHOLD):
        """Discover roles and assign each attribute value to its dominant role.

        Returns ``(mapping value -> role name, value rows, role rows)``.
        Roles are numbered by the number of events of the resources assigned
        to them, so ``Role_1`` is the largest group of workers.
        """
        frame = pd.DataFrame({
            "resource": cls.attribute_values(df, attribute),
            "activity": df[ACTIVITY_KEY].astype(str),
        })
        # Each role is [sorted list of activities, {resource: number of events}].
        roles = roles_discovery.apply(frame, parameters={
            RolesParameters.RESOURCE_KEY: "resource",
            RolesParameters.ACTIVITY_KEY: "activity",
            RolesParameters.ROLES_THRESHOLD_PARAMETER: threshold,
        })

        # Dominant role of a resource = the role in which it has most events.
        # Ties go to the role that comes first in pm4py's (alphabetical) order.
        dominant = {}
        for role_index, (_, resource_counts) in enumerate(roles):
            for resource, count in resource_counts.items():
                if resource not in dominant or count > dominant[resource][1]:
                    dominant[resource] = (role_index, count)

        events_per_resource = Counter(frame["resource"])
        events_per_role = Counter()
        resources_per_role = Counter()
        for resource, (role_index, _) in dominant.items():
            events_per_role[role_index] += events_per_resource[resource]
            resources_per_role[role_index] += 1

        # Number only the roles that are somebody's dominant role, largest first.
        used_roles = sorted(events_per_role, key=lambda index: (-events_per_role[index], index))
        role_name = {index: f"Role_{rank}" for rank, index in enumerate(used_roles, start=1)}

        mapping = {resource: role_name[role_index] for resource, (role_index, _) in dominant.items()}
        total = sum(events_per_resource.values())
        value_rows = [
            {"value": resource, "group": mapping[resource], "events": events_per_resource[resource],
             "share_of_events": round(events_per_resource[resource] / total, 4),
             "events_in_dominant_role": dominant[resource][1]}
            for resource in sorted(mapping, key=lambda value: (-events_per_resource[value], value))
        ]
        role_rows = [
            {"group": role_name.get(index, ""),
             "resources_assigned": resources_per_role.get(index, 0),
             "events_of_assigned_resources": events_per_role.get(index, 0),
             "activities": " | ".join(activities),
             "resources_performing_these_activities": len(resource_counts)}
            for index, (activities, resource_counts) in enumerate(roles)
        ]
        role_rows.sort(key=lambda row: (row["group"] == "", -row["events_of_assigned_resources"]))
        return mapping, value_rows, role_rows

    # ----------------------------------------------------------------------
    # Relabelling
    # ----------------------------------------------------------------------

    @classmethod
    def relabel(cls, df, attribute, mapping=None):
        """Return a copy of ``df`` whose activity is ``<activity>_<group>``.

        ``original_activity`` keeps the untouched activity and
        ``attribute_group`` the group that was fused in, so later steps and
        the report can always go back to both parts of the label.
        """
        df = df.copy()
        df["original_activity"] = df[ACTIVITY_KEY]
        values = cls.attribute_values(df, attribute)
        if mapping is not None:
            values = values.map(mapping)
        df["attribute_group"] = values.map(strip_whitespace)
        df[ACTIVITY_KEY] = df[ACTIVITY_KEY].astype(str).map(strip_whitespace) + "_" + df["attribute_group"]
        return df

    def run(self, attribute=None, output_dir="output", grouping="auto",
            grouping_coverage=DEFAULT_GROUPING_COVERAGE, roles_threshold=DEFAULT_ROLES_THRESHOLD):
        df = self.load_dataframe()
        self.show_attributes(df)
        recommendations = self.recommend_attributes(df)
        self.show_recommended_attributes(recommendations)
        attribute = self.choose_attribute(df, attribute)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        n_distinct = int(self.attribute_values(df, attribute).nunique())
        chosen_grouping = self.resolve_grouping(grouping, n_distinct)
        mapping = None
        if chosen_grouping == "roles":
            mapping, value_rows, role_rows = self.group_by_roles(df, attribute, roles_threshold)
            pd.DataFrame(role_rows).to_csv(output_dir / "roles.csv", index=False)
            pd.DataFrame(value_rows).to_csv(output_dir / "attribute_groups.csv", index=False)
            print(f"\nGrouping '{attribute}' by discovered roles (threshold {roles_threshold}): "
                  f"{n_distinct} values -> {len(set(mapping.values()))} roles. "
                  f"See '{output_dir / 'roles.csv'}' and '{output_dir / 'attribute_groups.csv'}'.")
        elif chosen_grouping == "frequency":
            mapping, value_rows = self.group_by_frequency(df, attribute, grouping_coverage)
            pd.DataFrame(value_rows).to_csv(output_dir / "attribute_groups.csv", index=False)
            kept = sum(1 for group in mapping.values() if group != OTHER_GROUP)
            print(f"\nGrouping '{attribute}' by frequency: kept the {kept} most frequent of "
                  f"{n_distinct} values (covering {grouping_coverage:.0%} of the events), "
                  f"the rest is '{OTHER_GROUP}'. See '{output_dir / 'attribute_groups.csv'}'.")
        else:
            print(f"\nUsing '{attribute}' without grouping ({n_distinct} distinct values).")
        if grouping == "auto":
            print(f"  (--grouping auto: attributes with more than {AUTO_GROUPING_MAX_VALUES} "
                  "distinct values are grouped by roles; override with --grouping)")

        df = self.relabel(df, attribute, mapping)
        print(f"{df[ACTIVITY_KEY].nunique()} distinct activity labels after fusing '{attribute}' "
              f"(was {df['original_activity'].nunique()}).")

        pd.DataFrame(recommendations).to_csv(output_dir / "attribute_recommendations.csv", index=False)
        relabeled_log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
        xes_path = output_dir / "relabeled_log.xes"
        xes_exporter.apply(relabeled_log, str(xes_path))
        df.to_csv(output_dir / "relabeled_log.csv", index=False)
        print(f"Saved relabelled log to '{xes_path}'")
        return xes_path


def add_preprocess_arguments(parser):
    """Step 1 options, shared by this module's CLI and ``main.py``."""
    parser.add_argument("--attribute", default=None,
                        help="Attribute to fuse into the activity label (skips the interactive prompt)")
    parser.add_argument("--grouping", choices=GROUPING_CHOICES, default="auto",
                        help="How to reduce the number of attribute values: 'roles' (discovered "
                             "organisational roles), 'frequency' (most frequent values, rest OTHER), "
                             "'none', or 'auto' (roles if the attribute has more than "
                             f"{AUTO_GROUPING_MAX_VALUES} values)")
    parser.add_argument("--grouping-coverage", type=float, default=DEFAULT_GROUPING_COVERAGE,
                        help="For --grouping frequency: share of events the kept values must cover")
    parser.add_argument("--roles-threshold", type=float, default=DEFAULT_ROLES_THRESHOLD,
                        help="For --grouping roles: similarity above which two roles are merged")


def main():
    parser = argparse.ArgumentParser(description="Step 1: preprocess the event log.")
    parser.add_argument("input_path", help="Path to the input .xes file")
    parser.add_argument("--output-dir", default="output")
    add_preprocess_arguments(parser)
    args = parser.parse_args()
    Preprocessor(args.input_path).run(
        attribute=args.attribute,
        output_dir=args.output_dir,
        grouping=args.grouping,
        grouping_coverage=args.grouping_coverage,
        roles_threshold=args.roles_threshold,
    )


if __name__ == "__main__":
    main()

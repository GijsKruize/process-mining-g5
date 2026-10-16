"""Step 1 - Event log preprocessing.

Assignment: show the user every attribute in the event log, let them pick one
(e.g. ``org:resource``) on the command line, and give every event the new
label ``activity_selectedAttribute``. In the terms of Diamantini et al. (2016)
each event then becomes an instance of an *entity specification*: an
(activity, executor) pair, at the granularity of the chosen attribute.

The step is split into small functions so each can be read and tested on its
own:

    describe_attributes()   what is in the log?        -> overview table
    print_attribute_table() show that table in the terminal
    ask_for_attribute()     let the user pick one       -> attribute name
    relabel_events()        build activity_value labels -> new DataFrame
    summarise_labels()      how many labels did we get? -> table
    run_preprocessing()     all of the above + save outputs
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import pm4py

from . import config
from .log_io import read_xes_as_dataframe, write_dataframe_as_xes

# Above this many distinct labels the Petri net and BIG in step 2 become slow;
# we only warn, the user stays free to choose.
MANY_LABELS_WARNING = 500
N_EXAMPLE_VALUES = 3


# ---------------------------------------------------------------------------
# 1. Inspect the attributes
# ---------------------------------------------------------------------------

def describe_attributes(df):
    """One row per attribute (column) of the log with basic statistics.

    Columns of the result:
        attribute        name as it appears in the log
        level            'trace' (same value for the whole case) or 'event'
        distinct_values  number of different values
        filled_pct       share of events that have a value
        examples         a few example values
        selectable       False for the activity, case id and timestamp
    """
    rows = []
    for column in df.columns:
        values = df[column].dropna()
        is_trace_level = column.startswith(config.TRACE_ATTRIBUTE_PREFIX)
        rows.append({
            "attribute": column,
            "level": "trace" if is_trace_level else "event",
            "distinct_values": int(values.nunique()),
            "filled_pct": round(100 * len(values) / len(df), 1) if len(df) else 0.0,
            "examples": ", ".join(values.astype(str).unique()[:N_EXAMPLE_VALUES]),
            "selectable": column not in config.NON_SELECTABLE_ATTRIBUTES,
        })
    overview = pd.DataFrame(rows)
    # Event attributes first, then trace attributes; alphabetical within each.
    return overview.sort_values(["level", "attribute"]).reset_index(drop=True)


def print_attribute_table(overview, n_traces, n_events):
    """Print the overview as a numbered table, so the user can pick by number."""
    print(f"\nEvent log: {n_traces:,} traces, {n_events:,} events, "
          f"{len(overview)} attributes\n")
    header = f"{'#':>3}  {'attribute':<28} {'level':<6} {'distinct':>8} {'filled':>7}  examples"
    print(header)
    print("-" * len(header))
    for number, row in enumerate(overview.itertuples(), start=1):
        marker = "" if row.selectable else "  (not selectable)"
        print(f"{number:>3}  {row.attribute:<28} {row.level:<6} {row.distinct_values:>8} "
              f"{row.filled_pct:>6.1f}%  {row.examples[:45]}{marker}")


# ---------------------------------------------------------------------------
# 2. Let the user choose
# ---------------------------------------------------------------------------

def validate_attribute(overview, choice):
    """Turn a user's choice (a number from the table or a name) into an attribute name.

    Raises ValueError with a readable message when the choice is not valid.
    """
    choice = choice.strip()
    names = list(overview["attribute"])
    if choice.isdigit():
        index = int(choice) - 1
        if not 0 <= index < len(names):
            raise ValueError(f"There is no attribute number {choice}.")
        attribute = names[index]
    elif choice in names:
        attribute = choice
    else:
        raise ValueError(f"'{choice}' is not an attribute of this log.")

    if attribute in config.NON_SELECTABLE_ATTRIBUTES:
        raise ValueError(f"'{attribute}' cannot be fused with the activity; pick an "
                         "organisational attribute such as org:resource.")
    return attribute


def ask_for_attribute(overview, input_fn=input):
    """Ask on the command line until the user gives a valid attribute.

    ``input_fn`` is a parameter only so tests can feed answers without a keyboard.
    """
    while True:
        choice = input_fn("\nWhich attribute do you want to analyse? (number or name): ")
        try:
            return validate_attribute(overview, choice)
        except ValueError as error:
            print(f"  {error} Please try again.")


# ---------------------------------------------------------------------------
# 3. Build the new labels
# ---------------------------------------------------------------------------

def clean_label_part(value):
    """Make a value safe to use inside a label.

    BIG writes its graphs as space-separated text (``v 3 A-Submitted``), so a
    label must not contain whitespace. Spaces become '-', which is also the
    style the BPI 2017 activity names already use.
    """
    return re.sub(r"\s+", "-", str(value).strip())


def relabel_events(df, attribute):
    """Return a copy of ``df`` in which every activity is ``<activity>_<value>``.

    Events without a value for ``attribute`` get ``UNKNOWN`` as value, so no
    event is dropped. The original activity and the value are kept in their
    own columns (see config.py for why).
    """
    relabeled = df.copy()
    activity = relabeled[config.ACTIVITY_KEY].map(clean_label_part)
    value = relabeled[attribute].fillna(config.MISSING_VALUE).map(clean_label_part)

    relabeled[config.ORIGINAL_ACTIVITY_KEY] = relabeled[config.ACTIVITY_KEY]
    relabeled[config.ATTRIBUTE_VALUE_KEY] = value
    relabeled[config.ACTIVITY_KEY] = activity + config.LABEL_SEPARATOR + value
    return relabeled


def summarise_labels(relabeled):
    """Frequency of every new label, with its two parts, most frequent first."""
    counts = (relabeled
              .groupby([config.ACTIVITY_KEY, config.ORIGINAL_ACTIVITY_KEY,
                        config.ATTRIBUTE_VALUE_KEY])
              .size()
              .reset_index(name="events")
              .rename(columns={config.ACTIVITY_KEY: "label"}))
    counts["events_pct"] = (100 * counts["events"] / counts["events"].sum()).round(2)
    return counts.sort_values(["events", "label"], ascending=[False, True]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. Put it together
# ---------------------------------------------------------------------------

@dataclass
class PreprocessingResult:
    """What step 1 hands over to step 2."""
    attribute: str
    output_dir: Path
    relabeled_log_path: Path
    n_labels: int


def output_folder_name(attribute):
    """Folder-safe version of an attribute name, e.g. 'org:resource' -> 'org_resource'."""
    return re.sub(r"[^A-Za-z0-9]+", "_", attribute).strip("_")


def run_preprocessing(log_path=config.DEFAULT_LOG_PATH, attribute=None,
                      output_root=config.STEP1_OUTPUT_DIR):
    """Run step 1 end to end and write its outputs.

    If ``attribute`` is None the user is asked interactively; passing it (for
    example via ``--attribute`` on the command line) skips the question, which
    is handy for repeated runs.

    Outputs in ``<output_root>/<attribute>/``:
        attributes_overview.csv   the table shown to the user
        label_counts.csv          every new label with its frequency
        relabeled_log.xes         the relabelled log, input for step 2
        summary.json              settings and headline numbers of this run
    """
    print(f"Reading event log: {log_path}")
    df = read_xes_as_dataframe(log_path)
    n_traces = int(df[config.CASE_ID_KEY].nunique())

    overview = describe_attributes(df)
    print_attribute_table(overview, n_traces, len(df))

    if attribute is None:
        attribute = ask_for_attribute(overview)
    else:
        attribute = validate_attribute(overview, attribute)
    print(f"\nSelected attribute: {attribute}")

    relabeled = relabel_events(df, attribute)
    label_counts = summarise_labels(relabeled)
    n_activities = int(df[config.ACTIVITY_KEY].nunique())
    n_values = int(relabeled[config.ATTRIBUTE_VALUE_KEY].nunique())
    n_labels = len(label_counts)
    n_missing = int(df[attribute].isna().sum())

    print(f"  {n_activities} activities x {n_values} values of '{attribute}' "
          f"-> {n_labels} distinct labels actually occurring")
    if n_missing:
        print(f"  {n_missing:,} events had no value and were labelled "
              f"'<activity>{config.LABEL_SEPARATOR}{config.MISSING_VALUE}'")
    if n_labels > MANY_LABELS_WARNING:
        print(f"  Warning: more than {MANY_LABELS_WARNING} labels. Process discovery and "
              "BIG in step 2 may become slow on this granularity.")
    print("\n  Most frequent new labels:")
    for row in label_counts.head(5).itertuples():
        print(f"    {row.label:<45} {row.events:>7,} events ({row.events_pct}%)")

    output_dir = Path(output_root) / output_folder_name(attribute)
    output_dir.mkdir(parents=True, exist_ok=True)
    overview.to_csv(output_dir / "attributes_overview.csv", index=False)
    label_counts.to_csv(output_dir / "label_counts.csv", index=False)
    print(f"\nWriting relabelled log (this takes a moment for large logs) ...")
    xes_path = write_dataframe_as_xes(relabeled, output_dir / "relabeled_log.xes")

    summary = {
        "step": "1 - preprocessing",
        "created": datetime.now().isoformat(timespec="seconds"),
        "pm4py_version": pm4py.__version__,
        "input_log": str(log_path),
        "selected_attribute": attribute,
        "label_format": f"<activity>{config.LABEL_SEPARATOR}<{attribute}>",
        "traces": n_traces,
        "events": len(df),
        "distinct_activities": n_activities,
        "distinct_attribute_values": n_values,
        "distinct_labels": n_labels,
        "events_without_value": n_missing,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Step 1 outputs written to: {output_dir}")
    return PreprocessingResult(attribute, output_dir, xes_path, n_labels)

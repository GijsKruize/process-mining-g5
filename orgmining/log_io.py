"""Reading and writing XES event logs with pm4py 2.2.16.

All pipeline steps work on a pandas DataFrame (one row per event), which is
easier to inspect and manipulate than pm4py's EventLog object. These helpers
do the conversion in both directions.
"""
from pathlib import Path

from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.importer.xes import importer as xes_importer


def read_xes_as_dataframe(path):
    """Load an XES file into a DataFrame with one row per event.

    Trace-level attributes are copied onto every event of the trace and get
    the prefix ``case:`` (e.g. ``case:LoanGoal``).
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Event log not found: {path}")
    log = xes_importer.apply(str(path))
    return log_converter.apply(log, variant=log_converter.Variants.TO_DATA_FRAME)


def write_dataframe_as_xes(df, path):
    """Write an event DataFrame back to XES (``case:`` columns become trace attributes)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
    xes_exporter.apply(log, str(path))
    return path

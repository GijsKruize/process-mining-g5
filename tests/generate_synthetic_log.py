"""Generate a tiny synthetic XES event log for testing the preprocessing pipeline.

Roughly 5 traces, 6 distinct activities, 3 resources, with one event that has
a missing resource so the missing-value handling path can be exercised.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.objects.log.obj import Event, EventLog, Trace

RESOURCES = ["User_1", "User_2", "User_3"]

# 6 distinct activities across 5 traces of varying length.
TRACE_DEFS = [
    ["A_Submitted", "A_Accepted", "W_Complete", "O_Sent"],
    ["A_Submitted", "A_Accepted", "A_Denied"],
    ["A_Submitted", "W_Complete", "O_Sent", "A_Cancelled"],
    ["A_Submitted", "A_Accepted", "W_Complete"],
    ["A_Submitted", "A_Denied"],
]

# (trace_index, step_index) whose org:resource is left empty to simulate missing data.
MISSING_RESOURCE_EVENTS = {(1, 1)}


def build_synthetic_log() -> EventLog:
    """Build a small in-memory EventLog."""
    log = EventLog()
    base_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for case_idx, activities in enumerate(TRACE_DEFS):
        trace = Trace()
        trace.attributes["concept:name"] = f"case_{case_idx + 1}"
        for step, activity in enumerate(activities):
            event = Event()
            event["concept:name"] = activity
            if (case_idx, step) in MISSING_RESOURCE_EVENTS:
                event["org:resource"] = ""
            else:
                event["org:resource"] = RESOURCES[(case_idx + step) % len(RESOURCES)]
            event["time:timestamp"] = base_time + timedelta(hours=case_idx, minutes=step * 10)
            trace.append(event)
        log.append(trace)
    return log


def write_synthetic_log(path: Path) -> None:
    """Build the synthetic log and export it to *path* as XES."""
    log = build_synthetic_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    xes_exporter.apply(log, str(path))


if __name__ == "__main__":
    write_synthetic_log(Path(__file__).parent / "data" / "synthetic_log.xes")
    print("Wrote synthetic log to tests/data/synthetic_log.xes")

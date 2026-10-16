"""Unit tests for step 1 on a tiny hand-made log.

Run from the project root:  python -m unittest discover tests -v
"""
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from orgmining import config
from orgmining.log_io import read_xes_as_dataframe, write_dataframe_as_xes
from orgmining.preprocessing import EventLogPreprocessor


def tiny_log():
    """Two traces in the style of BPI 2017; one event has no resource."""
    return pd.DataFrame({
        "case:concept:name": ["c1", "c1", "c1", "c2", "c2"],
        "case:LoanGoal": ["Car", "Car", "Car", "Home improvement", "Home improvement"],
        "concept:name": ["A-Submitted", "W-Validate application", "A-Denied",
                         "A-Submitted", "A-Denied"],
        "org:resource": ["User_1", "User_2", None, "User_1", "User_2"],
        "time:timestamp": pd.to_datetime([
            "2016-01-01 10:00", "2016-01-01 11:00", "2016-01-01 12:00",
            "2016-01-02 10:00", "2016-01-02 11:00"], utc=True),
    })


class DescribeAttributesTest(unittest.TestCase):
    def test_lists_every_column_with_its_level(self):
        overview = EventLogPreprocessor(tiny_log()).overview.set_index("attribute")
        self.assertEqual(len(overview), 5)
        self.assertEqual(overview.loc["case:LoanGoal", "level"], "trace")
        self.assertEqual(overview.loc["org:resource", "level"], "event")
        self.assertEqual(overview.loc["org:resource", "distinct_values"], 2)
        self.assertEqual(overview.loc["org:resource", "filled_pct"], 80.0)
        self.assertFalse(overview.loc["concept:name", "selectable"])


class SelectAttributeTest(unittest.TestCase):
    def setUp(self):
        self.preprocessor = EventLogPreprocessor(tiny_log())

    def test_accepts_name_and_number(self):
        self.assertEqual(self.preprocessor.validate_attribute(" org:resource "), "org:resource")
        number = str(list(self.preprocessor.overview["attribute"]).index("org:resource") + 1)
        self.assertEqual(self.preprocessor.validate_attribute(number), "org:resource")

    def test_rejects_unknown_and_non_selectable(self):
        for bad_choice in ("department", "99", "concept:name"):
            with self.assertRaises(ValueError):
                self.preprocessor.validate_attribute(bad_choice)

    def test_asks_again_after_invalid_answer(self):
        answers = iter(["department", "org:resource"])
        chosen = self.preprocessor.ask_for_attribute(input_fn=lambda prompt: next(answers))
        self.assertEqual(chosen, "org:resource")


class RelabelEventsTest(unittest.TestCase):
    def setUp(self):
        self.preprocessor = EventLogPreprocessor(tiny_log())

    def test_labels_are_activity_underscore_value(self):
        relabeled = self.preprocessor.relabel_events("org:resource")
        self.assertEqual(list(relabeled[config.ACTIVITY_KEY]), [
            "A-Submitted_User_1",
            "W-Validate-application_User_2",   # whitespace replaced for BIG
            "A-Denied_UNKNOWN",                # missing value made explicit
            "A-Submitted_User_1",
            "A-Denied_User_2",
        ])
        self.assertEqual(relabeled[config.ORIGINAL_ACTIVITY_KEY].iloc[1], "W-Validate application")
        self.assertEqual(relabeled[config.ATTRIBUTE_VALUE_KEY].iloc[0], "User_1")

    def test_original_log_is_not_modified(self):
        self.preprocessor.relabel_events("org:resource")
        self.assertEqual(self.preprocessor.event_log[config.ACTIVITY_KEY].iloc[0], "A-Submitted")

    def test_trace_attribute_can_be_selected(self):
        relabeled = self.preprocessor.relabel_events("case:LoanGoal")
        self.assertEqual(relabeled[config.ACTIVITY_KEY].iloc[3], "A-Submitted_Home-improvement")

    def test_label_counts(self):
        counts = EventLogPreprocessor.summarise_labels(
            self.preprocessor.relabel_events("org:resource"))
        self.assertEqual(len(counts), 4)
        self.assertEqual(counts.iloc[0]["label"], "A-Submitted_User_1")
        self.assertEqual(counts.iloc[0]["events"], 2)


class RunPreprocessingTest(unittest.TestCase):
    def test_end_to_end_writes_readable_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            log_path = write_dataframe_as_xes(tiny_log(), tmp / "tiny.xes")
            preprocessor = EventLogPreprocessor.from_xes(log_path, tmp / "out")
            result = preprocessor.run("org:resource")

            self.assertEqual(result.output_dir.name, "org_resource")
            for name in ("attributes_overview.csv", "label_counts.csv",
                         "relabeled_log.xes", "summary.json"):
                self.assertTrue((result.output_dir / name).is_file(), name)

            reloaded = read_xes_as_dataframe(result.relabeled_log_path)
            self.assertIn("A-Denied_UNKNOWN", set(reloaded[config.ACTIVITY_KEY]))
            self.assertEqual(reloaded[config.CASE_ID_KEY].nunique(), 2)


if __name__ == "__main__":
    unittest.main()

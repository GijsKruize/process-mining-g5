"""Project-wide constants: file locations and the XES attribute keys we rely on.

Keeping these in one place means a team member who renames a folder or works
with a different log only has to change this file.
"""
from pathlib import Path

# --- Locations -------------------------------------------------------------
# All paths are derived from the location of this file, never hard-coded, so
# the project runs unchanged on any machine. The dataset folder is not in git;
# see README.md for where to put it.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "datasets_group5_mining_organizational_patterns"
DEFAULT_LOG_PATH = DATASET_DIR / "BPI2017Denied(3).xes"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
STEP1_OUTPUT_DIR = OUTPUT_DIR / "step1_preprocessing"


def display_path(path):
    """Path relative to the project root for messages and output files.

    Keeps machine-specific parts such as 'C:/Users/<name>/...' out of the
    terminal output and out of files that are shared with the team.
    """
    path = Path(path).resolve()
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:  # outside the project, e.g. a temporary test folder
        return path.as_posix()

# --- Standard XES keys (as they appear in a pm4py DataFrame) ----------------
ACTIVITY_KEY = "concept:name"        # event label; step 1 overwrites this
CASE_ID_KEY = "case:concept:name"    # trace identifier
TIMESTAMP_KEY = "time:timestamp"
TRACE_ATTRIBUTE_PREFIX = "case:"     # pm4py prefixes trace-level attributes with this

# --- Columns added by step 1 ------------------------------------------------
# The new label "<activity>_<value>" cannot be split back reliably, because
# attribute values may contain "_" themselves (e.g. "User_1"). So both parts
# are also kept as separate columns for the later steps and the evaluation.
ORIGINAL_ACTIVITY_KEY = "original_activity"
ATTRIBUTE_VALUE_KEY = "selected_attribute_value"

# Attributes that are listed to the user but cannot be selected: fusing the
# activity with itself, the case id or a timestamp gives no resource-task view.
NON_SELECTABLE_ATTRIBUTES = (ACTIVITY_KEY, CASE_ID_KEY, TIMESTAMP_KEY)

# Value used when an event has no value for the selected attribute. This is
# the same default the BPI 2017 log declares for its global attributes.
MISSING_VALUE = "UNKNOWN"

# Separator between activity and attribute value in the new label, as the
# assignment prescribes: activity_selectedAttribute.
LABEL_SEPARATOR = "_"

"""Non-interactive tests for the preprocessing pipeline, using a tiny synthetic log."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

import pandas as pd
import pytest

import preprocess as pp
from generate_synthetic_log import build_synthetic_log, write_synthetic_log


def make_fake_input(responses: list[str]) -> Callable[[str], str]:
    """Return an input_func that yields *responses* in order, ignoring the prompt."""
    it: Iterator[str] = iter(responses)

    def fake_input(_prompt: str) -> str:
        return next(it)

    return fake_input


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    log = build_synthetic_log()
    return pp.EventLogRepository.to_dataframe(log)


# ---------------------------------------------------------------------------
# Unit tests for individual collaborator classes
# ---------------------------------------------------------------------------


def test_synthetic_log_shape(synthetic_df: pd.DataFrame) -> None:
    stats = pp.LogReporter.summarize(synthetic_df)
    assert stats["n_traces"] == 5
    assert stats["n_activities"] == 6
    assert stats["n_events"] == sum(len(t) for t in build_synthetic_log())


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A Submitted", "A_Submitted"),
        ("R,1", "R_1"),
        ('User "1"', "User_1"),
        ("<init>", "init"),
        ("", pp.UNKNOWN_LABEL),
        (None, pp.UNKNOWN_LABEL),
    ],
)
def test_sanitize_label_part(raw: object, expected: str) -> None:
    assert pp.ActivityRelabeler.sanitize_label_part(raw) == expected


def test_count_missing(synthetic_df: pd.DataFrame) -> None:
    handler = pp.MissingValueHandler()
    assert handler.count_missing(synthetic_df, "org:resource") == 1


def test_apply_missing_strategy_drop(synthetic_df: pd.DataFrame) -> None:
    handler = pp.MissingValueHandler()
    n_before = len(synthetic_df)
    dropped = handler.apply(synthetic_df, "org:resource", "drop")
    assert len(dropped) == n_before - 1
    assert handler.count_missing(dropped, "org:resource") == 0


def test_apply_missing_strategy_unknown(synthetic_df: pd.DataFrame) -> None:
    handler = pp.MissingValueHandler()
    filled = handler.apply(synthetic_df, "org:resource", "unknown")
    assert len(filled) == len(synthetic_df)
    assert (filled["org:resource"] == pp.UNKNOWN_LABEL).sum() == 1


def test_apply_missing_strategy_rejects_unknown_strategy(synthetic_df: pd.DataFrame) -> None:
    handler = pp.MissingValueHandler()
    with pytest.raises(ValueError):
        handler.apply(synthetic_df, "org:resource", "not-a-strategy")


def test_prompt_choose_attribute_by_number_and_reprompt(synthetic_df: pd.DataFrame) -> None:
    reporter = pp.LogReporter()
    columns_info = reporter.describe_columns(synthetic_df)
    selector = pp.AttributeSelector()
    fake = make_fake_input(["not-a-column", "999", "2"])
    result = selector.choose(columns_info, input_func=fake)
    assert result == columns_info[1].name


def test_prompt_choose_attribute_by_name(synthetic_df: pd.DataFrame) -> None:
    reporter = pp.LogReporter()
    columns_info = reporter.describe_columns(synthetic_df)
    selector = pp.AttributeSelector()
    fake = make_fake_input(["org:resource"])
    assert selector.choose(columns_info, input_func=fake) == "org:resource"


def test_prompt_missing_strategy_reprompt() -> None:
    handler = pp.MissingValueHandler()
    fake = make_fake_input(["maybe", "drop"])
    assert handler.prompt_strategy(3, input_func=fake) == "drop"


def test_prompt_missing_strategy_skipped_when_none_missing() -> None:
    def fail_if_called(_prompt: str) -> str:
        raise AssertionError("should not prompt when there is nothing missing")

    handler = pp.MissingValueHandler()
    assert handler.prompt_strategy(0, input_func=fail_if_called) == "unknown"


def test_relabel_labels(synthetic_df: pd.DataFrame) -> None:
    handler = pp.MissingValueHandler()
    relabeler = pp.ActivityRelabeler()
    df_handled = handler.apply(synthetic_df, "org:resource", "unknown")
    df_after = relabeler.relabel(df_handled, "org:resource")
    assert df_after[pp.ACTIVITY_KEY].iloc[0] == "A_Submitted_User_1"
    assert (df_after[pp.ACTIVITY_KEY].str.contains(f"_{pp.UNKNOWN_LABEL}$")).sum() == 1
    assert df_after[pp.ACTIVITY_KEY].nunique() >= synthetic_df[pp.ACTIVITY_KEY].nunique()


def test_pipeline_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "custom_config.yaml"
    config_path.write_text(
        "input_path: some_dir\noutput_dir: some_output\nn_examples: 5\ntop_n_labels: 7\n"
    )
    config = pp.PipelineConfig.from_yaml(config_path)
    assert config.input_path == Path("some_dir")
    assert config.output_dir == Path("some_output")
    assert config.n_examples == 5
    assert config.top_n_labels == 7


def test_pipeline_config_from_yaml_partial_uses_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "partial_config.yaml"
    config_path.write_text("output_dir: only_output_set\n")
    config = pp.PipelineConfig.from_yaml(config_path)
    assert config.input_path == pp.PipelineConfig().input_path
    assert config.output_dir == Path("only_output_set")


# ---------------------------------------------------------------------------
# End-to-end, non-interactive run of the whole pipeline via main()
# ---------------------------------------------------------------------------


def test_full_pipeline_end_to_end(tmp_path: Path) -> None:
    xes_path = tmp_path / "synthetic_log.xes"
    write_synthetic_log(xes_path)

    output_dir = tmp_path / "output"
    fake = make_fake_input(["org:resource", "unknown"])

    pp.main(argv=[str(xes_path), "--output-dir", str(output_dir)], input_func=fake)

    xes_out = output_dir / "relabeled_log.xes"
    csv_out = output_dir / "relabeled_log.csv"
    assert xes_out.exists()
    assert csv_out.exists()

    repository = pp.EventLogRepository()
    reimported = repository.load(xes_out)
    reimported_df = repository.to_dataframe(reimported)
    assert reimported_df[pp.ACTIVITY_KEY].nunique() >= 6
    assert reimported_df[pp.CASE_KEY].nunique() == 5


def test_missing_input_file_raises_clear_error(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.xes"
    with pytest.raises(FileNotFoundError, match="not found"):
        pp.EventLogRepository().load(missing)


def test_empty_data_dir_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No .xes file"):
        pp.EventLogRepository().load(tmp_path)

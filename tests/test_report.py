"""The audit-trail invariant: nothing changes without a corresponding record."""

from __future__ import annotations

import json
from pathlib import Path

from _fixtures import _write_csv
from messy_table import ActionKind, clean


def test_disguised_nulls_count_is_exact(built_fixtures: dict[str, Path]) -> None:
    # f13 has exactly four null tokens: '-', 'N/A', '#REF!', '#DIV/0!'.
    result = clean(built_fixtures["f13_disguised_nulls.csv"])
    assert result.report.summary()["null_normalized"] == 4


def test_number_parse_count_is_exact(built_fixtures: dict[str, Path]) -> None:
    # f13: id col (1,2,3) = 3; valor col leaves only '10' after nulling = 1.
    result = clean(built_fixtures["f13_disguised_nulls.csv"])
    assert result.report.summary()["number_parsed"] == 4


def test_invariant_every_changed_null_is_recorded(tmp_path: Path) -> None:
    # Read raw, count tokens that WILL become null, compare to the report.
    raw = "a,b\n-,1\nN/A,2\nok,3\n"
    path = _write_csv(tmp_path / "inv.csv", raw)
    result = clean(path)
    recorded = sum(a.count for a in result.report.of_kind(ActionKind.NULL_NORMALIZED))
    assert recorded == 2  # '-' and 'N/A'


def test_examples_are_bounded(tmp_path: Path) -> None:
    from messy_table.report import EXAMPLE_CAP

    rows = "\n".join("-" for _ in range(50))
    path = _write_csv(tmp_path / "many.csv", f"col\n{rows}\n")
    result = clean(path)
    null_actions = result.report.of_kind(ActionKind.NULL_NORMALIZED)
    assert null_actions[0].count == 50
    assert len(null_actions[0].examples) <= EXAMPLE_CAP


def test_report_json_has_summary_and_actions(built_fixtures: dict[str, Path]) -> None:
    result = clean(built_fixtures["f02_title_and_blank.xlsx"])
    payload = json.loads(result.report.to_json())
    assert "summary" in payload
    assert isinstance(payload["actions"], list)

"""Acceptance criterion #1: every fixture cleans to its gabarito."""

from __future__ import annotations

from pathlib import Path

import pytest

from _fixtures import FIXTURES, Fixture
from messy_table import clean


@pytest.mark.parametrize("fx", FIXTURES, ids=[f.name for f in FIXTURES])
def test_fixture_matches_gabarito(fx: Fixture, built_fixtures: dict[str, Path]) -> None:
    result = clean(built_fixtures[fx.name], config=fx.config)

    assert result.data == fx.expected_data, fx.notes
    assert [(c.name, c.dtype) for c in result.columns] == fx.expected_columns, fx.notes


@pytest.mark.parametrize("fx", FIXTURES, ids=[f.name for f in FIXTURES])
def test_fixture_report_roundtrips_to_json(fx: Fixture, built_fixtures: dict[str, Path]) -> None:
    result = clean(built_fixtures[fx.name], config=fx.config)
    # The whole result, report included, must be JSON-serialisable.
    payload = result.to_json()
    assert isinstance(payload, str) and payload

"""Direct unit tests for branches awkward to reach end-to-end."""

from __future__ import annotations

import datetime as dt

import pytest

from messy_table import AmbiguityError, Config
from messy_table.context import Context
from messy_table.grid import Epoch, Grid, MergedRange, SourceInfo
from messy_table.report import ColumnInfo
from messy_table.transformers.dates import convert_dates
from messy_table.transformers.types import finalize_types


def _ctx(names: list[str], **cfg: object) -> Context:
    ctx = Context(config=Config(**cfg), source=SourceInfo("t", "xlsx"))
    ctx.column_names = names
    return ctx


def test_convert_dates_via_number_format() -> None:
    # Numeric value + date number-format, no date hint in the name → F4 fires.
    grid = Grid(
        values=[[45123], [45124]],
        source=SourceInfo("t", "xlsx", epoch=Epoch.E1900),
        number_formats={(0, 0): "dd/mm/yyyy", (1, 0): "dd/mm/yyyy"},
    )
    ctx = _ctx(["x"])
    convert_dates(grid, ctx)
    assert grid.values[0][0] == dt.date(2023, 7, 16)
    assert grid.values[1][0] == dt.date(2023, 7, 17)


def test_convert_dates_name_hint_below_threshold_warns() -> None:
    grid = Grid(values=[[45123]], source=SourceInfo("t", "xlsx", epoch=Epoch.E1900))
    ctx = _ctx(["data_venda"], confidence_threshold=0.8)  # name hint conf 0.7 < 0.8
    convert_dates(grid, ctx)
    assert any("serial dates" in w.message for w in ctx.warnings)


def test_convert_dates_strict_raises() -> None:
    grid = Grid(values=[[45123]], source=SourceInfo("t", "xlsx", epoch=Epoch.E1900))
    ctx = _ctx(["data_venda"], confidence_threshold=0.8, strict=True)
    with pytest.raises(AmbiguityError):
        convert_dates(grid, ctx)


def test_finalize_promotes_date_to_datetime() -> None:
    grid = Grid(
        values=[[dt.date(2024, 1, 1)], [dt.datetime(2024, 1, 2, 10, 30)]],
        source=SourceInfo("t", "xlsx"),
    )
    ctx = _ctx(["when"])
    cols = finalize_types(grid, ctx, originals=["when"])
    assert cols == [ColumnInfo("when", "when", "datetime", 0, 2)]
    assert grid.values[0][0] == dt.datetime(2024, 1, 1, 0, 0)


def test_finalize_native_bool_column() -> None:
    grid = Grid(values=[[True], [False], [None]], source=SourceInfo("t", "xlsx"))
    ctx = _ctx(["flag"])
    cols = finalize_types(grid, ctx, originals=["flag"])
    assert cols[0].dtype == "bool"
    assert cols[0].null_count == 1


def test_grid_helpers() -> None:
    grid = Grid(
        values=[[1, None], [3, 4]],
        source=SourceInfo("t", "xlsx"),
        number_formats={(1, 1): "0.00"},
        is_date={(0, 0)},
        merged_ranges=[MergedRange(0, 0, 1, 0)],
    )
    assert grid.column(0) == [1, 3]
    assert grid.cell(99, 99) is None
    assert grid.is_date_cell(0, 0) is True
    assert grid.number_format(1, 1) == "0.00"
    assert MergedRange(0, 0, 1, 0).cells() == [(0, 0), (1, 0)]


def test_ambiguity_error_without_suggestion() -> None:
    err = AmbiguityError("plain message")
    assert str(err) == "plain message"
    assert err.suggestion is None

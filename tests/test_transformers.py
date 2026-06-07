"""Transformer behaviour at the unit and end-to-end level."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.utils.datetime import CALENDAR_MAC_1904

from _fixtures import _write_csv, _write_xlsx
from messy_table import AmbiguityError, Config, clean
from messy_table.context import Context
from messy_table.grid import Epoch, SourceInfo
from messy_table.transformers.dates import _serial_to_date
from messy_table.transformers.header_names import normalize_headers


def _ctx() -> Context:
    return Context(config=Config(), source=SourceInfo(origin="t", kind="csv"))


def test_header_slugify_dedupe_empty_leadingdigit() -> None:
    ctx = _ctx()
    pairs = normalize_headers(["Valor (R$)", "2024", "", "Nome", "Nome"], ctx)
    names = [name for _, name in pairs]
    assert names == ["valor_r", "col_2024", "column_3", "nome", "nome_2"]
    assert ctx.column_names == names


def test_null_values_extra(tmp_path: Path) -> None:
    path = _write_csv(tmp_path / "n.csv", "id,status\n1,s/i\n2,ok\n")
    result = clean(path, config=Config(null_values_extra=["s/i"]))
    assert result.data == [{"id": 1, "status": None}, {"id": 2, "status": "ok"}]


def test_forced_locale_en_us(tmp_path: Path) -> None:
    # Values are ambiguous alone, but forcing en-US makes '.' the decimal point.
    path = _write_csv(tmp_path / "num.csv", "x\n1.5\n2.75\n")
    result = clean(path, config=Config(locale="en_US"))
    assert [row["x"] for row in result.data] == [1.5, 2.75]


def test_ambiguous_numbers_strict_raises(tmp_path: Path) -> None:
    # Mixed conventions in one column → 50/50 vote → below threshold.
    path = _write_csv(tmp_path / "amb.csv", "x\n1.5\n2,5\n")
    with pytest.raises(AmbiguityError) as exc:
        clean(path, config=Config(strict=True))
    assert exc.value.suggestion is not None
    assert "locale" in str(exc.value)


def test_ambiguous_numbers_permissive_warns(tmp_path: Path) -> None:
    path = _write_csv(tmp_path / "amb.csv", "x\n1.5\n2,5\n")
    result = clean(path, config=Config(strict=False))
    assert any("ambiguous number" in w.message for w in result.warnings)


def test_serial_dates_both_epochs() -> None:
    assert _serial_to_date(44927, Epoch.E1900) == dt.date(2023, 1, 1)
    # The 1904 serial of the same day is exactly 1462 lower.
    assert _serial_to_date(44927 - 1462, Epoch.E1904) == dt.date(2023, 1, 1)
    assert _serial_to_date(45123.5, Epoch.E1900) == dt.datetime(2023, 7, 16, 12, 0)


def test_serial_dates_1904_end_to_end(tmp_path: Path) -> None:
    wb = Workbook()
    wb.epoch = CALENDAR_MAC_1904
    ws = wb.active
    ws.append(["item", "data"])
    ws.append(["X", 44927 - 1462])
    path = tmp_path / "d1904.xlsx"
    wb.save(path)
    result = clean(path)
    assert result.data == [{"item": "X", "data": dt.date(2023, 1, 1)}]


def test_plain_numbers_not_converted_without_hint(tmp_path: Path) -> None:
    # 'ano' is not a date hint and values are out of serial range → stay numeric.
    path = _write_csv(tmp_path / "y.csv", "ano,n\n2023,5\n2024,6\n")
    result = clean(path)
    assert result.data == [{"ano": 2023, "n": 5}, {"ano": 2024, "n": 6}]


def test_mixed_column_kept_as_str_with_warning(tmp_path: Path) -> None:
    # 3/4 numeric → parsed to ints, leaving one real string → genuinely mixed.
    path = _write_csv(tmp_path / "m.csv", "v\n10\n20\n30\nhello\n")
    result = clean(path)
    assert [c.dtype for c in result.columns] == ["str"]
    assert result.data == [{"v": "10"}, {"v": "20"}, {"v": "30"}, {"v": "hello"}]
    assert any("mixes types" in w.message for w in result.warnings)


def test_merged_fill_records_actions(tmp_path: Path) -> None:
    from messy_table import ActionKind

    path = _write_xlsx(
        tmp_path / "mf.xlsx",
        [["r", "p"], ["Sul", "A"], [None, "B"], [None, "C"]],
        merges=("A2:A4",),
    )
    result = clean(path)
    assert [row["r"] for row in result.data] == ["Sul", "Sul", "Sul"]
    filled = result.report.of_kind(ActionKind.MERGED_FILLED)
    assert filled and filled[0].count == 2  # two non-anchor cells filled

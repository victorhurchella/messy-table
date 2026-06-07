"""Detector behaviour: forced header, headerless data, trailing-junk trimming."""

from __future__ import annotations

from pathlib import Path

from _fixtures import _write_csv, _write_xlsx
from messy_table import ActionKind, Config, clean


def test_forced_header_index(tmp_path: Path) -> None:
    # Two preamble rows, then the real header at index 2.
    text = "garbage,stuff\nmore,junk\nid,name\n1,Ana\n2,Beto\n"
    path = _write_csv(tmp_path / "h.csv", text)
    result = clean(path, config=Config(header=2))
    assert result.data == [{"id": 1, "name": "Ana"}, {"id": 2, "name": "Beto"}]


def test_headerless_autodetect(tmp_path: Path) -> None:
    path = _write_csv(tmp_path / "nohdr.csv", "10,20,30\n40,50,60\n70,80,90\n")
    result = clean(path)
    assert [c.name for c in result.columns] == ["column_1", "column_2", "column_3"]
    assert any("no header" in w.message for w in result.warnings)


def test_table_start_skips_title(tmp_path: Path) -> None:
    path = _write_xlsx(
        tmp_path / "t.xlsx",
        [["Big Title"], [None], ["a", "b"], [1, 2]],
    )
    result = clean(path)
    assert result.data == [{"a": 1, "b": 2}]
    starts = result.report.of_kind(ActionKind.TABLE_START)
    assert starts and "skipped" in (starts[0].detail or "")


def test_all_null_trailing_column_keeps_data(tmp_path: Path) -> None:
    # Regression: a fully-empty trailing column must not make every data row look
    # sparse and get trimmed as junk (silent total data loss).
    path = _write_csv(tmp_path / "deadcol.csv", "id,nota\n1,\n2,\n3,\n")
    result = clean(path)
    assert result.data == [
        {"id": 1, "nota": None},
        {"id": 2, "nota": None},
        {"id": 3, "nota": None},
    ]


def test_all_null_middle_column_keeps_data(tmp_path: Path) -> None:
    path = _write_csv(tmp_path / "deadmid.csv", "a,dead,b\n1,,9\n2,,8\n")
    result = clean(path)
    assert result.data == [{"a": 1, "dead": None, "b": 9}, {"a": 2, "dead": None, "b": 8}]


def test_sparse_last_data_row_kept_when_column_is_live(tmp_path: Path) -> None:
    # A real last row missing one of several values is data, not junk.
    path = _write_csv(tmp_path / "sparse.csv", "a,b,c\n1,2,3\n4,5,6\n7,8,\n")
    result = clean(path)
    assert len(result.data) == 3
    assert result.data[-1] == {"a": 7, "b": 8, "c": None}


def test_table_end_trims_total_and_footnote(tmp_path: Path) -> None:
    path = _write_xlsx(
        tmp_path / "e.xlsx",
        [["p", "v"], ["A", 1], ["B", 2], ["TOTAL", 3], ["Fonte: ACME", None]],
    )
    result = clean(path)
    assert result.data == [{"p": "A", "v": 1}, {"p": "B", "v": 2}]
    ends = result.report.of_kind(ActionKind.TABLE_END)
    assert ends and "trimmed" in (ends[0].detail or "")

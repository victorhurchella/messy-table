"""CleanResult surface: to_pandas (and its absence), to_json, repr."""

from __future__ import annotations

import builtins
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from messy_table import clean


def test_to_pandas_returns_dataframe(built_fixtures: dict[str, Path]) -> None:
    pd = pytest.importorskip("pandas")
    result = clean(built_fixtures["f01_clean_baseline.csv"])
    df = result.to_pandas()
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["name", "age", "active"]
    assert len(df) == 2


def test_to_pandas_without_pandas_raises_clear_error(
    built_fixtures: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = clean(built_fixtures["f01_clean_baseline.csv"])
    real_import: Callable[..., Any] = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pandas":
            raise ImportError("No module named 'pandas'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match=r"messy-table\[pandas\]"):
        result.to_pandas()


def test_to_json_is_valid_json(built_fixtures: dict[str, Path]) -> None:
    result = clean(built_fixtures["f09_serial_dates.xlsx"])
    payload = json.loads(result.to_json())
    assert payload["data"][0]["data_venda"] == "2023-07-16"  # date → ISO string
    assert payload["columns"][0]["name"] == "item"
    assert "report" in payload and "warnings" in payload


def test_repr_is_informative(built_fixtures: dict[str, Path]) -> None:
    result = clean(built_fixtures["f01_clean_baseline.csv"])
    text = repr(result)
    assert "rows=2" in text and "cols=3" in text

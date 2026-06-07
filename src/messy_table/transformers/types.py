"""F6 — per-column type inference and final coercion.

By the time this runs, nulls are ``None``, numeric strings are real numbers, and
serial dates are ``date``/``datetime``. This stage looks at each column's surviving
non-null values and commits to one dtype:

* all dates → ``date`` (or ``datetime`` if any carry a time);
* all integers → ``int``; any fractional → ``float``;
* all boolean (native or text tokens) → ``bool``;
* anything genuinely mixed → ``str`` (lossless fallback, with a warning).

The "95% numeric + a few N/A" case from the spec resolves to a clean numeric
column here, because F7 already turned the ``N/A`` cells into nulls.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from messy_table.context import Context
from messy_table.grid import Grid
from messy_table.report import ActionKind, ColumnInfo
from messy_table.util import is_blank, parse_bool


def finalize_types(grid: Grid, ctx: Context, originals: list[str | None]) -> list[ColumnInfo]:
    columns: list[ColumnInfo] = []
    names = ctx.column_names
    for c in range(grid.ncols):
        column = names[c] if c < len(names) else f"column_{c + 1}"
        original = originals[c] if c < len(originals) else None
        values = [grid.values[r][c] for r in range(grid.nrows)]
        dtype = _infer_and_coerce(values, grid, c, column, ctx)
        for r in range(grid.nrows):
            grid.values[r][c] = values[r]
        null_count = sum(1 for v in values if is_blank(v))
        columns.append(
            ColumnInfo(
                original_name=original,
                name=column,
                dtype=dtype,
                null_count=null_count,
                total=grid.nrows,
            )
        )
    return columns


def _infer_and_coerce(values: list[Any], grid: Grid, col: int, column: str, ctx: Context) -> str:
    indexed = [(r, v) for r, v in enumerate(values) if not is_blank(v)]
    if not indexed:
        return "str"

    kinds = {_python_kind(v) for _, v in indexed}

    if kinds <= {"date", "datetime"}:
        return _coerce_dates(values, indexed, kinds, column, ctx)
    if kinds == {"int"}:
        return "int"
    if kinds <= {"int", "float"}:
        return "float"
    if _all_boolean(indexed):
        _coerce_booleans(values, indexed, grid, col, column, ctx)
        return "bool"
    return _coerce_strings(values, indexed, column, ctx)


def _python_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, dt.datetime):
        return "datetime"
    if isinstance(value, dt.date):
        return "date"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _coerce_dates(
    values: list[Any],
    indexed: list[tuple[int, Any]],
    kinds: set[str],
    column: str,
    ctx: Context,
) -> str:
    if "datetime" not in kinds:
        return "date"
    # Promote bare dates to datetime so the column is uniform.
    for r, value in indexed:
        if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
            values[r] = dt.datetime(value.year, value.month, value.day)
            ctx.report.record(
                ActionKind.TYPE_COERCED,
                "date->datetime",
                column=column,
                row=r,
                original=value,
                final=values[r],
            )
    return "datetime"


def _all_boolean(indexed: list[tuple[int, Any]]) -> bool:
    for _, value in indexed:
        if isinstance(value, bool):
            continue
        if isinstance(value, str) and parse_bool(value) is not None:
            continue
        return False
    return True


def _coerce_booleans(
    values: list[Any],
    indexed: list[tuple[int, Any]],
    grid: Grid,
    col: int,
    column: str,
    ctx: Context,
) -> None:
    for r, value in indexed:
        if isinstance(value, bool):
            continue
        parsed = parse_bool(value) if isinstance(value, str) else None
        if parsed is not None:
            values[r] = parsed
            ctx.report.record(
                ActionKind.TYPE_COERCED,
                "bool",
                column=column,
                row=r,
                col=col,
                original=value,
                final=parsed,
            )


def _coerce_strings(
    values: list[Any], indexed: list[tuple[int, Any]], column: str, ctx: Context
) -> str:
    mixed = len({_python_kind(v) for _, v in indexed if _python_kind(v) != "str"}) > 0
    if mixed:
        ctx.warn(
            f"column {column!r} mixes types; kept as text to avoid data loss",
            column=column,
        )
    for r, value in indexed:
        text = value.strip() if isinstance(value, str) else str(value)
        if text != value:
            values[r] = text
            ctx.report.record(
                ActionKind.TYPE_COERCED,
                "to-str",
                column=column,
                row=r,
                original=value,
                final=text,
            )
    return "str"

"""Small, dependency-free primitives shared by detectors and transformers.

Everything here works on *raw* cell values — the values as the reader produced
them, before any cleaning. ``raw_category`` is the workhorse: a coarse type guess
used to reason about which rows are headers and which columns are numeric.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# Tokens recognised as boolean text in pt-BR and en-US (lower-cased, stripped).
_TRUE_TOKENS = frozenset({"true", "verdadeiro", "sim", "yes", "y", "v"})
_FALSE_TOKENS = frozenset({"false", "falso", "nao", "não", "no", "n", "f"})

_CURRENCY = ("r$", "us$", "$", "€", "£", "%")


def is_blank(value: Any) -> bool:
    """A cell is blank if it is ``None`` or whitespace-only text."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def filled_count(row: list[Any]) -> int:
    return sum(1 for v in row if not is_blank(v))


def row_filled_counts(
    rows: list[list[Any]], covered: set[tuple[int, int]] | None = None
) -> list[int]:
    """Filled-cell count per row, merge-aware. Hot path — kept tight.

    A cell counts as filled if it is non-blank, or (when ``covered`` is given) it
    belongs to a row-spanning merge. The no-merge case skips the per-cell set
    lookup entirely.
    """
    if not covered:
        return [
            sum(1 for v in row if v is not None and not (isinstance(v, str) and not v.strip()))
            for row in rows
        ]
    return [
        sum(
            1
            for c, v in enumerate(row)
            if (v is not None and not (isinstance(v, str) and not v.strip())) or (r, c) in covered
        )
        for r, row in enumerate(rows)
    ]


def merge_covered_cells(merged_ranges: list[Any]) -> set[tuple[int, int]]:
    """Cells belonging to a *row-spanning* merge (vertical or block-down).

    These cells read as ``None`` before unmerging but are structurally part of
    the table (a category merged down a column), so density-based detection must
    count them as filled. Purely *horizontal* merges (a one-row banner) are
    excluded on purpose — those are titles we want to stay sparse and skip.
    """
    covered: set[tuple[int, int]] = set()
    for m in merged_ranges:
        if m.max_row > m.min_row:
            for r in range(m.min_row, m.max_row + 1):
                for c in range(m.min_col, m.max_col + 1):
                    covered.add((r, c))
    return covered


def density_threshold(width: int, ratio: float) -> int:
    """Minimum filled cells for a row to count as table body.

    Single-column tables use a floor of 1; wider tables use a floor of 2 so a
    lone stray cell (a title) never reads as a data row.
    """
    if width <= 1:
        return 1
    import math

    return max(2, math.ceil(ratio * width))


def first_nonblank(row: list[Any]) -> Any:
    for v in row:
        if not is_blank(v):
            return v
    return None


def looks_like_number(text: str) -> bool:
    """Loose, locale-agnostic test: could this string be a number?

    Accepts grouped/decimal separators in either convention, optional sign,
    currency symbols and a trailing percent. Deliberately permissive — the
    number transformer does the real, locale-aware parsing later.
    """
    t = text.strip().lower()
    if not t:
        return False
    for sym in _CURRENCY:
        t = t.replace(sym, "")
    t = t.strip().replace(" ", "").replace("\u00a0", "").lstrip("+-")
    if not t or not any(c.isdigit() for c in t):
        return False
    return all(c.isdigit() or c in ".,'" for c in t)


def looks_like_bool(text: str) -> bool:
    t = text.strip().lower()
    return t in _TRUE_TOKENS or t in _FALSE_TOKENS


def parse_bool(text: str) -> bool | None:
    t = text.strip().lower()
    if t in _TRUE_TOKENS:
        return True
    if t in _FALSE_TOKENS:
        return False
    return None


def raw_category(value: Any) -> str:
    """Coarse category of a raw cell: blank | bool | number | datetime | text."""
    if is_blank(value):
        return "blank"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (dt.datetime, dt.date)):
        return "datetime"
    if isinstance(value, str):
        s = value.strip()
        if looks_like_bool(s):
            return "bool"
        if looks_like_number(s):
            return "number"
        return "text"
    return "text"

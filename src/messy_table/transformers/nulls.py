"""F7 — normalise disguised nulls.

Real spreadsheets spell "missing" a dozen ways: ``-``, ``N/A``, ``n/d``, the Excel
error literals (``#REF!``, ``#DIV/0!`` ...), or just whitespace. We map all of them
to ``None`` so downstream type inference sees clean, comparable nulls. The token
list is extensible via ``Config.null_values_extra``.

Comparison is case-insensitive and whitespace-trimmed; ``"  N/A "`` matches.
"""

from __future__ import annotations

from messy_table.context import Context
from messy_table.grid import Grid
from messy_table.report import ActionKind

# Built-in null tokens (already lower-cased, compared after .strip()).
DEFAULT_NULL_TOKENS: frozenset[str] = frozenset(
    {
        "",
        "-",
        "--",
        "---",
        "—",
        "n/a",
        "n.a.",
        "na",
        "n/d",
        "nd",
        "null",
        "none",
        "nil",
        "nan",
        "#n/a",
        "#ref!",
        "#div/0!",
        "#value!",
        "#name?",
        "#null!",
        "#num!",
        "#####",
    }
)


def normalize_nulls(grid: Grid, ctx: Context) -> None:
    null_tokens = DEFAULT_NULL_TOKENS | {t.strip().lower() for t in ctx.config.null_values_extra}
    names = ctx.column_names

    for r in range(grid.nrows):
        row = grid.values[r]
        for c, value in enumerate(row):
            if not isinstance(value, str):
                continue
            if value.strip().lower() in null_tokens:
                row[c] = None
                column = names[c] if c < len(names) else None
                ctx.report.record(
                    ActionKind.NULL_NORMALIZED,
                    "null-token",
                    column=column,
                    row=r,
                    col=c,
                    original=value,
                    final=None,
                )

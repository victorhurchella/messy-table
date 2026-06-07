"""F4 — Excel serial dates.

A properly date-formatted ``.xlsx`` cell already arrives as a ``datetime`` (openpyxl
converts it using the workbook epoch). The mess F4 fixes is the *other* case: a
column whose values are bare numbers like ``45123`` that are really dates — the
column was exported as General/number, or it came from a CSV.

Converting bare numbers is risky (``45123`` is also a perfectly good integer), so
we only do it when there is corroborating evidence:

* the cell's number format looks like a date, **or**
* the column name hints at a date (``data``, ``vencimento``, ``date`` ...),

*and* every value sits in a plausible serial range. Both Excel epochs (1900 with
its leap-year bug, and 1904) are handled via the epoch captured by the reader.
"""

from __future__ import annotations

import datetime as dt

from messy_table.context import Context
from messy_table.grid import Epoch, Grid
from messy_table.report import ActionKind

# Serial range roughly 1954-08-18 .. 2064-03-22 — wide enough for real data,
# narrow enough to avoid grabbing ordinary small integers.
SERIAL_MIN = 20_000
SERIAL_MAX = 60_000

_DATE_NAME_HINTS = (
    "data",
    "date",
    "vencimento",
    "emissao",
    "nascimento",
    "competencia",
    "periodo",
    "dt_",
    "_dt",
    "created",
    "updated",
    "dia",
)
_EPOCH_BASE = {
    Epoch.E1900: dt.datetime(1899, 12, 30),  # offset absorbs Excel's 1900 leap bug
    Epoch.E1904: dt.datetime(1904, 1, 1),
}


def convert_dates(grid: Grid, ctx: Context) -> None:
    names = ctx.column_names
    epoch = grid.source.epoch
    for c in range(grid.ncols):
        column = names[c] if c < len(names) else None
        numeric = [
            (r, v)
            for r in range(grid.nrows)
            if isinstance((v := grid.values[r][c]), (int, float)) and not isinstance(v, bool)
        ]
        if not numeric:
            continue
        if not all(SERIAL_MIN <= v <= SERIAL_MAX for _, v in numeric):
            continue

        fmt_is_date = any(_is_date_format(grid.number_format(r, c)) for r, _ in numeric)
        name_is_date = _name_suggests_date(column)
        if not (fmt_is_date or name_is_date):
            continue

        confidence = 0.9 if fmt_is_date else 0.7
        if confidence < ctx.config.confidence_threshold:
            ctx.ambiguous(
                f"column {column!r} may be serial dates",
                suggestion="rename the column or pre-format it as a date in the source",
                column=column,
                confidence=confidence,
            )
        for r, serial in numeric:
            converted = _serial_to_date(serial, epoch)
            grid.values[r][c] = converted
            ctx.report.record(
                ActionKind.DATE_CONVERTED,
                f"serial-{epoch.value}",
                column=column,
                row=r,
                col=c,
                original=serial,
                final=converted,
                confidence=confidence,
            )


def _serial_to_date(serial: int | float, epoch: Epoch) -> dt.date | dt.datetime:
    base = _EPOCH_BASE[epoch]
    moment = base + dt.timedelta(days=float(serial))
    if float(serial).is_integer() and moment.time() == dt.time(0, 0):
        return moment.date()
    return moment


def _is_date_format(number_format: str | None) -> bool:
    if not number_format:
        return False
    fmt = number_format.lower()
    if any(token in fmt for token in ("yy", "dd", "mmm")):
        return True
    return "m" in fmt and "d" in fmt


def _name_suggests_date(column: str | None) -> bool:
    if not column:
        return False
    return any(hint in column for hint in _DATE_NAME_HINTS)

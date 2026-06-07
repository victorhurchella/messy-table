"""F5 — localised numbers, inferred at the **column** level.

``1.234,56`` (pt-BR/EU) and ``1,234.56`` (en-US) are indistinguishable cell by
cell, but a *column* almost always speaks one convention. So we vote across the
column:

* a value with both separators → the **last** one is the decimal point;
* a value with one separator → it is a thousands group only if it splits the
  number into clean 3-digit runs, otherwise it is the decimal point.

The majority convention wins; the margin becomes the confidence. ``Config.locale``
overrides the vote entirely. Only columns that are *mostly* numeric strings are
touched — a text column with the odd number is left alone.
"""

from __future__ import annotations

import re

from messy_table.config import Config
from messy_table.context import Context
from messy_table.grid import Grid
from messy_table.report import ActionKind
from messy_table.util import is_blank, looks_like_number

# Fraction of non-blank string cells that must look numeric to treat the column
# as a numeric column.
NUMERIC_COLUMN_RATIO = 0.7
_CURRENCY = ("R$", "US$", "$", "€", "£")
# (decimal, thousands) per forced locale.
_LOCALE_SEPS: dict[str, tuple[str, str]] = {
    "pt_BR": (",", "."),
    "de_DE": (",", "."),
    "fr_FR": (",", " "),
    "en_US": (".", ","),
}
_GROUP_3 = re.compile(r"^\d{1,3}(\d{3})+$")


def parse_numbers(grid: Grid, ctx: Context) -> None:
    cfg = ctx.config
    names = ctx.column_names
    for c in range(grid.ncols):
        column = names[c] if c < len(names) else None
        string_cells = [
            (r, v)
            for r in range(grid.nrows)
            if isinstance((v := grid.values[r][c]), str) and not is_blank(v)
        ]
        if not string_cells:
            continue
        numeric_cells = [(r, v) for r, v in string_cells if looks_like_number(v)]
        if len(numeric_cells) < NUMERIC_COLUMN_RATIO * len(string_cells):
            continue

        decimal_sep, thousands_sep, locale_name, confidence = _infer_locale(numeric_cells, cfg)
        if confidence < cfg.confidence_threshold:
            ctx.ambiguous(
                f"ambiguous number format in column {column!r} (confidence {confidence})",
                suggestion='Config(locale="pt_BR")  # or "en_US"',
                column=column,
                confidence=confidence,
            )
        for r, raw in numeric_cells:
            parsed = _parse_number(raw, decimal_sep, thousands_sep)
            if parsed is None:
                continue
            grid.values[r][c] = parsed
            ctx.report.record(
                ActionKind.NUMBER_PARSED,
                f"locale:{locale_name}",
                column=column,
                row=r,
                col=c,
                original=raw,
                final=parsed,
                confidence=confidence,
            )


def _infer_locale(cells: list[tuple[int, str]], cfg: Config) -> tuple[str, str, str, float]:
    if cfg.locale != "auto":
        decimal_sep, thousands_sep = _LOCALE_SEPS[cfg.locale]
        return decimal_sep, thousands_sep, cfg.locale, 1.0

    comma_votes = dot_votes = 0
    for _, raw in cells:
        vote = _decimal_vote(raw)
        if vote == ",":
            comma_votes += 1
        elif vote == ".":
            dot_votes += 1

    total = comma_votes + dot_votes
    if total == 0:
        # All plain integers: convention is irrelevant. Default to en-US grouping.
        return ".", ",", "en_US", 1.0
    if comma_votes >= dot_votes:
        return ",", ".", "pt_BR", round(comma_votes / total, 2)
    return ".", ",", "en_US", round(dot_votes / total, 2)


def _decimal_vote(raw: str) -> str | None:
    """Which character is this value's decimal separator? ``None`` if undecidable."""
    body = _strip_affixes(raw)
    has_dot, has_comma = "." in body, "," in body
    if has_dot and has_comma:
        return "." if body.rfind(".") > body.rfind(",") else ","
    if has_comma:
        return "." if _is_thousands_grouping(body, ",") else ","
    if has_dot:
        return "," if _is_thousands_grouping(body, ".") else "."
    return None


def _is_thousands_grouping(body: str, sep: str) -> bool:
    """True when ``sep`` splits ``body`` into a leading run then clean 3-digit runs.

    ``1.234`` and ``12.345.678`` look like grouping; ``1.23`` and ``1.2345`` do not.
    """
    if body.count(sep) == 0:
        return False
    digits_only = body.replace(sep, "")
    return bool(_GROUP_3.match(digits_only)) and all(len(part) == 3 for part in body.split(sep)[1:])


def _strip_affixes(raw: str) -> str:
    t = raw.strip()
    for sym in _CURRENCY:
        t = t.replace(sym, "")
    return t.strip().lstrip("+-").rstrip("%").strip().replace(" ", "").replace("\u00a0", "")


def _parse_number(raw: str, decimal_sep: str, thousands_sep: str) -> int | float | None:
    t = raw.strip()
    for sym in _CURRENCY:
        t = t.replace(sym, "")
    t = t.strip()
    is_percent = t.endswith("%")
    t = t.rstrip("%").strip()
    sign = 1
    if t.startswith("-"):
        sign, t = -1, t[1:]
    elif t.startswith("+"):
        t = t[1:]
    t = t.replace(" ", "").replace("\u00a0", "").replace("'", "")
    had_decimal = decimal_sep in t
    if thousands_sep:
        t = t.replace(thousands_sep, "")
    if decimal_sep:
        t = t.replace(decimal_sep, ".")
    try:
        number = float(t) * sign
    except ValueError:
        return None
    if is_percent:
        return number / 100.0
    if not had_decimal and number.is_integer():
        return int(number)
    return number

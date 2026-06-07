"""F2 (detection half) — find the header row(s).

By the time this runs the grid is already sliced to the table body and unmerged,
so the header is at local row 0. Two questions:

* **Is there a header at all?** If the first row looks like data (numeric-heavy)
  and has the same per-column type signature as the row below it, there is no
  header — we synthesise ``column_1 ...`` and start data at row 0.
* **How many rows does it span?** Multi-row headers ("Vendas" over "2024") come
  from a horizontally merged group cell. We keep the original merged ranges as
  metadata, so a top row that intersects a horizontal merge tells us the next
  row holds the leaf labels. That ties multi-row detection to real structure
  rather than a fragile text heuristic.

The raw, still-dirty column names are returned; slugifying/de-duping/filling is
the header-names transformer's job.
"""

from __future__ import annotations

from messy_table.context import Context
from messy_table.grid import Grid
from messy_table.report import ActionKind
from messy_table.util import raw_category

MAX_HEADER_ROWS = 3
TEXT_RATIO_THRESHOLD = 0.5


def detect_header(grid: Grid, ctx: Context) -> tuple[int, list[str]]:
    """Return ``(header_row_count, raw_column_names)``.

    ``header_row_count`` is the number of leading rows consumed by the header;
    data begins at that local index.
    """
    cfg = ctx.config
    nrows, ncols = grid.nrows, grid.ncols

    if cfg.header is None:
        return 0, _synthetic_names(ncols)
    if nrows == 0:
        return 0, []

    if isinstance(cfg.header, int):
        ctx.report.note(ActionKind.HEADER, "config", detail="header row pinned via Config.header")
        return 1, _merge_header_rows(grid, 1, ncols)

    row0_text = _text_ratio(grid.row(0))
    if _looks_headerless(grid, row0_text):
        ctx.warn(
            "no header row detected; generated column names",
            suggestion="Config(header=0) to force the first row as the header",
        )
        return 0, _synthetic_names(ncols)

    max_header = max(1, min(MAX_HEADER_ROWS, nrows - 1)) if nrows > 1 else 1
    header_rows = 1
    while header_rows < max_header and _has_horizontal_merge(grid, header_rows - 1):
        header_rows += 1

    confidence = 0.9 if row0_text >= TEXT_RATIO_THRESHOLD else 0.55
    detail = f"header occupies {header_rows} row(s)"
    if header_rows > 1:
        detail += " (multi-row header merged column-wise)"
    ctx.report.note(ActionKind.HEADER, "auto", detail=detail, confidence=confidence)
    if confidence < cfg.confidence_threshold:
        ctx.ambiguous(
            f"low confidence ({confidence}) that row 0 is a header",
            suggestion="Config(header=<row index>) or Config(header=None)",
        )
    return header_rows, _merge_header_rows(grid, header_rows, ncols)


def _looks_headerless(grid: Grid, row0_text: float) -> bool:
    if grid.nrows < 2 or row0_text >= TEXT_RATIO_THRESHOLD:
        return False
    if _has_horizontal_merge(grid, 0):
        return False
    return _category_signature(grid.row(0)) == _category_signature(grid.row(1))


def _text_ratio(row: list[object]) -> float:
    cats = [raw_category(v) for v in row]
    nonblank = [c for c in cats if c != "blank"]
    if not nonblank:
        return 0.0
    return sum(1 for c in nonblank if c == "text") / len(nonblank)


def _category_signature(row: list[object]) -> tuple[str, ...]:
    return tuple(raw_category(v) for v in row)


def _has_horizontal_merge(grid: Grid, row: int) -> bool:
    return any(m.min_row <= row <= m.max_row and m.max_col > m.min_col for m in grid.merged_ranges)


def _merge_header_rows(grid: Grid, header_rows: int, ncols: int) -> list[str]:
    names: list[str] = []
    for c in range(ncols):
        parts: list[str] = []
        for r in range(header_rows):
            value = grid.cell(r, c)
            if value is None:
                continue
            text = str(value).strip()
            # Skip a part already contributed by the row above (merge fill repeats it).
            if text and (not parts or parts[-1] != text):
                parts.append(text)
        names.append(" ".join(parts))
    return names


def _synthetic_names(ncols: int) -> list[str]:
    return [f"column_{i + 1}" for i in range(ncols)]

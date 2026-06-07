"""F8 — trim trailing junk: totals, signatures, footnotes.

After the last data row, exports often append a totals line, a "Gerado em ..."
stamp, a signature, or free-text notes. We walk up from the bottom and trim rows
that are either *sparse* (the data block is dense, these are not) or begin with a
*summary keyword*. We stop at the first real data row, so only the trailing block
is removed.
"""

from __future__ import annotations

from messy_table.context import Context
from messy_table.grid import Grid
from messy_table.report import ActionKind
from messy_table.util import (
    density_threshold,
    first_nonblank,
    is_blank,
    merge_covered_cells,
)

DENSITY_RATIO = 0.5

# Lower-cased; matched as a prefix of the row's first non-blank cell.
SUMMARY_PREFIXES = (
    "total",
    "totais",
    "subtotal",
    "sub-total",
    "soma",
    "grand total",
    "resumo",
    "média",
    "media",
    "assinatura",
    "observ",
    "obs.",
    "nota",
    "fonte",
    "gerado em",
    "emitido",
    "página",
    "pagina",
)


def detect_table_end(grid: Grid, ctx: Context, start: int) -> int:
    """Return the exclusive end row index of the data block."""
    nrows, ncols = grid.nrows, grid.ncols
    if nrows == 0 or ncols == 0:
        return nrows

    covered = merge_covered_cells(grid.merged_ranges)
    # Measure fill against *live* columns only. A fully empty column (a stray
    # trailing column is common in real exports) must not make every data row look
    # sparse and get trimmed as junk — that silently destroys the whole table.
    live_cols = _live_columns(grid, start + 1, nrows, covered)
    threshold = density_threshold(len(live_cols), DENSITY_RATIO)

    end = nrows
    keyword_hit = False
    r = nrows - 1
    while r > start:
        first = first_nonblank(grid.row(r))
        filled_live = sum(
            1 for c in live_cols if not is_blank(grid.cell(r, c)) or (r, c) in covered
        )
        is_summary = isinstance(first, str) and first.strip().lower().startswith(SUMMARY_PREFIXES)
        if filled_live < threshold or is_summary:
            end = r
            keyword_hit = keyword_hit or is_summary
            r -= 1
        else:
            break

    return _finish(ctx, nrows, end, start, keyword_hit)


def _live_columns(grid: Grid, start: int, stop: int, covered: set[tuple[int, int]]) -> set[int]:
    """Columns holding any data in ``[start, stop)``. Short-circuits when all are
    live (the common dense case), so this stays cheap on large sheets."""
    ncols = grid.ncols
    live: set[int] = set()
    for r in range(start, stop):
        for c in range(ncols):
            if c not in live and (not is_blank(grid.cell(r, c)) or (r, c) in covered):
                live.add(c)
        if len(live) == ncols:
            break
    return live or set(range(ncols))


def _finish(ctx: Context, nrows: int, end: int, start: int, keyword_hit: bool) -> int:
    trimmed = nrows - end
    if trimmed:
        # A keyword-matched total carries more certainty than a merely sparse row.
        confidence = 0.85 if keyword_hit else 0.7
        ctx.report.note(
            ActionKind.TABLE_END,
            "trailing-junk",
            detail=f"trimmed {trimmed} trailing row(s) (totals/notes/blank) after row {end - 1}",
            confidence=confidence,
        )
    return end

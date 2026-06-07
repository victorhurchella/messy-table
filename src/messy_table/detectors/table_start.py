"""F1 — find where the real table begins.

Real exports bury the table under a title, a logo cell, a date stamp, blank
rows. Those leading rows are *sparse*: one or two filled cells. The table — its
header included — is *dense*: most columns filled, row after row. So we locate
the longest contiguous run of dense rows and call its first row the start.

Merged title banners are not a problem here: openpyxl reports a merged cell's
value only in its top-left anchor, so a full-width merged title still counts as
a single filled cell. We detect boundaries *before* unmerging precisely so this
holds.
"""

from __future__ import annotations

from messy_table.context import Context
from messy_table.grid import Grid
from messy_table.report import ActionKind
from messy_table.util import density_threshold, merge_covered_cells, row_filled_counts

DENSITY_RATIO = 0.5


def detect_table_start(grid: Grid, ctx: Context) -> int:
    """Return the 0-based index of the first row belonging to the table."""
    cfg = ctx.config
    nrows, ncols = grid.nrows, grid.ncols
    if nrows == 0 or ncols == 0:
        return 0

    if isinstance(cfg.header, int):
        start = min(cfg.header, nrows - 1)
        if start > 0:
            ctx.report.note(
                ActionKind.TABLE_START,
                "config",
                detail=f"table start pinned to row {start} via Config.header",
            )
        return start

    covered = merge_covered_cells(grid.merged_ranges)
    filled = row_filled_counts(grid.values, covered)
    width = max(filled)
    if width == 0:
        return 0
    threshold = density_threshold(width, DENSITY_RATIO)
    substantial = [f >= threshold for f in filled]

    best_start, best_len = 0, 0
    i = 0
    while i < nrows:
        if not substantial[i]:
            i += 1
            continue
        j = i
        while j < nrows and substantial[j]:
            j += 1
        if j - i > best_len:
            best_start, best_len = i, j - i
        i = j

    start = best_start
    if start > 0:
        above_density = sum(filled[:start]) / (start * ncols)
        body_density = filled[start] / ncols
        confidence = round(min(1.0, max(0.3, body_density - above_density + 0.5)), 2)
        ctx.report.note(
            ActionKind.TABLE_START,
            "density",
            detail=(
                f"skipped {start} leading row(s) (title/metadata/blank); "
                f"table starts at row {start}"
            ),
            confidence=confidence,
        )
        if confidence < cfg.confidence_threshold:
            ctx.ambiguous(
                f"low confidence ({confidence}) locating the table start at row {start}",
                suggestion=f"Config(header={start})",
            )
    return start

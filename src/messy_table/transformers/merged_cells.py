"""F3 — merged cells.

openpyxl stores a merged value only in the range's top-left anchor; every other
cell in the range reads as ``None``. ``"fill"`` propagates the anchor value
across the whole range (the common, useful default — a category merged down a
column should apply to each row). ``"first-only"`` keeps openpyxl's behaviour and
is a no-op here.

This runs on the body slice *before* header detection so that a horizontally
merged group header ("Vendas" spanning two columns) is filled and the header
detector can merge it with the leaf row below.
"""

from __future__ import annotations

from messy_table.context import Context
from messy_table.grid import Grid
from messy_table.report import ActionKind


def apply_merged_cells(grid: Grid, ctx: Context) -> None:
    if not grid.merged_ranges or ctx.config.merged_cells == "first-only":
        return

    for rng in grid.merged_ranges:
        anchor = grid.cell(rng.min_row, rng.min_col)
        if anchor is None:
            continue
        for row, col in rng.cells():
            if (row, col) == (rng.min_row, rng.min_col):
                continue
            if grid.values[row][col] != anchor:
                grid.values[row][col] = anchor
                ctx.report.record(
                    ActionKind.MERGED_FILLED,
                    "fill",
                    row=row,
                    col=col,
                    original=None,
                    final=anchor,
                )

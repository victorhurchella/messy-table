"""The single public entry point: :func:`clean`.

This module owns the pipeline order, which is the one place the whole design
comes together:

    read → [detect start] → [detect end] → slice body
         → unmerge → [detect header] → name header → slice off header
         → nulls → numbers → dates → finalize types → emit

Detectors run on the still-merged grid (so banner/title rows stay sparse and get
skipped); unmerge then runs before header detection; value transformers run on
the header-stripped data grid in dependency order.
"""

from __future__ import annotations

from typing import Any

from messy_table.config import Config
from messy_table.context import Context
from messy_table.detectors import detect_header, detect_table_end, detect_table_start
from messy_table.grid import Grid, SourceInfo
from messy_table.readers import Source, read
from messy_table.result import CleanResult
from messy_table.transformers import (
    apply_merged_cells,
    convert_dates,
    finalize_types,
    normalize_headers,
    normalize_nulls,
    parse_numbers,
)


def clean(source: Source, *, config: Config | None = None) -> CleanResult:
    """Clean a messy spreadsheet and return typed data plus an audit report.

    Parameters
    ----------
    source:
        A path (``str``/``Path``), raw ``bytes``, or a binary/text file-like
        object holding an ``.xlsx``, ``.csv`` or ``.tsv``.
    config:
        Optional :class:`~messy_table.config.Config`. Omit it for the 80% case.

    Returns
    -------
    CleanResult
        ``.data``, ``.columns``, ``.report`` and ``.warnings``.
    """
    cfg = config or Config()
    ctx = Context(config=cfg, source=SourceInfo(origin="<input>", kind="unknown"))

    grid = read(source, cfg, ctx)
    if grid.nrows == 0 or grid.ncols == 0:
        return _empty_result(ctx)

    start = detect_table_start(grid, ctx)
    end = detect_table_end(grid, ctx, start)
    body = grid.slice_rows(start, end)

    apply_merged_cells(body, ctx)

    header_rows, raw_names = detect_header(body, ctx)
    pairs = normalize_headers(raw_names, ctx)
    originals = [original for original, _ in pairs]

    data = body.slice_rows(header_rows, body.nrows)
    normalize_nulls(data, ctx)
    parse_numbers(data, ctx)
    convert_dates(data, ctx)
    columns = finalize_types(data, ctx, originals)

    rows = _emit_rows(data, ctx.column_names)
    return CleanResult(
        data=rows,
        columns=columns,
        report=ctx.report.build(),
        warnings=ctx.warnings,
        source=ctx.source,
    )


def _emit_rows(grid: Grid, names: list[str]) -> list[dict[str, Any]]:
    return [{names[c]: grid.cell(r, c) for c in range(len(names))} for r in range(grid.nrows)]


def _empty_result(ctx: Context) -> CleanResult:
    ctx.warn("input contained no data", suggestion="check the file and sheet selection")
    return CleanResult(
        data=[],
        columns=[],
        report=ctx.report.build(),
        warnings=ctx.warnings,
        source=ctx.source,
    )

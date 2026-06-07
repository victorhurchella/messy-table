"""XLSX reader built on openpyxl.

Two security and performance realities shape this module:

1. ``.xlsx`` is a ZIP archive, so it can be a *decompression bomb*. We inspect
   the archive's declared sizes before openpyxl touches it and refuse anything
   that expands beyond sane absolute and ratio limits.
2. openpyxl's full (styled) load is correct but heavy. For ordinary spreadsheets
   we use it — it gives values, number formats, merged ranges and bold in one
   pass. For very large sheets we switch to read-only streaming (values +
   number formats only), which meets the <5s / 50k-row performance gate, and we
   record a warning that merged-cell handling was skipped.

openpyxl returns ``datetime`` objects for date-formatted cells already (using the
workbook epoch); the raw-serial case that F4 cares about is handled downstream.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils.datetime import CALENDAR_MAC_1904
from openpyxl.worksheet.worksheet import Worksheet

from messy_table.config import Config
from messy_table.context import Context
from messy_table.exceptions import MessyTableError, UnsupportedFormatError
from messy_table.grid import Epoch, Grid, MergedRange, SourceInfo

# Above this many cells we stop loading styles and stream values only.
LARGE_SHEET_CELLS = 200_000
# Bold is only a header signal, so we only ever look at the top of the sheet.
HEADER_SCAN_ROWS = 50


def read_xlsx(data: bytes, origin: str, config: Config, ctx: Context) -> Grid:
    _guard_decompression_bomb(data, config)

    # Stream values first via read-only `values_only`: fast, low-memory, and — key
    # for security — it never calls ws.max_row, which would make openpyxl scan the
    # whole sheet when the <dimension> tag is absent or lying. The cell cap is
    # enforced as we read, so size limits do not depend on the declared dimension.
    values, epoch, sheet_name = _read_values(data, config)
    source = SourceInfo(origin=origin, kind="xlsx", sheet=sheet_name, epoch=epoch)
    ctx.source = source
    nrows = len(values)
    ncols = max((len(line) for line in values), default=0)

    if nrows * ncols > LARGE_SHEET_CELLS:
        ctx.warn(
            f"sheet {sheet_name!r} has ~{nrows * ncols} cells; merged-cell propagation "
            "is skipped for very large sheets to stay within the performance budget",
            suggestion="split the sheet or pre-unmerge in Excel if merges matter",
        )
        return Grid(values=values, source=source)

    # openpyxl's styled load materialises a MergedCell per merged cell — O(total
    # merged area). A crafted file with overlapping merges can blow that up. A valid
    # sheet's merges never exceed its own area (Excel forbids overlaps), so if the
    # declared merge area does, we keep the merge-free stream we already have.
    if _merge_area_exceeds(data, max(nrows * ncols, 1)):
        ctx.warn(
            "merged ranges cover more area than the sheet itself; reading without "
            "merge handling (malformed or adversarial file)",
            suggestion="check the source spreadsheet for overlapping merges",
        )
        return Grid(values=values, source=source)

    # Small and well-formed: re-read with styles to capture merges, number formats
    # and bold. The extra pass is cheap at this size.
    return _read_full(data, config, source, ctx)


def _merge_area_exceeds(data: bytes, area_cap: int) -> bool:
    """Sum the area of declared ``<mergeCell>`` refs; stop early once over the cap.

    Cheap (the full-load path only runs for bounded sheets, so the worksheet XML
    is small) and runs *before* openpyxl, so it caps the work openpyxl would do.
    """
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml")]
        for name in names:
            for ref in re.findall(rb'<mergeCell ref="([^"]+)"', zf.read(name)):
                try:
                    min_col, min_row, max_col, max_row = range_boundaries(ref.decode("ascii"))
                except ValueError:
                    continue
                if None in (min_col, min_row, max_col, max_row):
                    return True  # whole-row/column merge — unbounded, treat as excessive
                total += (max_col - min_col + 1) * (max_row - min_row + 1)
                if total > area_cap:
                    return True
    return False


def _guard_decompression_bomb(data: bytes, config: Config) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            uncompressed = sum(info.file_size for info in zf.infolist())
            compressed = sum(info.compress_size for info in zf.infolist()) or 1
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormatError(
            "not a valid .xlsx file (corrupt or not a ZIP archive)"
        ) from exc
    if uncompressed > config.max_uncompressed_bytes:
        raise UnsupportedFormatError(
            f"archive expands to {uncompressed} bytes, above the "
            f"{config.max_uncompressed_bytes}-byte limit (possible decompression bomb)"
        )
    if uncompressed / compressed > config.max_compression_ratio:
        raise UnsupportedFormatError(
            f"archive compression ratio {uncompressed / compressed:.0f}x exceeds the "
            f"{config.max_compression_ratio}x limit (possible decompression bomb)"
        )


def _select_sheet(wb: Any, sheet: int | str) -> Worksheet:
    try:
        if isinstance(sheet, int):
            return wb.worksheets[sheet]
        return wb[sheet]
    except (IndexError, KeyError) as exc:
        available = ", ".join(repr(n) for n in wb.sheetnames)
        raise MessyTableError(f"sheet {sheet!r} not found; available sheets: {available}") from exc


def _read_values(data: bytes, config: Config) -> tuple[list[list[Any]], Epoch, str]:
    """Stream the value matrix (+ epoch, sheet name) via read-only `values_only`.

    Deliberately avoids ws.max_row/max_column — accessing them forces a full-sheet
    scan when the dimension tag is missing. We size the sheet from what we read and
    enforce the cell cap inline, so the limit never depends on declared dimensions.
    """
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = _select_sheet(wb, config.sheet)
        epoch = Epoch.E1904 if wb.epoch == CALENDAR_MAC_1904 else Epoch.E1900
        values: list[list[Any]] = []
        append = values.append
        cap = config.max_cells
        cell_count = 0
        # Hot loop: keep it tight. The cap check is inlined (no per-row call) so a
        # crafted huge sheet is still bounded in memory and time as we read.
        for row in ws.iter_rows(values_only=True):
            line = list(row)
            append(line)
            cell_count += len(line)
            if cell_count > cap:
                raise UnsupportedFormatError(
                    f"sheet exceeds the {cap}-cell limit while reading "
                    "(declared dimensions were misleading)"
                )
        return values, epoch, ws.title
    finally:
        wb.close()


def _read_full(data: bytes, config: Config, source: SourceInfo, ctx: Context) -> Grid:
    wb = load_workbook(io.BytesIO(data), read_only=False, data_only=True)
    try:
        ws = _select_sheet(wb, config.sheet)
        values: list[list[Any]] = []
        number_formats: dict[tuple[int, int], str] = {}
        is_date: set[tuple[int, int]] = set()
        bold_cells: set[tuple[int, int]] = set()

        cell_count = 0
        for r, row in enumerate(ws.iter_rows()):
            line: list[Any] = []
            for c, cell in enumerate(row):
                line.append(cell.value)
                # Non-anchor cells of a merge are MergedCell, which lack these
                # style attributes; getattr keeps the loop branch-free and safe.
                fmt = getattr(cell, "number_format", None)
                if fmt and fmt != "General":
                    number_formats[(r, c)] = fmt
                if getattr(cell, "is_date", False):
                    is_date.add((r, c))
                font = getattr(cell, "font", None)
                if r < HEADER_SCAN_ROWS and font is not None and font.bold:
                    bold_cells.add((r, c))
            cell_count += len(line)
            _enforce_cell_cap(cell_count, config)
            values.append(line)

        merged = _collect_merges(ws, values, ctx)
        return Grid(
            values=values,
            source=source,
            merged_ranges=merged,
            number_formats=number_formats,
            is_date=is_date,
            bold_cells=bold_cells,
        )
    finally:
        wb.close()


def _enforce_cell_cap(cell_count: int, config: Config) -> None:
    """Enforce ``max_cells`` *during* the read.

    The pre-read probe trusts the sheet's declared ``<dimension>``, which is
    attacker-controlled. This makes the ceiling real regardless of what the
    dimension claims, bounding both memory and time on crafted files.
    """
    if cell_count > config.max_cells:
        raise UnsupportedFormatError(
            f"sheet exceeds the {config.max_cells}-cell limit while reading "
            "(declared dimensions were misleading)"
        )


def _collect_merges(ws: Worksheet, values: list[list[Any]], ctx: Context) -> list[MergedRange]:
    """Collect merged ranges, bounded by the sheet's own area.

    Excel forbids overlapping merges, so a legitimate sheet's merged ranges sum to
    at most its cell count. A crafted file with thousands of large overlapping
    merges would otherwise make merge-aware density O(ranges x area) — tens of
    seconds of CPU. We cap the total area at the sheet size and warn past it.
    """
    nrows = len(values)
    ncols = max((len(line) for line in values), default=0)
    area_cap = max(nrows * ncols, 1)
    merged: list[MergedRange] = []
    total_area = 0
    for rng in ws.merged_cells.ranges:
        m = MergedRange(rng.min_row - 1, rng.min_col - 1, rng.max_row - 1, rng.max_col - 1)
        total_area += (m.max_row - m.min_row + 1) * (m.max_col - m.min_col + 1)
        if total_area > area_cap:
            ctx.warn(
                "merged ranges cover more area than the sheet itself; ignoring the "
                "excess (malformed or adversarial file)",
                suggestion="check the source spreadsheet for overlapping merges",
            )
            break
        merged.append(m)
    return merged

"""The :class:`Grid` — messy-table's single in-memory representation.

A reader produces a ``Grid``; every detector and transformer reads (and some
mutate) it; the emitter consumes it. The design goal is *cheap to carry around*:
values live in a dense matrix, while sparse per-cell metadata (number formats,
bold cells, merged ranges) lives in side tables so that a 1.5M-cell sheet does
not allocate 1.5M wrapper objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NamedTuple


class Epoch(str, Enum):
    """Excel's two date-serial origins. Captured by the reader, used by F4."""

    E1900 = "1900"  # Windows default; day 1 == 1900-01-01 (with the leap bug)
    E1904 = "1904"  # legacy Mac default


class MergedRange(NamedTuple):
    """A merged-cell rectangle, 0-based and inclusive on both corners."""

    min_row: int
    min_col: int
    max_row: int
    max_col: int

    def cells(self) -> list[tuple[int, int]]:
        return [
            (r, c)
            for r in range(self.min_row, self.max_row + 1)
            for c in range(self.min_col, self.max_col + 1)
        ]


@dataclass(slots=True)
class SourceInfo:
    """Provenance for the report and for epoch-aware date conversion."""

    origin: str  # filename, sheet name, or "<bytes>"
    kind: str  # "xlsx" | "csv" | "tsv"
    sheet: str | None = None
    epoch: Epoch = Epoch.E1900
    encoding: str | None = None
    delimiter: str | None = None


@dataclass(slots=True)
class Grid:
    """A rectangular value matrix plus sparse formatting metadata.

    ``values[r][c]`` holds the raw cell value as the reader saw it: ``str`` for
    text, ``int``/``float`` for numbers, ``datetime``/``date`` for date-formatted
    xlsx cells, ``bool`` for booleans, ``None`` for blanks. Ragged input is
    normalised to a rectangle at construction.
    """

    values: list[list[Any]]
    source: SourceInfo
    merged_ranges: list[MergedRange] = field(default_factory=list)
    # Sparse: only cells whose number format is not "General".
    number_formats: dict[tuple[int, int], str] = field(default_factory=dict)
    # Sparse: only cells that openpyxl reported a date for (already a datetime).
    is_date: set[tuple[int, int]] = field(default_factory=set)
    # Sparse: only bold cells (a header signal). Empty for CSV/large xlsx.
    bold_cells: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._normalize_rectangular()

    def _normalize_rectangular(self) -> None:
        width = self.ncols
        for row in self.values:
            if len(row) < width:
                row.extend([None] * (width - len(row)))

    @property
    def nrows(self) -> int:
        return len(self.values)

    @property
    def ncols(self) -> int:
        return max((len(r) for r in self.values), default=0)

    def cell(self, row: int, col: int) -> Any:
        """Safe accessor: out-of-range coordinates read as ``None``."""
        if 0 <= row < len(self.values):
            line = self.values[row]
            if 0 <= col < len(line):
                return line[col]
        return None

    def row(self, index: int) -> list[Any]:
        return self.values[index]

    def column(self, index: int, *, start: int = 0, stop: int | None = None) -> list[Any]:
        stop = self.nrows if stop is None else stop
        return [self.cell(r, index) for r in range(start, stop)]

    def is_date_cell(self, row: int, col: int) -> bool:
        return (row, col) in self.is_date

    def number_format(self, row: int, col: int) -> str | None:
        return self.number_formats.get((row, col))

    def slice_rows(self, start: int, stop: int) -> Grid:
        """Return a new Grid restricted to ``[start, stop)`` rows.

        The new grid *shares* its row lists with this one (a shallow slice) — the
        pipeline only ever advances forward and discards the parent, so this is
        safe and avoids copying every cell of a large sheet on each slice. Sparse
        metadata is re-based onto the new coordinate system.
        """
        sub_values = self.values[start:stop]
        in_range = range(start, stop)
        return Grid(
            values=sub_values,
            source=self.source,
            merged_ranges=[
                MergedRange(m.min_row - start, m.min_col, m.max_row - start, m.max_col)
                for m in self.merged_ranges
                if m.min_row >= start and m.max_row < stop
            ],
            number_formats={
                (r - start, c): fmt for (r, c), fmt in self.number_formats.items() if r in in_range
            },
            is_date={(r - start, c) for (r, c) in self.is_date if r in in_range},
            bold_cells={(r - start, c) for (r, c) in self.bold_cells if r in in_range},
        )

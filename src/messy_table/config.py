"""User-facing configuration.

The 80% case needs none of this — ``clean(path)`` works. ``Config`` exists for
the cases where a heuristic needs a hand: a forced locale, a known header row,
a specific sheet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from messy_table.exceptions import MessyTableError

MergedCellsMode = Literal["fill", "first-only"]
HeaderSpec = Literal["auto"] | int | None
LocaleSpec = Literal["auto", "pt_BR", "en_US", "de_DE", "fr_FR"]

# A library that parses untrusted files needs hard ceilings. These defend
# against decompression bombs and pathological inputs without getting in the
# way of any realistic spreadsheet (50k x 30 = 1.5M cells sits well under).
_DEFAULT_MAX_CELLS = 5_000_000
_DEFAULT_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024  # 512 MiB expanded
_DEFAULT_MAX_COMPRESSION_RATIO = 200  # expanded/packed beyond this is suspicious


@dataclass(frozen=True, slots=True)
class Config:
    """Tuning knobs for :func:`messy_table.clean`.

    All fields have safe defaults; constructing ``Config()`` matches the implicit
    behaviour of calling ``clean`` with no config.
    """

    locale: LocaleSpec = "auto"
    """Forces number/date interpretation. ``"auto"`` infers per column."""

    header: HeaderSpec = "auto"
    """``"auto"`` detects the header; an ``int`` pins the 0-based row; ``None``
    means there is no header (columns become ``column_1``, ``column_2``, ...)."""

    sheet: int | str = 0
    """Worksheet to read, by 0-based index or by name. Ignored for CSV/TSV."""

    merged_cells: MergedCellsMode = "fill"
    """``"fill"`` propagates a merged value across its whole range;
    ``"first-only"`` keeps it in the top-left cell and nulls the rest."""

    null_values_extra: tuple[str, ...] = ()
    """Extra tokens to treat as null, *added* to the built-in set."""

    strict: bool = False
    """When ``True``, a low-confidence decision raises
    :class:`~messy_table.exceptions.AmbiguityError` instead of warning."""

    # --- Safety limits (rarely touched; present so they are auditable) -------
    max_cells: int = _DEFAULT_MAX_CELLS
    max_uncompressed_bytes: int = _DEFAULT_MAX_UNCOMPRESSED_BYTES
    max_compression_ratio: int = _DEFAULT_MAX_COMPRESSION_RATIO

    # Confidence thresholds for the heuristics. Documented in docs/heuristics.md.
    confidence_threshold: float = field(default=0.6)
    """Below this, a decision is a warning (or an error in strict mode)."""

    def __post_init__(self) -> None:
        if self.merged_cells not in ("fill", "first-only"):
            raise MessyTableError(
                f"merged_cells must be 'fill' or 'first-only', got {self.merged_cells!r}"
            )
        if not (0.0 <= self.confidence_threshold <= 1.0):
            raise MessyTableError("confidence_threshold must be in [0.0, 1.0]")
        if isinstance(self.header, int) and self.header < 0:
            raise MessyTableError("header row index must be >= 0")
        if self.max_cells <= 0 or self.max_uncompressed_bytes <= 0:
            raise MessyTableError("safety limits must be positive")

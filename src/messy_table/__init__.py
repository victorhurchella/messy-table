"""messy-table — turn messy real-world spreadsheets into clean, typed data.

``pandas.read_excel`` assumes your spreadsheet is well-behaved. messy-table
assumes it is not.

    >>> from messy_table import clean
    >>> result = clean("relatorio_vendas.xlsx")
    >>> result.data        # list[dict] — clean, typed rows
    >>> result.columns     # per-column name/dtype/null summary
    >>> result.report      # every fix that was applied
    >>> result.warnings    # low-confidence decisions

The public surface is intentionally small. Everything below ``clean`` and
``Config`` is for inspecting results and handling errors.
"""

from __future__ import annotations

from messy_table.api import clean
from messy_table.config import Config
from messy_table.exceptions import (
    AmbiguityError,
    MessyTableError,
    UnsupportedFormatError,
)
from messy_table.report import (
    Action,
    ActionKind,
    CleanReport,
    ColumnInfo,
    Issue,
    Severity,
)
from messy_table.result import CleanResult

__version__ = "0.1.0"

__all__ = [
    "Action",
    "ActionKind",
    "AmbiguityError",
    "CleanReport",
    "CleanResult",
    "ColumnInfo",
    "Config",
    "Issue",
    "MessyTableError",
    "Severity",
    "UnsupportedFormatError",
    "__version__",
    "clean",
]

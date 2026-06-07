"""Transformers mutate the grid in place and record every change they make.

Order matters and is fixed by the pipeline in ``api.py``: unmerge runs before
header detection; nulls run before number/date parsing so missing values do not
poison type inference; type finalisation runs last."""

from __future__ import annotations

from messy_table.transformers.dates import convert_dates
from messy_table.transformers.header_names import normalize_headers
from messy_table.transformers.merged_cells import apply_merged_cells
from messy_table.transformers.nulls import normalize_nulls
from messy_table.transformers.numbers import parse_numbers
from messy_table.transformers.types import finalize_types

__all__ = [
    "apply_merged_cells",
    "convert_dates",
    "finalize_types",
    "normalize_headers",
    "normalize_nulls",
    "parse_numbers",
]

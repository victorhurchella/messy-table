"""Detectors locate structure in the raw grid; each returns a decision + records
its confidence. They never mutate values — that is the transformers' job."""

from __future__ import annotations

from messy_table.detectors.header import detect_header
from messy_table.detectors.table_end import detect_table_end
from messy_table.detectors.table_start import detect_table_start

__all__ = ["detect_header", "detect_table_end", "detect_table_start"]

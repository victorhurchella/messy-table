"""CSV / TSV reader with encoding and delimiter sniffing.

The spec's F10 requires us to handle real-world exports: unknown delimiter
(``,`` ``;`` tab ``|``) and unknown encoding (UTF-8, Latin-1, cp1252). We do
both without an external dependency — a decode cascade for encoding and a
Sniffer-with-fallback for the delimiter.
"""

from __future__ import annotations

import csv
import io
from collections import Counter

from messy_table.config import Config
from messy_table.context import Context
from messy_table.grid import Grid, SourceInfo

# Order matters: utf-8-sig strips a BOM if present; cp1252 is a strict superset
# attempt before latin-1, which decodes any byte sequence and so is the floor.
_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
_CANDIDATE_DELIMITERS = ",;\t|"
_SNIFF_SAMPLE = 64 * 1024


def read_csv(data: bytes, origin: str, kind: str, config: Config, ctx: Context) -> Grid:
    text, encoding = _decode(data)
    delimiter = "\t" if kind == "tsv" else _sniff_delimiter(text)
    # A None delimiter means "single column" — use a char that cannot occur so
    # csv keeps each line as one field (and a stray decimal comma is left alone).
    effective = delimiter if delimiter is not None else "\x00"

    source = SourceInfo(
        origin=origin,
        kind=kind,
        encoding=encoding,
        delimiter=_name_delimiter(delimiter) if delimiter is not None else "single-column",
    )
    ctx.source = source

    reader = csv.reader(io.StringIO(text), delimiter=effective)
    # Keep every cell as the raw string the file held; typing happens downstream.
    # Strip a trailing fully-empty row that a final newline produces.
    rows: list[list[object]] = [list(r) for r in reader]
    while rows and all(c == "" for c in rows[-1]):
        rows.pop()

    if not rows:
        ctx.warn("input parsed to zero rows", suggestion="check the file is not empty")

    return Grid(values=rows, source=source)


def _decode(data: bytes) -> tuple[str, str]:
    for enc in _ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    # Unreachable in practice: latin-1 decodes anything. Kept for total safety.
    return data.decode("latin-1", errors="replace"), "latin-1"  # pragma: no cover


def _sniff_delimiter(text: str) -> str | None:
    """Pick the delimiter that yields the most *consistent* column count.

    csv.Sniffer is notoriously fooled by preamble rows (a title line, a decimal
    comma inside a semicolon-separated file). The robust signal for messy files
    is structural: the right delimiter splits *most* lines into the same number
    of (≥2) fields. We score each candidate by how many lines agree on a modal
    field count, preferring more fields as a tie-breaker.

    Returns ``None`` when nothing qualifies — the file is a single column, and a
    lone decimal comma must not be mistaken for a delimiter.
    """
    lines = [ln for ln in text[:_SNIFF_SAMPLE].splitlines() if ln.strip()][:200]
    if not lines:
        return None
    quorum = max(1, len(lines) // 2)
    best: str | None = None
    best_score = (-1, -1)
    for delim in _CANDIDATE_DELIMITERS:
        field_counts = [ln.count(delim) + 1 for ln in lines]
        split_lines = sum(1 for fc in field_counts if fc >= 2)
        if split_lines < quorum:
            continue
        modal_count, agreement = Counter(field_counts).most_common(1)[0]
        if modal_count < 2:
            continue
        score = (agreement, modal_count)
        if score > best_score:
            best, best_score = delim, score
    return best


def _name_delimiter(delimiter: str) -> str:
    return {"\t": "tab", ",": "comma", ";": "semicolon", "|": "pipe"}.get(delimiter, delimiter)

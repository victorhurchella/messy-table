"""Input layer: normalise any supported source into a :class:`Grid`.

A source may be a path (``str``/``Path``), raw ``bytes``, or a binary/text
file-like object. We materialise it to bytes once, classify the format by
extension then by magic bytes, and dispatch. This is the only place the
untrusted-input boundary lives, so the size guard runs here for everyone.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, Any

from messy_table.config import Config
from messy_table.context import Context
from messy_table.exceptions import UnsupportedFormatError
from messy_table.grid import Grid
from messy_table.readers.csv import read_csv
from messy_table.readers.xlsx import read_xlsx

_XLSX_MAGIC = b"PK\x03\x04"
Source = str | Path | bytes | bytearray | IO[Any]


def read(source: Source, config: Config, ctx: Context) -> Grid:
    data, origin, suffix = _materialize(source)
    kind = _detect_kind(data, suffix, origin)
    if len(data) > config.max_uncompressed_bytes and kind != "xlsx":
        # xlsx is checked separately (compressed); text formats are checked here.
        raise UnsupportedFormatError(
            f"input is {len(data)} bytes, above the {config.max_uncompressed_bytes}-byte limit "
            "(raise Config.max_uncompressed_bytes if this is expected)"
        )
    if kind == "xlsx":
        return read_xlsx(data, origin, config, ctx)
    return read_csv(data, origin, kind, config, ctx)


def _materialize(source: Source) -> tuple[bytes, str, str]:
    """Return ``(data, origin_name, lowercased_suffix)``."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        try:
            return path.read_bytes(), str(path), path.suffix.lower()
        except FileNotFoundError as exc:
            raise UnsupportedFormatError(f"file not found: {path}") from exc
        except OSError as exc:
            raise UnsupportedFormatError(f"cannot read {path}: {exc}") from exc
    if isinstance(source, (bytes, bytearray)):
        return bytes(source), "<bytes>", ""
    if hasattr(source, "read"):
        raw = source.read()
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        name = getattr(source, "name", "<stream>")
        suffix = Path(name).suffix.lower() if isinstance(name, str) else ""
        return data, str(name), suffix
    raise UnsupportedFormatError(
        f"unsupported source type {type(source).__name__}; "
        "pass a path, bytes, or a file-like object"
    )


def _detect_kind(data: bytes, suffix: str, origin: str) -> str:
    if suffix in (".xlsx", ".xlsm"):
        return "xlsx"
    if suffix == ".tsv":
        return "tsv"
    if suffix == ".csv":
        return "csv"
    if suffix == ".xls":
        raise UnsupportedFormatError(
            "legacy .xls is not supported in v0.1 — convert to .xlsx (xlrd is on the v0.2 roadmap)"
        )
    if suffix in (".ods",):
        raise UnsupportedFormatError(".ods is not supported (roadmap item)")
    # No usable extension: fall back to content sniffing.
    if data[:4] == _XLSX_MAGIC:
        return "xlsx"
    if data.strip():
        return "csv"
    raise UnsupportedFormatError(f"could not determine format of {origin!r} (empty input?)")


__all__ = ["Source", "read"]

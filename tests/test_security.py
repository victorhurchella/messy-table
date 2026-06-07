"""Untrusted-input defences: decompression bombs, cell ceiling, size caps."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from _fixtures import _write_xlsx
from messy_table import Config, UnsupportedFormatError, clean


def _zip_with_payload(payload: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("payload.bin", payload)
    return buf.getvalue()


def test_decompression_ratio_bomb_rejected() -> None:
    bomb = _zip_with_payload(b"\x00" * 2_000_000)  # compresses to almost nothing
    with pytest.raises(UnsupportedFormatError, match="compression ratio"):
        clean(bomb)


def test_absolute_uncompressed_size_rejected() -> None:
    bomb = _zip_with_payload(b"\x00" * 5000)
    cfg = Config(max_uncompressed_bytes=1000, max_compression_ratio=10**9)
    with pytest.raises(UnsupportedFormatError, match="decompression bomb"):
        clean(bomb, config=cfg)


def test_cell_ceiling_rejected(tmp_path: Path) -> None:
    path = _write_xlsx(tmp_path / "small.xlsx", [["a", "b", "c"], [1, 2, 3], [4, 5, 6]])
    with pytest.raises(UnsupportedFormatError, match="cell limit"):
        clean(path, config=Config(max_cells=4))


def test_corrupt_zip_rejected() -> None:
    with pytest.raises(UnsupportedFormatError, match="not a valid"):
        clean(b"PK\x03\x04 corrupt not really a zip")


def test_oversized_text_rejected() -> None:
    data = b"aaa,bbb\n1,2\n3,4\n5,6\n"
    with pytest.raises(UnsupportedFormatError, match="byte limit"):
        clean(data, config=Config(max_uncompressed_bytes=10))


def _xlsx_with_many_merges(n: int, ref: str = "A1:E20") -> bytes:
    import re

    from openpyxl import Workbook

    buf = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    for _ in range(20):
        ws.append(list(range(10)))
    ws.merge_cells("A1:B2")  # ensure a <mergeCells> element exists to rewrite
    wb.save(buf)

    one = f'<mergeCell ref="{ref}"/>'
    block = f'<mergeCells count="{n}">{one * n}</mergeCells>'
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in src.namelist():
            payload = src.read(name)
            if name == "xl/worksheets/sheet1.xml":
                payload = re.sub(
                    rb"<mergeCells.*?</mergeCells>", block.encode(), payload, flags=re.DOTALL
                )
            zf.writestr(name, payload)
    return out.getvalue()


def test_merge_area_amplification_is_bounded() -> None:
    # Thousands of large overlapping merges on a 200-cell sheet. Before the cap
    # this was O(ranges x area) — tens of seconds. Now it is bounded by sheet area.
    import time

    evil = _xlsx_with_many_merges(5000)
    start = time.perf_counter()
    result = clean(evil)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"merge handling took {elapsed:.2f}s (amplification not bounded)"
    assert any("more area than the sheet" in w.message for w in result.warnings)


def test_in_read_cell_cap_independent_of_declared_dimensions() -> None:
    from messy_table.readers.xlsx import _enforce_cell_cap

    _enforce_cell_cap(50, Config(max_cells=100))  # under the cap: fine
    with pytest.raises(UnsupportedFormatError, match="while reading"):
        _enforce_cell_cap(200, Config(max_cells=100))

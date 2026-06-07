"""Acceptance criterion #2: 50k x 30 cleans in under 5 seconds.

Marked ``perf`` so it can be skipped in fast local loops (``-m "not perf"``) but
runs in CI. Generation uses openpyxl's write-only mode so the timer measures
``clean`` itself, not fixture construction. This also exercises the large-sheet
streaming path (and its "merges skipped" warning).
"""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from messy_table import clean

ROWS = 50_000
COLS = 30
BUDGET_SECONDS = 5.0


@pytest.fixture(scope="module")
def big_sheet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A realistic 50k x 30 sheet — i.e. one that carries a ``<dimension>`` tag.

    Every file produced by Excel, Google Sheets, LibreOffice or normal openpyxl
    declares its dimensions. We generate with write-only mode for speed, then
    inject the dimension so the fixture mirrors a real export. (Without it,
    openpyxl scans the sheet XML twice — once to size it, once to read — which is
    a ~50% penalty unrepresentative of real inputs; see ARCHITECTURE.md.)
    """
    buf = io.BytesIO()
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("big")
    ws.append([f"col{c}" for c in range(COLS)])
    for r in range(ROWS):
        ws.append([r * COLS + c for c in range(COLS)])
    wb.save(buf)

    ref = f"A1:{get_column_letter(COLS)}{ROWS + 1}"
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    path = tmp_path_factory.mktemp("perf") / "big.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in src.namelist():
            data = src.read(name)
            if name == "xl/worksheets/sheet1.xml" and b"<dimension" not in data:
                data = data.replace(
                    b"<sheetData>", f'<dimension ref="{ref}"/><sheetData>'.encode(), 1
                )
            zf.writestr(name, data)
    return path


@pytest.mark.perf
def test_large_file_under_budget(big_sheet: Path) -> None:
    start = time.perf_counter()
    result = clean(big_sheet)
    elapsed = time.perf_counter() - start

    assert len(result.data) == ROWS
    assert len(result.columns) == COLS
    assert elapsed < BUDGET_SECONDS, f"clean took {elapsed:.2f}s (budget {BUDGET_SECONDS}s)"


@pytest.mark.perf
def test_large_sheet_warns_merges_skipped(big_sheet: Path) -> None:
    result = clean(big_sheet)
    assert any("merged-cell" in w.message for w in result.warnings)

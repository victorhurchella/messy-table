"""The object returned by :func:`messy_table.clean`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from messy_table.grid import SourceInfo
from messy_table.report import CleanReport, ColumnInfo, Issue, _json_default, _to_jsonable

if TYPE_CHECKING:
    import pandas as pd

_PANDAS_HINT = (
    "to_pandas() needs pandas, which is an optional extra.\n"
    "  → install it with: pip install 'messy-table[pandas]'"
)


@dataclass
class CleanResult:
    """Cleaned, typed data plus the full audit trail.

    Attributes mirror the spec exactly:

    * ``data`` — the cleaned rows, one ``dict`` per row keyed by clean column name.
    * ``columns`` — per-column name/dtype/null summary.
    * ``report`` — every transformation that was applied.
    * ``warnings`` — low-confidence decisions that did not raise.
    """

    data: list[dict[str, Any]]
    columns: list[ColumnInfo]
    report: CleanReport
    warnings: list[Issue]
    source: SourceInfo

    def to_pandas(self) -> pd.DataFrame:
        """Return the data as a pandas ``DataFrame``.

        Raises ``ImportError`` with an install hint if pandas is absent — pandas
        is never a hard dependency of the core.
        """
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
            raise ImportError(_PANDAS_HINT) from exc
        columns = [c.name for c in self.columns]
        return pd.DataFrame(self.data, columns=columns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "columns": [_to_jsonable(c) | {"null_pct": c.null_pct} for c in self.columns],
            "report": self.report.to_dict(),
            "warnings": [_to_jsonable(w) for w in self.warnings],
            "source": _to_jsonable(self.source),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=_json_default, ensure_ascii=False)

    def __repr__(self) -> str:
        return (
            f"CleanResult(rows={len(self.data)}, cols={len(self.columns)}, "
            f"actions={len(self.report)}, warnings={len(self.warnings)})"
        )

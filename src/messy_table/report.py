"""The audit trail.

messy-table's contract: **nothing changes without a record**. Every structural
decision and every value rewrite lands here. Per-cell rewrites (nulls, number
parsing, ...) are *aggregated per (kind, column, rule)* with a count and a bounded
set of examples — otherwise a 50k-row file would emit hundreds of thousands of
records. The aggregation is exact: the reported ``count`` equals the number of
cells actually changed, which the invariant test in the suite verifies.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

EXAMPLE_CAP = 5


class ActionKind(str, Enum):
    """The closed set of transformations messy-table can apply."""

    TABLE_START = "table_start_detected"
    HEADER = "header_detected"
    HEADER_RENAMED = "header_renamed"
    TABLE_END = "table_end_trimmed"
    MERGED_FILLED = "merged_cell_filled"
    NULL_NORMALIZED = "null_normalized"
    NUMBER_PARSED = "number_parsed"
    DATE_CONVERTED = "date_converted"
    TYPE_COERCED = "type_coerced"


class Severity(str, Enum):
    WARNING = "warning"


@dataclass(slots=True)
class ActionExample:
    """A single concrete instance of an action, for human inspection."""

    row: int | None
    col: int | None
    original: Any
    final: Any


@dataclass(slots=True)
class Action:
    """One recorded transformation (possibly aggregating many cells).

    For structural actions (table start, header, trimming) ``count`` is 1 and
    ``detail`` carries the explanation. For per-cell actions ``count`` is the
    number of cells changed and ``examples`` holds up to ``EXAMPLE_CAP`` samples.
    """

    kind: ActionKind
    rule: str
    confidence: float = 1.0
    column: str | None = None
    count: int = 1
    examples: list[ActionExample] = field(default_factory=list)
    detail: str | None = None


@dataclass(slots=True)
class Issue:
    """A low-confidence decision surfaced as a warning (never silent)."""

    message: str
    severity: Severity = Severity.WARNING
    column: str | None = None
    row: int | None = None
    confidence: float | None = None
    suggestion: str | None = None


@dataclass(slots=True)
class ColumnInfo:
    """Per-column summary returned alongside the cleaned data."""

    original_name: str | None
    name: str
    dtype: str  # int | float | date | datetime | bool | str
    null_count: int
    total: int

    @property
    def null_pct(self) -> float:
        return round(self.null_count / self.total, 4) if self.total else 0.0


@dataclass
class CleanReport:
    """The complete, serialisable list of everything messy-table changed."""

    actions: list[Action] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.actions)

    def __iter__(self) -> Any:
        return iter(self.actions)

    def of_kind(self, kind: ActionKind) -> list[Action]:
        return [a for a in self.actions if a.kind == kind]

    def summary(self) -> dict[str, int]:
        """Count of changed cells/rows grouped by action kind."""
        out: dict[str, int] = {}
        for a in self.actions:
            out[a.kind.value] = out.get(a.kind.value, 0) + a.count
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "actions": [_to_jsonable(a) for a in self.actions],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=_json_default, ensure_ascii=False)


class ReportBuilder:
    """Mutable accumulator used by the pipeline; ``build()`` freezes it.

    ``record`` aggregates homogeneous per-cell changes; ``note`` appends a
    one-off structural action. Both preserve first-seen ordering.
    """

    def __init__(self, *, example_cap: int = EXAMPLE_CAP) -> None:
        self._actions: list[Action] = []
        self._batches: dict[tuple[ActionKind, str | None, str], Action] = {}
        self._cap = example_cap

    def record(
        self,
        kind: ActionKind,
        rule: str,
        *,
        column: str | None = None,
        row: int | None = None,
        col: int | None = None,
        original: Any = None,
        final: Any = None,
        confidence: float = 1.0,
    ) -> None:
        key = (kind, column, rule)
        action = self._batches.get(key)
        if action is None:
            action = Action(kind=kind, rule=rule, column=column, count=0, confidence=confidence)
            self._batches[key] = action
            self._actions.append(action)
        action.count += 1
        action.confidence = min(action.confidence, confidence)
        if len(action.examples) < self._cap:
            action.examples.append(ActionExample(row, col, original, final))

    def note(
        self,
        kind: ActionKind,
        rule: str,
        *,
        detail: str,
        column: str | None = None,
        confidence: float = 1.0,
    ) -> Action:
        action = Action(
            kind=kind, rule=rule, column=column, confidence=confidence, count=1, detail=detail
        )
        self._actions.append(action)
        return action

    def build(self) -> CleanReport:
        return CleanReport(actions=self._actions)


# --------------------------------------------------------------------------- #
# JSON serialisation                                                          #
# --------------------------------------------------------------------------- #
def _json_default(obj: Any) -> Any:
    if isinstance(obj, dt.datetime | dt.date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _to_jsonable(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


def _to_jsonable(obj: Any) -> Any:
    """dataclass → dict with enums unwrapped and empty fields pruned."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            if value in ([], None):
                continue
            out[f.name] = _to_jsonable(value)
        return out
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    return obj

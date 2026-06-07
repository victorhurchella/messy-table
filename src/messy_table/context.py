"""Shared, mutable context threaded through every pipeline stage.

Centralising the strict-vs-permissive decision here means each detector and
transformer just calls ``ctx.ambiguous(...)`` when its confidence is low and
never has to know which mode it is running in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from messy_table.config import Config
from messy_table.exceptions import AmbiguityError
from messy_table.grid import SourceInfo
from messy_table.report import Issue, ReportBuilder, Severity


@dataclass
class Context:
    config: Config
    source: SourceInfo
    report: ReportBuilder = field(default_factory=ReportBuilder)
    warnings: list[Issue] = field(default_factory=list)
    # The current header names, mutated as the header transformer runs.
    column_names: list[str] = field(default_factory=list)

    def warn(
        self,
        message: str,
        *,
        column: str | None = None,
        row: int | None = None,
        confidence: float | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.warnings.append(
            Issue(
                message=message,
                severity=Severity.WARNING,
                column=column,
                row=row,
                confidence=confidence,
                suggestion=suggestion,
            )
        )

    def ambiguous(
        self,
        message: str,
        *,
        suggestion: str,
        column: str | None = None,
        row: int | None = None,
        confidence: float | None = None,
    ) -> None:
        """A below-threshold decision: raise in strict mode, else warn.

        ``suggestion`` is mandatory and must be a copy-pasteable ``Config`` hint,
        so the error/warning is always actionable.
        """
        if self.config.strict:
            raise AmbiguityError(message, suggestion=suggestion)
        self.warn(message, column=column, row=row, confidence=confidence, suggestion=suggestion)

"""Exception hierarchy for messy-table.

Every error raised by the public API descends from :class:`MessyTableError`, so
callers can catch the whole family with a single ``except``. Errors that the user
can resolve by changing configuration always carry a concrete ``suggestion``.
"""

from __future__ import annotations


class MessyTableError(Exception):
    """Base class for every error raised by messy-table."""


class UnsupportedFormatError(MessyTableError):
    """Raised when the input is not a format messy-table can read.

    Covers unknown extensions, corrupt archives, and inputs that trip a safety
    guard (for example an ``.xlsx`` that decompresses far beyond its packed size,
    which is the classic decompression-bomb shape).
    """


class AmbiguityError(MessyTableError):
    """Raised in ``strict`` mode when a heuristic cannot decide confidently.

    In permissive mode the same situation is recorded as a low-confidence
    :class:`~messy_table.report.Issue` instead of raising. The ``suggestion`` is
    always a copy-pasteable hint for the ``Config`` field that resolves it.
    """

    def __init__(self, message: str, *, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.suggestion = suggestion

    def __str__(self) -> str:
        base = super().__str__()
        if self.suggestion:
            return f"{base}\n  → resolve with: {self.suggestion}"
        return base

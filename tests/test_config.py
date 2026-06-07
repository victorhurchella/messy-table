"""Config validation."""

from __future__ import annotations

import pytest

from messy_table import Config, MessyTableError


def test_valid_config() -> None:
    cfg = Config(locale="pt_BR", header=3, merged_cells="first-only", strict=True)
    assert cfg.header == 3


def test_bad_merged_cells() -> None:
    with pytest.raises(MessyTableError, match="merged_cells"):
        Config(merged_cells="nope")  # type: ignore[arg-type]


def test_bad_confidence_threshold() -> None:
    with pytest.raises(MessyTableError, match="confidence_threshold"):
        Config(confidence_threshold=1.5)


def test_negative_header_index() -> None:
    with pytest.raises(MessyTableError, match="header row index"):
        Config(header=-1)


def test_bad_safety_limits() -> None:
    with pytest.raises(MessyTableError, match="safety limits"):
        Config(max_cells=0)

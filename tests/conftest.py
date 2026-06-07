"""Shared pytest fixtures: build every catalogue fixture once per session."""

from __future__ import annotations

from pathlib import Path

import pytest

from _fixtures import FIXTURES


@pytest.fixture(scope="session")
def built_fixtures(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("fixtures")
    return {fx.name: fx.build(directory / fx.name) for fx in FIXTURES}

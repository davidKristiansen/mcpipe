"""Shared fixtures for mcpipe tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect cache to a temp dir so tests don't pollute /tmp/mcpipe."""
    cache_dir = tmp_path / "mcpipe_cache"
    cache_dir.mkdir()
    monkeypatch.setattr("mcpipe.cache.CACHE_DIR", cache_dir)
    return cache_dir

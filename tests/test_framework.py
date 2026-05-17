"""Tests for mcpipe.framework — view, handles tool functions."""

from __future__ import annotations

from mcpipe.cache import store
from mcpipe.framework import handles, view


class TestView:
    def test_returns_content(self, tmp_cache):
        handle = store("t", "a\nb\nc\nd\ne")
        result = view(handle=handle)
        assert "a" in result
        assert "e" in result

    def test_missing_handle(self, tmp_cache):
        result = view(handle="nonexistent_xyz")
        assert "Error" in result


class TestHandles:
    def test_lists_active(self, tmp_cache):
        h1 = store("a", "x")
        h2 = store("b", "y")
        result = handles()
        assert h1 in result
        assert h2 in result

    def test_empty(self, tmp_cache):
        result = handles()
        assert "No cached outputs" in result

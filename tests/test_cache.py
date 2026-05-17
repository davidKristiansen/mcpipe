"""Tests for mcpipe.cache — store, load, evict_expired, list_handles, CachedOutput."""

from __future__ import annotations

import time

import pytest

from mcpipe.cache import CachedOutput, evict_expired, list_handles, load, store


class TestStore:
    def test_returns_handle(self, tmp_cache):
        handle = store("mytool", "line1\nline2\n")
        assert handle.startswith("mytool_")

    def test_creates_data_and_meta_files(self, tmp_cache):
        handle = store("mytool", "hello")
        assert (tmp_cache / handle).exists()
        assert (tmp_cache / f"{handle}.meta").exists()

    def test_data_content_matches(self, tmp_cache):
        handle = store("mytool", "hello world")
        assert (tmp_cache / handle).read_text() == "hello world"

    def test_custom_ttl(self, tmp_cache):
        handle = store("mytool", "x", ttl=42)
        meta = (tmp_cache / f"{handle}.meta").read_text().strip().split("\n")
        assert meta[1] == "42"


class TestLoad:
    def test_roundtrip(self, tmp_cache):
        handle = store("t", "a\nb\nc")
        cached = load(handle)
        assert cached.handle == handle
        assert cached.lines == ["a", "b", "c"]
        assert cached.total_lines == 3

    def test_missing_handle_raises(self, tmp_cache):
        with pytest.raises(FileNotFoundError):
            load("nonexistent_handle")


class TestCachedOutput:
    def test_slice(self):
        co = CachedOutput(
            handle="h", lines=["a", "b", "c", "d"],
            total_lines=4, created_at=0,
        )
        assert co.slice(1, 2) == ["b", "c"]

    def test_slice_beyond_end(self):
        co = CachedOutput(handle="h", lines=["a", "b"], total_lines=2, created_at=0)
        assert co.slice(0, 100) == ["a", "b"]

    def test_search_matches(self):
        co = CachedOutput(
            handle="h", lines=["foo bar", "baz", "foobar"],
            total_lines=3, created_at=0,
        )
        matches = co.search("foo")
        assert len(matches) == 2
        assert matches[0] == (0, "foo bar")
        assert matches[1] == (2, "foobar")

    def test_search_no_match(self):
        co = CachedOutput(handle="h", lines=["a", "b"], total_lines=2, created_at=0)
        assert co.search("zzz") == []

    def test_search_case_insensitive(self):
        co = CachedOutput(
            handle="h", lines=["Hello", "HELLO", "world"],
            total_lines=3, created_at=0,
        )
        assert len(co.search("hello")) == 2


class TestGc:
    def test_removes_expired(self, tmp_cache):
        handle = store("old", "data", ttl=1)
        # Backdate the meta file
        meta = tmp_cache / f"{handle}.meta"
        meta.write_text(f"{int(time.time()) - 100}\n1\n")
        removed = evict_expired()
        assert removed == 1
        assert not (tmp_cache / handle).exists()

    def test_keeps_fresh(self, tmp_cache):
        handle = store("fresh", "data", ttl=3600)
        removed = evict_expired()
        assert removed == 0
        assert (tmp_cache / handle).exists()


class TestListHandles:
    def test_returns_active(self, tmp_cache):
        h1 = store("a", "x")
        h2 = store("b", "y")
        active = list_handles()
        assert h1 in active
        assert h2 in active

    def test_excludes_expired(self, tmp_cache):
        handle = store("old", "data", ttl=1)
        meta = tmp_cache / f"{handle}.meta"
        meta.write_text(f"{int(time.time()) - 100}\n1\n")
        active = list_handles()
        assert handle not in active

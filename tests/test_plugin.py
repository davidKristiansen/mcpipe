"""Tests for mcpipe.plugin — @tool decorator, schema generation, execute."""

from __future__ import annotations

import asyncio
from typing import Annotated

import pytest

from mcpipe.plugin import (
    INLINE_THRESHOLD,
    Cmd,
    ToolOutput,
    _build_schema,
    _make_preview,
    _sanitize_args,
    execute,
    get_tools,
    tool,
)
from mcpipe.transform import TransformStep

# ---------------------------------------------------------------------------
# ToolOutput
# ---------------------------------------------------------------------------


class TestToolOutput:
    def test_is_inline_when_text_set(self):
        out = ToolOutput(handle="h", text="hello")
        assert out.is_inline is True

    def test_not_inline_when_text_none(self):
        out = ToolOutput(handle="h", total_lines=100, preview="first lines")
        assert out.is_inline is False


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------


class TestBuildSchema:
    def test_simple_types(self):
        def fn(name: str, count: int, flag: bool = False):
            pass

        schema = _build_schema(fn)
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["flag"]["type"] == "boolean"
        assert schema["properties"]["flag"]["default"] is False
        assert schema["required"] == ["name", "count"]

    def test_annotated_description(self):
        def fn(path: Annotated[str, "Path to the file"]):
            pass

        schema = _build_schema(fn)
        assert schema["properties"]["path"]["description"] == "Path to the file"

    def test_no_required_when_all_defaults(self):
        def fn(a: str = "x", b: int = 0):
            pass

        schema = _build_schema(fn)
        assert "required" not in schema


# ---------------------------------------------------------------------------
# _sanitize_args
# ---------------------------------------------------------------------------


class TestSanitizeArgs:
    def test_expands_home(self):
        result = _sanitize_args({"path": "~/foo"})
        assert "~" not in result["path"]
        assert result["path"].endswith("/foo")

    def test_non_string_passthrough(self):
        result = _sanitize_args({"count": 42, "flag": True})
        assert result == {"count": 42, "flag": True}


# ---------------------------------------------------------------------------
# _make_preview
# ---------------------------------------------------------------------------


class TestMakePreview:
    def test_truncates(self):
        lines = "\n".join(f"line{i}" for i in range(100))
        preview = _make_preview(lines, max_lines=3)
        assert preview == "line0\nline1\nline2"


# ---------------------------------------------------------------------------
# @tool decorator + execute
# ---------------------------------------------------------------------------


class TestToolDecorator:
    def test_registers_tool(self):
        @tool("A test tool", read_only=True, destructive=False)
        def _test_tool_reg(x: Annotated[str, "input"]) -> str:
            return x

        tools = get_tools()
        assert "_test_tool_reg" in tools
        entry = tools["_test_tool_reg"]
        assert entry.tool.description == "A test tool"
        assert entry.tool.annotations.read_only is True
        assert entry.tool.annotations.destructive is False

    def test_schema_is_set(self):
        @tool("schema test")
        def _test_tool_schema(a: str, b: int = 5) -> str:
            return ""

        entry = get_tools()["_test_tool_schema"]
        assert entry.tool.input_schema["properties"]["a"]["type"] == "string"
        assert entry.tool.input_schema["properties"]["b"]["default"] == 5


class TestExecute:
    def test_str_return_inline(self, tmp_cache):
        @tool("inline test")
        def _test_exec_inline(msg: str) -> str:
            return msg

        output = asyncio.run(execute("_test_exec_inline", {"msg": "hi"}))
        assert output.is_inline
        assert output.text == "hi"
        assert output.handle.startswith("_test_exec_inline_")

    def test_large_output_not_inline(self, tmp_cache):
        @tool("large test")
        def _test_exec_large() -> str:
            return "\n".join(f"line{i}" for i in range(INLINE_THRESHOLD + 10))

        output = asyncio.run(execute("_test_exec_large", {}))
        assert not output.is_inline
        assert output.preview is not None
        assert output.total_lines > INLINE_THRESHOLD

    def test_cmd_echo(self, tmp_cache):
        @tool("cmd test")
        def _test_exec_cmd() -> Cmd:
            return Cmd("echo", "hello from cmd")

        output = asyncio.run(execute("_test_exec_cmd", {}))
        assert "hello from cmd" in (output.text or "")

    def test_cmd_failure(self, tmp_cache):
        @tool("fail test")
        def _test_exec_fail() -> Cmd:
            return Cmd("false")

        output = asyncio.run(execute("_test_exec_fail", {}))
        assert output.is_error

    def test_unknown_tool_raises(self, tmp_cache):
        with pytest.raises(ValueError, match="Unknown tool"):
            asyncio.run(execute("nonexistent_tool_xyz", {}))

    def test_transform_search(self, tmp_cache):
        from mcpipe.bootstrap import bootstrap
        bootstrap()

        @tool("pipe search test")
        def _test_pipe_search() -> str:
            return "apple\nbanana\ncherry\napricot"

        transforms = [TransformStep(name="search", params={"pattern": "ap"})]
        output = asyncio.run(
            execute("_test_pipe_search", {}, transforms=transforms),
        )
        assert output.is_inline
        assert output.text is not None
        assert "apple" in output.text
        assert "apricot" in output.text
        assert "banana" not in output.text

    def test_transform_paginate(self, tmp_cache):
        from mcpipe.bootstrap import bootstrap
        bootstrap()
        @tool("pipe paginate test")
        def _test_pipe_paginate() -> str:
            return "\n".join(f"line{i}" for i in range(20))

        transforms = [
            TransformStep(name="offset", params={"n": "5"}),
            TransformStep(name="limit", params={"n": "3"}),
        ]
        output = asyncio.run(
            execute("_test_pipe_paginate", {}, transforms=transforms),
        )
        assert output.text is not None
        assert "line5" in output.text
        assert "line7" in output.text
        assert "line8" not in output.text

    def test_transform_search_no_match(self, tmp_cache):
        from mcpipe.bootstrap import bootstrap
        bootstrap()
        @tool("pipe no match test")
        def _test_pipe_nomatch() -> str:
            return "aaa\nbbb\nccc"

        transforms = [TransformStep(name="search", params={"pattern": "zzz"})]
        output = asyncio.run(
            execute("_test_pipe_nomatch", {}, transforms=transforms),
        )
        assert output.text == ""

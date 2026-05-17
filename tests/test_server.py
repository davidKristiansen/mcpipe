"""Tests for mcpipe.server — camelCase serialization, dispatch, handlers."""

from __future__ import annotations

import asyncio

from mcpipe.server import _camel, _dispatch, _handle_initialize, _to_json
from mcpipe.types.protocol import (
    ErrorCode,
    InitializeResult,
    ServerCapabilities,
    ServerInfo,
    TextContent,
    Tool,
    ToolAnnotations,
    ToolResult,
)

# ---------------------------------------------------------------------------
# _camel
# ---------------------------------------------------------------------------


class TestCamel:
    def test_single_word(self):
        assert _camel("name") == "name"

    def test_two_words(self):
        assert _camel("server_info") == "serverInfo"

    def test_three_words(self):
        assert _camel("protocol_version_number") == "protocolVersionNumber"

    def test_already_camel(self):
        # Single word — no underscores — passes through
        assert _camel("tools") == "tools"


# ---------------------------------------------------------------------------
# _to_json
# ---------------------------------------------------------------------------


class TestToJson:
    def test_initialize_result_camel_keys(self):
        result = InitializeResult(
            capabilities=ServerCapabilities(),
            server_info=ServerInfo(name="test", version="1.0"),
        )
        j = _to_json(result)
        assert "protocolVersion" in j
        assert "serverInfo" in j
        assert "server_info" not in j
        assert "protocol_version" not in j
        assert j["serverInfo"]["name"] == "test"

    def test_tool_annotations_camel(self):
        ann = ToolAnnotations(read_only=True, destructive=False, open_world=False)
        j = _to_json(ann)
        assert "readOnly" in j
        assert "openWorld" in j
        assert "read_only" not in j

    def test_tool_input_schema_camel(self):
        t = Tool(name="test", description="d", input_schema={"type": "object"})
        j = _to_json(t)
        assert "inputSchema" in j
        assert "input_schema" not in j

    def test_none_fields_omitted(self):
        t = Tool(name="t", description="d", output_schema=None)
        j = _to_json(t)
        assert "outputSchema" not in j

    def test_tool_result_camel(self):
        tr = ToolResult(
            content=[TextContent(text="hi")],
            is_error=False,
        )
        j = _to_json(tr)
        # is_error=False is not None, so it should be present as isError
        assert "isError" in j
        assert j["isError"] is False

    def test_list_of_dataclasses(self):
        items = [TextContent(text="a"), TextContent(text="b")]
        j = _to_json(items)
        assert j == [{"text": "a", "type": "text"}, {"text": "b", "type": "text"}]

    def test_plain_dict_passthrough(self):
        d = {"key": "value", "none_key": None}
        j = _to_json(d)
        # dict keys are NOT camelCased (only dataclass fields are)
        assert j == {"key": "value"}  # None removed


# ---------------------------------------------------------------------------
# _handle_initialize
# ---------------------------------------------------------------------------


class TestHandleInitialize:
    def test_response_structure(self):
        resp = _handle_initialize(req_id=1)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        result = resp["result"]
        assert "protocolVersion" in result
        assert "serverInfo" in result
        assert "capabilities" in result

    def test_protocol_version_is_string(self):
        resp = _handle_initialize(req_id=1)
        assert isinstance(resp["result"]["protocolVersion"], str)

    def test_server_info_has_name_version(self):
        resp = _handle_initialize(req_id=1)
        si = resp["result"]["serverInfo"]
        assert "name" in si
        assert "version" in si


# ---------------------------------------------------------------------------
# _dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_initialize(self):
        resp = asyncio.run(
            _dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        )
        assert resp is not None
        assert resp["result"]["protocolVersion"]

    def test_ping(self):
        resp = asyncio.run(
            _dispatch({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
        )
        assert resp is not None
        assert resp["result"] == {}

    def test_unknown_method(self):
        resp = asyncio.run(
            _dispatch({"jsonrpc": "2.0", "id": 3, "method": "bogus", "params": {}})
        )
        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == ErrorCode.METHOD_NOT_FOUND.value

    def test_notification_returns_none(self):
        resp = asyncio.run(
            _dispatch({"method": "notifications/initialized", "params": {}})
        )
        assert resp is None

    def test_tools_list(self, tmp_cache):
        # Bootstrap to register tools
        from mcpipe.bootstrap import bootstrap

        bootstrap()
        resp = asyncio.run(
            _dispatch({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
        )
        assert resp is not None
        tools = resp["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0
        # Check all tools have camelCase keys
        for t in tools:
            assert "inputSchema" in t
            assert "input_schema" not in t

    def test_tools_call_unknown_tool(self, tmp_cache):
        resp = asyncio.run(
            _dispatch({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "no_such_tool_xyz"},
            })
        )
        assert resp is not None
        assert "error" in resp

    def test_tools_call_missing_name(self, tmp_cache):
        resp = asyncio.run(
            _dispatch({
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {},
            })
        )
        assert resp is not None
        assert "error" in resp

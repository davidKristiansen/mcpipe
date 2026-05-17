def test_import():
    from mcpipe import Cmd, SinkPreference, tool

    assert callable(tool)
    assert Cmd is not None
    assert SinkPreference.FILE == "file"

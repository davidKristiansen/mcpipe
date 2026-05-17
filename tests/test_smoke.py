def test_import():
    from mcpipe import Cmd, tool

    assert callable(tool)
    assert Cmd is not None

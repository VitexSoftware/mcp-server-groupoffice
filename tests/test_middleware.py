import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from groupoffice_mcp_server.server import MUTATING_TOOLS


class TestReadOnlyGuard:
    async def test_mutating_tool_blocked_in_read_only_mode(self, server, mock_client):
        async with Client(server) as c:
            with pytest.raises(ToolError, match="read-only"):
                await c.call_tool("delete_contact", {"contact_id": "1"})
        mock_client.set.assert_not_called()

    async def test_mutating_tool_allowed_when_readonly_disabled(self, writable_server, mock_client):
        mock_client.set.return_value = {"destroyed": ["1"]}
        async with Client(writable_server) as c:
            result = await c.call_tool("delete_contact", {"contact_id": "1"})
        assert result.is_error is False
        mock_client.set.assert_called_once_with("Contact", destroy=["1"])

    async def test_read_only_tool_never_blocked(self, server, mock_client):
        mock_client.get.return_value = {"list": [{"id": "1"}], "notFound": []}
        async with Client(server) as c:
            result = await c.call_tool("get_contact", {"contact_id": "1"})
        assert result.is_error is False
        mock_client.get.assert_called_once()

    async def test_read_only_tool_not_blocked_even_in_writable_mode(
        self, writable_server, mock_client
    ):
        mock_client.get.return_value = {"list": [{"id": "1"}], "notFound": []}
        async with Client(writable_server) as c:
            result = await c.call_tool("get_contact", {"contact_id": "1"})
        assert result.is_error is False


class TestMutatingToolsRegistryConsistency:
    async def test_registry_matches_annotations(self, server):
        tools = await server.list_tools()
        for tool in tools:
            is_read_only = bool(tool.annotations and tool.annotations.read_only_hint)
            expected_mutating = tool.name in MUTATING_TOOLS
            assert expected_mutating != is_read_only, (
                f"'{tool.name}': MUTATING_TOOLS membership ({expected_mutating}) "
                f"disagrees with annotations.read_only_hint ({is_read_only})"
            )

    async def test_all_annotation_hints_are_bool(self, server):
        tools = await server.list_tools()
        for tool in tools:
            assert tool.annotations is not None, f"'{tool.name}' has no annotations"
            for field in (
                "read_only_hint",
                "destructive_hint",
                "idempotent_hint",
                "open_world_hint",
            ):
                value = getattr(tool.annotations, field)
                assert isinstance(value, bool), f"'{tool.name}'.{field} is {value!r}, not bool"

import json

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp_types import TextContent

from .config import GroupOfficeConfig


class ReadOnlyGuardMiddleware(Middleware):
    """Blocks any tool whose annotations.read_only_hint is not True when
    config.read_only is enabled (the default).

    This runs for every `tools/call` request server-wide (FastMCP's
    middleware chain is a genuine single choke point), so enforcement is
    driven directly by the same ToolAnnotations every tool must already
    declare - there is no separately-maintained call-site allowlist that
    could fall out of sync with what a tool actually does.
    """

    def __init__(self, config: GroupOfficeConfig):
        self._config = config

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        if not self._config.read_only:
            return await call_next(context)

        tool_name = context.message.name
        tool = await context.fastmcp_context.fastmcp.get_tool(tool_name)
        is_read_only = bool(tool.annotations and tool.annotations.read_only_hint)

        if not is_read_only:
            payload = {
                "error": True,
                "tool": tool_name,
                "message": (
                    f"Tool '{tool_name}' is disabled: the server is running in "
                    "read-only mode (default). Set GROUPOFFICE_READONLY=false "
                    "to allow writes."
                ),
            }
            return ToolResult(
                content=[TextContent(type="text", text=json.dumps(payload, indent=2))],
                structured_content=payload,
                is_error=True,
            )
        return await call_next(context)

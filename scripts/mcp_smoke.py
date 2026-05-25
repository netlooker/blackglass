from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main() -> None:
    await _retry(_smoke_once)


async def _retry(operation: Callable[[], Awaitable[None]]) -> None:
    last_error: BaseException | None = None
    for _ in range(30):
        try:
            await operation()
            return
        except BaseException as exc:
            last_error = exc
            await asyncio.sleep(1)
    assert last_error is not None
    raise last_error


async def _smoke_once() -> None:
    async with streamablehttp_client("http://127.0.0.1:8011/mcp") as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = sorted(tool.name for tool in tools.tools)
            assert tool_names == ["health", "retrieve"], tool_names

            health = await session.call_tool("health", {})
            assert health.isError is False
            assert health.structuredContent["ready"] is True

            retrieved = await session.call_tool(
                "retrieve",
                {"url": "https://example.com/article", "profile": "auto"},
            )
            assert retrieved.isError is False
            assert retrieved.structuredContent["artifact_id"].startswith("bg_")
            assert "policy" in retrieved.structuredContent


if __name__ == "__main__":
    asyncio.run(main())

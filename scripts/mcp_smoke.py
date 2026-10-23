"""Smoke-test the Storykeeper MCP server over Streamable HTTP: python scripts/mcp_smoke.py [url]"""
import asyncio
import os
import sys

from mcp import Client


async def main(url: str):
    async with Client(url) as client:
        tools = await client.list_tools()
        print("tools:", [t.name for t in tools.tools])
        for name, args in [("list_family", {}),
                           ("next_interview_question", {"elder_name": "Nanaji"}),
                           ("ask_family_archive", {"question": "How does Nani make mango pickle?"})]:
            res = await client.call_tool(name, args)
            print(f"\n{name} ->", (res.structured_content or res.content[0].text).__str__()[:400])


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MCP_URL", "http://127.0.0.1:8787/mcp")))

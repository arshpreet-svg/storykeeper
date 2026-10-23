"""Vercel entry point: the same Storykeeper app as a serverless ASGI function.

Serverless instances are short-lived, so the MCP endpoint runs stateless (every request stands alone, JSON
responses), the SQLite archive lives in /tmp and is seeded with the demo family on a cold start, and nothing a
visitor adds is kept for long. Run `python -m storykeeper.server` for a persistent deployment.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("STORYKEEPER_DB", "/tmp/storykeeper/storykeeper.db")
os.environ.setdefault("STORYKEEPER_MODE", "offline")

from storykeeper import seed, store  # noqa: E402
from storykeeper.server import mcp  # noqa: E402

if not store.DB_PATH.exists():
    seed.main()


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while (msg := await receive())["type"] != "lifespan.shutdown":
            await send({"type": "lifespan.startup.complete"})
        await send({"type": "lifespan.shutdown.complete"})
        return
    # A fresh app per request: its session manager can only run once, and nothing should outlive the request.
    # host="0.0.0.0" turns off the localhost-only Host check so the public Vercel domain is accepted.
    inner = mcp.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")
    async with inner.router.lifespan_context(inner):
        await inner(scope, receive, send)

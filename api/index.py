"""Vercel entry point: the same Storykeeper app as a serverless ASGI function.

Serverless instances are short-lived, so the MCP endpoint runs stateless (every request stands alone, JSON
responses), the SQLite archive lives in /tmp and is seeded with the demo family on a cold start, and nothing a
visitor adds is kept for long. Run `python -m storykeeper.server` for a persistent deployment.
"""

import os
import sys
from urllib.parse import unquote
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
    # vercel.json rewrites every URL to this function and passes the original path as ?__path=, so put it back.
    query = [kv for kv in scope.get("query_string", b"").split(b"&") if kv]
    original = [kv for kv in query if kv.startswith(b"__path=")]
    if original:
        path = unquote(original[0][len(b"__path="):].decode())
        rest = b"&".join(kv for kv in query if not kv.startswith(b"__path="))
        scope = dict(scope, path=path, raw_path=path.encode(), query_string=rest)
    # A fresh app per request: its session manager can only run once, and nothing should outlive the request.
    # host="0.0.0.0" turns off the localhost-only Host check so the public Vercel domain is accepted.
    inner = mcp.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")
    async with inner.router.lifespan_context(inner):
        await inner(scope, receive, send)

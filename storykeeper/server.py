"""Storykeeper MCP server (Streamable HTTP at /mcp) plus the family web app at /."""

import base64
import binascii
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from . import brain, gaps, store

WEB = Path(__file__).resolve().parent.parent / "web"

HANDBOOK_SHELVES = {"memoir": ["story"], "health": ["health"], "essentials": ["vault", "wisdom"], "recipes": ["recipe"]}

mcp = MCPServer(
    name="storykeeper",
    title="Storykeeper",
    description="A family's living memory: elders tell Alexa their stories, recipes, health history and where "
                "important things are kept; the family can ask about them any time.",
    instructions=(
        "Use Storykeeper when an elder wants to share a memory or be interviewed, or when a family member asks "
        "about an elder's life, recipes, health history or where something is kept.\n"
        "Interview loop: call next_interview_question, speak the question, then pass the elder's full spoken "
        "answer to save_memory and speak back its `say` field. Repeat if they want to continue.\n"
        "For family questions call ask_family_archive and speak its `say` field."
    ),
    version="1.0.0",
)


def _elder_or_error(conn, name: str | None) -> dict:
    elder = store.find_elder(conn, name)
    if not elder:
        names = ", ".join(e["name"] for e in store.list_elders(conn)) or "none yet"
        raise ValueError(f"No elder called '{name}'. Elders in this family: {names}.")
    return elder


# ------------------------------------------------------------------ core logic (shared by MCP + web)

def do_gaps(elder_name: str | None) -> dict:
    conn = store.connect()
    elder = _elder_or_error(conn, elder_name)
    ranked = gaps.rank(elder, store.list_memories(conn, elder["id"]), store.recent_questions(conn, elder["id"]))
    return {"elder": elder["name"], "gaps": ranked}


async def do_next_question(elder_name: str | None, gap_key: str | None = None) -> dict:
    conn = store.connect()
    elder = _elder_or_error(conn, elder_name)
    memories, asked = store.list_memories(conn, elder["id"]), store.recent_questions(conn, elder["id"])
    ranked = gaps.rank(elder, memories, asked)
    chosen = next((g for g in ranked if g["key"] == gap_key), None)
    if chosen:  # the family picked this gap on the dashboard
        q = {"question": chosen["question"], "shelf": chosen["shelf"], "why": chosen["why"]}
    else:
        q = await brain.next_question(elder, memories, asked, ranked)
    store.record_question(conn, elder["id"], q["question"], q["shelf"])
    top = chosen or (ranked[0] if ranked else None)
    return {"elder": elder["name"], "say": q["question"], "shelf": q["shelf"], "gap": q["why"],
            "score": top["score"] if top else None}


async def do_save(elder_name: str | None, what_they_said: str, source: str = "alexa") -> dict:
    conn = store.connect()
    elder = _elder_or_error(conn, elder_name)
    clean, redacted = store.redact(what_they_said)
    info = await brain.understand(elder, clean)
    details = {k: info[k] for k in ("ingredients", "steps", "condition", "onset_age", "medicines", "item",
                                    "location", "contact") if info.get(k)}
    mem = store.add_memory(conn, elder["id"], info["shelf"], info["title"], clean, info["summary"], info["year"],
                           info["place"], info["people"], details, redacted, language=info.get("language"),
                           translation=info.get("translation"), source=source)
    say = info["acknowledgement"]
    if redacted:
        say += " I left out the numbers - I only keep where things are, not the secrets."
    disputes = [c for c in store.conflicts(conn) if mem["id"] in (c["a"], c["b"])]
    for c in disputes:
        other = next(v for v in c["versions"] if v["id"] != mem["id"])
        say += f" {other['elder']} remembers that as {other['value']} - I've kept both versions for the family."
    return {"say": say, "memory": mem, "conflicts": disputes}


async def do_ask(question: str) -> dict:
    conn = store.connect()
    hits = store.search(conn, question)
    ids = {m["id"] for m in hits}
    disputed = [c for c in store.conflicts(conn) if c["a"] in ids or c["b"] in ids]
    for c in disputed:  # bring in the other version even if the search missed it
        for mid in (c["a"], c["b"]):
            if mid not in ids:
                hits.append(store.get_memory(conn, mid))
                ids.add(mid)
    res = await brain.answer(question, hits, disputed)
    used = [m for m in hits if m["id"] in set(res["sources"])] or hits[:1]
    return {"say": res["answer"], "conflicts": disputed,
            "sources": [{"id": m["id"], "elder": m["elder"], "title": m["title"], "shelf": m["shelf"],
                         "year": m["year"], "provenance": store.provenance(m)} for m in used]}


def do_timeline(elder_name: str | None) -> dict:
    conn = store.connect()
    elder = _elder_or_error(conn, elder_name)
    mems = store.list_memories(conn, elder["id"])
    return {"elder": elder, "events": [{"id": m["id"], "year": m["year"], "title": m["title"], "shelf": m["shelf"],
                                        "place": m["place"], "summary": m["summary"]} for m in mems if m["year"]]}


async def do_handbook(section: str, elder_name: str | None) -> dict:
    if section not in HANDBOOK_SHELVES:
        raise ValueError(f"section must be one of {list(HANDBOOK_SHELVES)}")
    conn = store.connect()
    elder_id = _elder_or_error(conn, elder_name)["id"] if elder_name else None
    mems = [m for s in HANDBOOK_SHELVES[section] for m in store.list_memories(conn, elder_id, s)]
    mems.sort(key=lambda m: (m["year"] or 9999))
    return {"section": section, "markdown": await brain.handbook(section, mems), "memory_count": len(mems)}


# ------------------------------------------------------------------ MCP tools

@mcp.tool(title="Next interview question")
async def next_interview_question(elder_name: str = "") -> dict:
    """Plan the single best next question to ask an elder, balancing practical gaps (health history, where
    documents are kept, recipes, trusted people) with untold chapters of their life. Speak the `say` field.

    Args:
        elder_name: Who is being interviewed, e.g. "Nanaji". Defaults to the first elder in the family.
    """
    return await do_next_question(elder_name or None)


@mcp.tool(title="Memory gaps")
async def get_memory_gaps(elder_name: str = "") -> dict:
    """Rank what the family has NOT recorded yet for an elder - missing allergies, unknown document locations,
    untold decades, medicines due for a recheck - each with a score (importance x uncertainty x freshness) and a
    suggested question."""
    return do_gaps(elder_name or None)


@mcp.tool(title="Save memory")
async def save_memory(what_they_said: str, elder_name: str = "") -> dict:
    """Save what an elder just said. Amazon Nova on Bedrock files it onto the right shelf (story, recipe, health,
    where-things-are, wisdom), dates it and extracts details. Account numbers, PINs and passwords are stripped
    before anything is stored. Speak the `say` field back to the elder.

    Args:
        what_they_said: The elder's full spoken answer, verbatim, in whatever language mix they used
            (Punjabi-English, Hindi-English, ...). The original is kept and an English translation added.
        elder_name: Who is speaking, e.g. "Nani".
    """
    return await do_save(elder_name or None, what_they_said)


@mcp.tool(title="Ask the family archive")
async def ask_family_archive(question: str) -> dict:
    """Answer a family member's question from the elders' own recorded words, e.g. "how does Nani make mango
    pickle", "does diabetes run in our family", "where are Nanaji's house papers". Every answer cites its source
    memories; when elders remember something differently, both versions are given. Speak the `say` field."""
    return await do_ask(question)


@mcp.tool(title="Life timeline")
async def get_life_timeline(elder_name: str = "") -> dict:
    """List an elder's dated memories in order, to retell their life or see which decades are still untold."""
    return do_timeline(elder_name or None)


@mcp.tool(title="Family handbook")
async def get_family_handbook(section: str, elder_name: str = "") -> dict:
    """Compile a printable document from the archive.

    Args:
        section: "memoir" (a memoir chapter), "health" (family health history for doctors), "essentials"
            (where papers, insurance and keys are and who to call), or "recipes" (family recipe book).
        elder_name: Limit to one elder; empty for the whole family.
    """
    return await do_handbook(section, elder_name or None)


@mcp.tool(title="Family members")
async def list_family() -> dict:
    """List the elders in this family and how much of each shelf has been recorded for them."""
    return {"elders": store.list_elders(store.connect()), "shelves": store.SHELVES}


@mcp.tool(title="Family graph")
async def get_family_graph() -> dict:
    """How the family's people, places and historical events connect through recorded memories, e.g. who appears in
    Nanaji's and Nani's stories, and which places they share. Each link lists the memory ids behind it."""
    return store.graph(store.connect())


@mcp.tool(title="Suggest a correction")
async def suggest_correction(memory_id: int, field: str, new_value: str, suggested_by: str, reason: str = "") -> dict:
    """A relative proposes a correction to a memory (title, year, place, summary or people). Nothing changes until
    the elder approves it, and their original words are never edited.

    Args:
        memory_id: The memory to correct (ids come from ask_family_archive sources or get_life_timeline).
        field: "title", "year", "place", "summary" or "people" (comma-separated names).
        new_value: The proposed value.
        suggested_by: Who is suggesting it, e.g. "Simran (granddaughter)".
        reason: Why, e.g. "The wedding card says 1970".
    """
    sug = store.suggest(store.connect(), memory_id, suggested_by, field, new_value, reason)
    return {"say": f"Thanks {sug['author']}. I've sent that to {store.get_memory(store.connect(), memory_id)['elder']} "
                   "to approve - nothing changes until they say yes.", "suggestion": sug}


@mcp.tool(title="Review a suggested correction")
async def review_suggestion(suggestion_id: int = 0, approve: bool = False, decided_by: str = "") -> dict:
    """For the elder (or their guardian): list pending corrections when suggestion_id is 0, otherwise approve or
    decline one. Approved changes update the memory; the full history is kept."""
    conn = store.connect()
    if not suggestion_id:
        pending = store.suggestions_for(conn, status="pending")
        return {"pending": pending, "say": f"There {'is' if len(pending) == 1 else 'are'} {len(pending) or 'no'} "
                                           f"suggested correction{'' if len(pending) == 1 else 's'} waiting."}
    res = store.decide(conn, suggestion_id, approve, decided_by or "the elder")
    return {"suggestion": res, "say": "Done, I've updated it." if approve else "Okay, I've left it as it was."}


# ------------------------------------------------------------------ web app + JSON API

async def _json(request: Request) -> dict:
    try:
        return await request.json()
    except ValueError:
        return {}


def _api(handler):
    async def wrapped(request: Request) -> Response:
        try:
            return JSONResponse(await handler(request))
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    return wrapped


@mcp.custom_route("/", methods=["GET"])
async def index(request: Request) -> Response:
    return FileResponse(WEB / "index.html")


@mcp.custom_route("/media/{name}", methods=["GET"])
async def media(request: Request) -> Response:
    path = (store.MEDIA_DIR / request.path_params["name"]).resolve()
    if store.MEDIA_DIR.resolve() not in path.parents or not path.is_file():
        return Response(status_code=404)
    return FileResponse(path)


@mcp.custom_route("/static/{name:path}", methods=["GET"])
async def static(request: Request) -> Response:
    path = (WEB / request.path_params["name"]).resolve()
    if WEB not in path.parents or not path.is_file():
        return Response(status_code=404)
    return FileResponse(path)


async def _status(request):
    return {**brain.status, "mcp_endpoint": "/mcp"}


async def _family(request):
    return {"elders": store.list_elders(store.connect()), "shelves": store.SHELVES}


async def _memories(request):
    conn = store.connect()
    name = request.query_params.get("elder")
    elder = _elder_or_error(conn, name) if name else None  # no elder given: the whole family
    mems = store.list_memories(conn, elder["id"] if elder else None, request.query_params.get("shelf"))
    disputes = store.conflicts(conn)
    for m in mems:
        m["provenance"] = store.provenance(m)
        m["conflicts"] = [c for c in disputes if m["id"] in (c["a"], c["b"])]
        m["media"] = store.media_for(conn, m["id"])
        m["suggestions"] = store.suggestions_for(conn, m["id"])
    return {"memories": mems}


async def _graph(request):
    return store.graph(store.connect())


async def _media_add(request):
    body = await _json(request)
    try:
        data = base64.b64decode(body.get("data", "").split(",")[-1], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("data must be a base64 file")
    return store.add_media(store.connect(), int(body.get("memory_id") or 0), data, (body.get("caption") or "")[:200],
                           (body.get("added_by") or "")[:60])


async def _suggest(request):
    b = await _json(request)
    return store.suggest(store.connect(), int(b.get("memory_id") or 0), b.get("author", ""), b.get("field", ""),
                         b.get("value", ""), b.get("reason"))


async def _decide(request):
    b = await _json(request)
    return store.decide(store.connect(), int(b.get("id") or 0), bool(b.get("approve")), b.get("by") or "the elder")


async def _suggestions(request):
    return {"suggestions": store.suggestions_for(store.connect(), status=request.query_params.get("status"))}


async def _gaps(request):
    return do_gaps(request.query_params.get("elder"))


async def _next(request):
    body = await _json(request)
    return await do_next_question(body.get("elder"), body.get("gap"))


async def _save(request):
    body = await _json(request)
    if not body.get("text", "").strip():
        raise ValueError("text is required")
    return await do_save(body.get("elder"), body["text"], source="web")


async def _ask(request):
    body = await _json(request)
    if not body.get("question", "").strip():
        raise ValueError("question is required")
    return await do_ask(body["question"])


async def _handbook(request):
    return await do_handbook(request.query_params.get("section", "memoir"), request.query_params.get("elder"))


for path, method, handler in [("/api/status", "GET", _status), ("/api/family", "GET", _family),
                              ("/api/memories", "GET", _memories), ("/api/gaps", "GET", _gaps), ("/api/next", "POST", _next),
                              ("/api/save", "POST", _save), ("/api/ask", "POST", _ask),
                              ("/api/handbook", "GET", _handbook), ("/api/graph", "GET", _graph),
                              ("/api/media", "POST", _media_add), ("/api/suggest", "POST", _suggest),
                              ("/api/decide", "POST", _decide), ("/api/suggestions", "GET", _suggestions)]:
    mcp.custom_route(path, methods=[method])(_api(handler))


def main():
    mcp.run("streamable-http", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8787")))


if __name__ == "__main__":
    main()

"""SQLite storage for elders, memories and the questions already asked."""

import json
import os
import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("STORYKEEPER_DB", Path(__file__).resolve().parent.parent / "data" / "storykeeper.db"))

SHELVES = {
    "story": "Stories",
    "recipe": "Kitchen",
    "health": "Health",
    "vault": "Where things are",
    "wisdom": "Wisdom & people",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS elders (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    full_name TEXT,
    relation TEXT,
    born_year INTEGER,
    birthplace TEXT
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    elder_id INTEGER NOT NULL REFERENCES elders(id),
    shelf TEXT NOT NULL,
    title TEXT NOT NULL,
    transcript TEXT NOT NULL,
    summary TEXT NOT NULL,
    year INTEGER,
    place TEXT,
    people TEXT NOT NULL DEFAULT '[]',
    details TEXT NOT NULL DEFAULT '{}',
    redacted INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'English',
    translation TEXT,
    source TEXT NOT NULL DEFAULT 'alexa',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    memory_id INTEGER NOT NULL REFERENCES memories(id),
    kind TEXT NOT NULL,            -- photo | voice
    file TEXT NOT NULL,
    mime TEXT NOT NULL,
    caption TEXT,
    added_by TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY,
    memory_id INTEGER NOT NULL REFERENCES memories(id),
    author TEXT NOT NULL,
    field TEXT NOT NULL,           -- title | year | place | summary | people | note
    old_value TEXT,
    new_value TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | declined
    decided_by TEXT,
    created_at REAL NOT NULL,
    decided_at REAL
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    elder_id INTEGER NOT NULL REFERENCES elders(id),
    question TEXT NOT NULL,
    shelf TEXT,
    created_at REAL NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    have = {r["name"] for r in conn.execute("PRAGMA table_info(memories)")}
    for col, ddl in [("language", "TEXT NOT NULL DEFAULT 'English'"), ("translation", "TEXT"),
                     ("source", "TEXT NOT NULL DEFAULT 'alexa'")]:
        if col not in have:
            conn.execute(f"ALTER TABLE memories ADD COLUMN {col} {ddl}")
    return conn


# Account numbers, OTPs, Aadhaar/PAN-like strings and passwords never get stored:
# the vault records *where* something is, not the secret itself.
_SECRET_PATTERNS = [
    (re.compile(r"\b\d[\d\s-]{5,}\d\b"), "[number withheld]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN withheld]"),
    (re.compile(r"(?i)\b(password|passcode|pin|otp)\b\s*(is|:)?\s*\S+"), r"\1 [withheld]"),
]


def redact(text: str) -> tuple[str, bool]:
    changed = False
    for pattern, repl in _SECRET_PATTERNS:
        text, n = pattern.subn(repl, text)
        changed |= n > 0
    return text, changed


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    if "people" in d:
        d["people"] = json.loads(d["people"])
    if "details" in d:
        d["details"] = json.loads(d["details"])
    return d


def list_elders(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT e.*, COUNT(m.id) AS memory_count FROM elders e
           LEFT JOIN memories m ON m.elder_id = e.id GROUP BY e.id ORDER BY e.id"""
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["shelves"] = dict.fromkeys(SHELVES, 0)
        for s in conn.execute("SELECT shelf, COUNT(*) c FROM memories WHERE elder_id=? GROUP BY shelf", (r["id"],)):
            d["shelves"][s["shelf"]] = s["c"]
        out.append(d)
    return out


def find_elder(conn, name: str | None) -> dict | None:
    if not name:
        r = conn.execute("SELECT * FROM elders ORDER BY id LIMIT 1").fetchone()
        return dict(r) if r else None
    needle = name.strip().lower()
    for r in conn.execute("SELECT * FROM elders"):
        names = [r["name"].lower(), (r["full_name"] or "").lower(), (r["relation"] or "").lower()]
        if any(needle == n or (n and needle in n) for n in names):
            return dict(r)
    return None


def add_elder(conn, name, full_name=None, relation=None, born_year=None, birthplace=None) -> dict:
    conn.execute(
        "INSERT OR IGNORE INTO elders(name, full_name, relation, born_year, birthplace) VALUES (?,?,?,?,?)",
        (name, full_name, relation, born_year, birthplace),
    )
    conn.commit()
    return find_elder(conn, name)


def add_memory(conn, elder_id: int, shelf: str, title: str, transcript: str, summary: str,
               year=None, place=None, people=None, details=None, redacted=False, created_at=None,
               language="English", translation=None, source="alexa") -> dict:
    cur = conn.execute(
        """INSERT INTO memories(elder_id, shelf, title, transcript, summary, year, place, people, details, redacted,
                                 language, translation, source, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (elder_id, shelf if shelf in SHELVES else "story", title, transcript, summary, year, place,
         json.dumps(people or []), json.dumps(details or {}), int(redacted), language or "English",
         translation or None, source, created_at or time.time()),
    )
    conn.commit()
    return get_memory(conn, cur.lastrowid)


def get_memory(conn, memory_id: int) -> dict | None:
    r = conn.execute(
        "SELECT m.*, e.name AS elder FROM memories m JOIN elders e ON e.id = m.elder_id WHERE m.id=?", (memory_id,)
    ).fetchone()
    return _row(r) if r else None


def list_memories(conn, elder_id: int | None = None, shelf: str | None = None) -> list[dict]:
    q = "SELECT m.*, e.name AS elder FROM memories m JOIN elders e ON e.id = m.elder_id WHERE 1=1"
    args: list = []
    if elder_id:
        q += " AND m.elder_id=?"
        args.append(elder_id)
    if shelf:
        q += " AND m.shelf=?"
        args.append(shelf)
    q += " ORDER BY COALESCE(m.year, 9999), m.created_at"
    return [_row(r) for r in conn.execute(q, args)]


def record_question(conn, elder_id: int, question: str, shelf: str | None):
    conn.execute(
        "INSERT INTO questions(elder_id, question, shelf, created_at) VALUES (?,?,?,?)",
        (elder_id, question, shelf, time.time()),
    )
    conn.commit()


def recent_questions(conn, elder_id: int, limit: int = 15) -> list[str]:
    return [r["question"] for r in conn.execute(
        "SELECT question FROM questions WHERE elder_id=? ORDER BY created_at DESC LIMIT ?", (elder_id, limit))]


_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or of to in on at for is was were did do does what when where who how my our your his her "
            "their he she they it i we you me us with about from that this tell ask storykeeper nanaji nani dadaji "
            "dadi grandpa grandma".split())


def search(conn, query: str, limit: int = 6) -> list[dict]:
    """Keyword-overlap ranking; small archives don't need a vector index."""
    terms = {w for w in _WORD.findall(query.lower()) if w not in _STOP}
    scored = []
    for m in list_memories(conn):
        hay = " ".join([m["title"], m["summary"], m["transcript"], m["translation"] or "", m["place"] or "", " ".join(m["people"]),
                        json.dumps(m["details"]), str(m["year"] or ""), SHELVES[m["shelf"]]]).lower()
        words = set(_WORD.findall(hay))
        score = sum(3 if t in m["title"].lower() else 1 for t in terms if t in words or (len(t) > 4 and t[:5] in hay))
        if score:
            scored.append((score, m))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]]


# ------------------------------------------------------------------ provenance

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
        "seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _spoken(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + ("" if n % 10 == 0 else "-" + _ONES[n % 10])


def _said(value, transcript: str) -> bool:
    """True when a value is (mostly) in the elder's own words rather than estimated by the model."""
    low = transcript.lower()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value) in low or (value < 100 and _spoken(value) in low)
    words = [w for w in _WORD.findall(str(value).lower()) if w not in _STOP and len(w) > 2]
    if not words:
        return str(value).lower() in low
    return sum(w in low for w in words) / len(words) >= 0.6


def provenance(m: dict) -> dict:
    """Which of a memory's facts the elder actually said, and which were inferred (dated from age clues, sugar ->
    type 2 diabetes, ...). Families can then trust the first kind and double-check the second."""
    said_in = m["transcript"] + " " + (m.get("translation") or "")
    fields = {}
    if m.get("year"):
        fields["year"] = "said" if str(m["year"]) in said_in else "inferred"
    if m.get("place"):
        fields["place"] = "said" if _said(m["place"], said_in) else "inferred"
    for k, v in m["details"].items():
        if k == "quantities":  # a note about the recipe, not a claim
            continue
        vals = v if isinstance(v, list) else [v]
        fields[k] = "said" if all(_said(x, said_in) for x in vals) else "inferred"
    return {"told_by": m["elder"], "recorded_at": m["created_at"], "source": m.get("source", "alexa"),
            "language": m.get("language", "English"), "redacted": bool(m["redacted"]), "fields": fields}


# ------------------------------------------------------------------ two versions of the same event

_EVENTS = {"wedding", "married", "marriage", "viyah", "born", "birth", "died", "death", "partition", "moved", "war",
           "retired", "job", "house", "school", "college", "accident", "operation", "baraat"}
_GENERIC = {"first", "mother", "father", "still", "whole", "every", "time", "family", "home", "came", "went", "year",
            "years", "they", "them", "said", "would", "could", "only", "like", "after", "before", "remembers"}


def _topic_words(m: dict) -> set[str]:
    text = f"{m['title']} {m['summary']} {m.get('translation') or ''}".lower()
    return {w for w in _WORD.findall(text) if w not in _STOP | _GENERIC and len(w) > 3 and not w.isdigit()}


def conflicts(conn, memories: list[dict] | None = None) -> list[dict]:
    """Pairs of memories from different elders that describe the same event with different years.

    Storykeeper never picks a winner: both versions are kept until the family clarifies.
    """
    mems = [m for m in (memories if memories is not None else list_memories(conn)) if m["year"] and m["shelf"] == "story"]
    out = []
    for i, a in enumerate(mems):
        for b in mems[i + 1:]:
            if a["elder_id"] == b["elder_id"] or a["year"] == b["year"] or abs(a["year"] - b["year"]) > 5:
                continue
            wa, wb = _topic_words(a), _topic_words(b)
            shared = wa & wb
            if shared & _EVENTS and len(shared) >= 3 and len(shared) / len(wa | wb) >= 0.15:
                out.append({"a": a["id"], "b": b["id"], "field": "year",
                            "versions": [{"id": a["id"], "elder": a["elder"], "value": a["year"], "title": a["title"]},
                                         {"id": b["id"], "elder": b["elder"], "value": b["year"], "title": b["title"]}],
                            "about": sorted(shared)[:4]})
    return out


# ------------------------------------------------------------------ photos and the elder's real voice

MEDIA_DIR = DB_PATH.parent / "media"
_MAGIC = {b"\xff\xd8\xff": ("photo", "image/jpeg", ".jpg"), b"\x89PNG": ("photo", "image/png", ".png"),
          b"RIFF": (None, None, None), b"\x1aE\xdf\xa3": ("voice", "audio/webm", ".webm"),
          b"OggS": ("voice", "audio/ogg", ".ogg")}
MAX_MEDIA_BYTES = 12 * 1024 * 1024


def _sniff(data: bytes) -> tuple[str, str, str]:
    """Trust the bytes, not the filename: only real JPEG/PNG/WebP photos and WebM/Ogg/MP4 recordings."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "photo", "image/webp", ".webp"
    if data[4:8] == b"ftyp":
        return "voice", "audio/mp4", ".m4a"
    for magic, kind in _MAGIC.items():
        if data.startswith(magic) and kind[0]:
            return kind
    raise ValueError("Only JPEG, PNG or WebP photos and WebM, Ogg or MP4 voice recordings can be added.")


def add_media(conn, memory_id: int, data: bytes, caption: str | None = None, added_by: str | None = None) -> dict:
    if not get_memory(conn, memory_id):
        raise ValueError(f"No memory #{memory_id}")
    if len(data) > MAX_MEDIA_BYTES:
        raise ValueError("That file is larger than 12 MB.")
    kind, mime, ext = _sniff(data)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{memory_id}-{kind}-{int(time.time() * 1000)}{ext}"
    (MEDIA_DIR / name).write_bytes(data)
    cur = conn.execute("INSERT INTO media(memory_id, kind, file, mime, caption, added_by, created_at) VALUES (?,?,?,?,?,?,?)",
                       (memory_id, kind, name, mime, caption, added_by, time.time()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM media WHERE id=?", (cur.lastrowid,)).fetchone())


def media_for(conn, memory_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM media WHERE memory_id=? ORDER BY created_at", (memory_id,))]


# ------------------------------------------------------------------ relatives suggest, the elder approves

EDITABLE = ("title", "year", "place", "summary", "people")


def suggest(conn, memory_id: int, author: str, field: str, new_value: str, reason: str | None = None) -> dict:
    """A relative proposes a correction. Nothing changes until the elder (or their guardian) approves it,
    and the elder's original words are never edited."""
    m = get_memory(conn, memory_id)
    if not m:
        raise ValueError(f"No memory #{memory_id}")
    if field not in EDITABLE:
        raise ValueError(f"field must be one of {list(EDITABLE)}")
    if not author.strip() or not str(new_value).strip():
        raise ValueError("Who is suggesting, and the new value, are both required.")
    new_value, _ = redact(str(new_value).strip())
    old = ", ".join(m["people"]) if field == "people" else m[field]
    cur = conn.execute(
        "INSERT INTO suggestions(memory_id, author, field, old_value, new_value, reason, created_at) VALUES (?,?,?,?,?,?,?)",
        (memory_id, author.strip()[:60], field, None if old is None else str(old), new_value, (reason or "")[:300],
         time.time()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM suggestions WHERE id=?", (cur.lastrowid,)).fetchone())


def decide(conn, suggestion_id: int, approve: bool, decided_by: str) -> dict:
    s = conn.execute("SELECT * FROM suggestions WHERE id=?", (suggestion_id,)).fetchone()
    if not s:
        raise ValueError(f"No suggestion #{suggestion_id}")
    if s["status"] != "pending":
        raise ValueError("That suggestion was already decided.")
    if approve:
        value = s["new_value"]
        if s["field"] == "year":
            if not value.isdigit():
                raise ValueError("A year must be a number.")
            value = int(value)
        elif s["field"] == "people":
            value = json.dumps([p.strip() for p in value.split(",") if p.strip()])
        conn.execute(f"UPDATE memories SET {s['field']}=? WHERE id=?", (value, s["memory_id"]))  # field is whitelisted
    conn.execute("UPDATE suggestions SET status=?, decided_by=?, decided_at=? WHERE id=?",
                 ("approved" if approve else "declined", decided_by, time.time(), suggestion_id))
    conn.commit()
    return dict(conn.execute("SELECT * FROM suggestions WHERE id=?", (suggestion_id,)).fetchone())


def suggestions_for(conn, memory_id: int | None = None, status: str | None = None) -> list[dict]:
    q, args = "SELECT s.*, m.title AS memory_title, e.name AS elder FROM suggestions s JOIN memories m ON m.id = s.memory_id " \
              "JOIN elders e ON e.id = m.elder_id WHERE 1=1", []
    if memory_id:
        q += " AND s.memory_id=?"
        args.append(memory_id)
    if status:
        q += " AND s.status=?"
        args.append(status)
    return [dict(r) for r in conn.execute(q + " ORDER BY s.created_at DESC", args)]


# ------------------------------------------------------------------ family graph

HISTORY = {1947: "Partition", 1965: "Indo-Pak war", 1971: "'71 war", 1984: "1984", 1991: "Liberalisation",
           2020: "Pandemic"}


def graph(conn) -> dict:
    """People, places and events linked through the memories that mention them."""
    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}

    def node(key, label, kind):
        n = nodes.setdefault(key, {"id": key, "label": label, "kind": kind, "memories": []})
        return n

    def link(a, b, mid, kind="told"):
        k = tuple(sorted((a, b)))
        e = edges.setdefault(k, {"source": k[0], "target": k[1], "kind": kind, "memories": []})
        if mid not in e["memories"]:
            e["memories"].append(mid)

    elders = {e["name"]: e for e in list_elders(conn)}
    names = {}
    for e in elders.values():
        node(f"elder:{e['name']}", e["name"], "elder")
        for alias in filter(None, [e["name"], e["full_name"], (e["full_name"] or "").split(" ")[0] + " " +
                                   ((e["full_name"] or " ").split(" ") + [""])[1]]):
            names[alias.strip().lower()] = e["name"]
    for m in list_memories(conn):
        me = f"elder:{m['elder']}"
        node(me, m["elder"], "elder")["memories"].append(m["id"])
        for p in m["people"]:
            p = re.sub(r"^(her|his|their) ", f"{m['elder']}'s ", p.strip())  # "her mother" -> "Nani's mother"
            canon = names.get(p.lower()) or next((v for k, v in names.items() if p.lower() in k), None)
            key = f"elder:{canon}" if canon else f"person:{p.lower()}"
            node(key, canon or p, "elder" if canon else "person")["memories"].append(m["id"])
            if key != me:
                link(me, key, m["id"])
        if m["place"] and m["place"].lower() not in ("home",):
            key = f"place:{m['place'].split(' (')[0].lower()}"
            node(key, m["place"].split(" (")[0], "place")["memories"].append(m["id"])
            link(me, key, m["id"])
        if m["year"] in HISTORY and m["shelf"] == "story":
            key = f"event:{m['year']}"
            node(key, f"{HISTORY[m['year']]} ({m['year']})", "event")["memories"].append(m["id"])
            link(me, key, m["id"], kind="context")  # historical context for that year, not something they said
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}

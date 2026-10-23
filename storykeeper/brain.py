"""Amazon Bedrock brain: understands what elders say, plans the next question, answers family
questions and writes the handbook. Uses Amazon Nova through the Bedrock Converse API, falling back to simple
heuristics so the demo never dead-ends on stage."""

import asyncio
import json
import logging
import os
import re

import boto3

from .store import SHELVES

log = logging.getLogger("storykeeper.brain")

NOVA_MODEL = os.environ.get("NOVA_MODEL", "us.amazon.nova-2-lite-v1:0")
REGION = os.environ.get("AWS_REGION", "us-east-1")
USE_BEDROCK = os.environ.get("STORYKEEPER_MODE", "bedrock") == "bedrock"

status = {"engine": "bedrock" if USE_BEDROCK else "offline", "model": NOVA_MODEL, "region": REGION, "last_error": None}
_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        _runtime = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=REGION).client("bedrock-runtime")
    return _runtime


def _fail(err: Exception | str):
    status["engine"], status["model"], status["last_error"] = "offline", None, str(err)[:300]
    log.warning("Bedrock unavailable, using offline fallback: %s", err)


async def _llm(system: str, prompt: str, schema: dict | None = None, max_tokens: int = 4000) -> str | dict | None:
    """One Bedrock call. Returns parsed JSON when a schema is given, text otherwise, None on failure."""
    if not USE_BEDROCK:
        return None
    return await _nova(system, prompt, schema, max_tokens)


async def _nova(system, prompt, schema, max_tokens):
    if schema:
        prompt += ("\n\nRespond with ONLY a JSON object (no prose, no code fences) matching this JSON schema. "
                   "Include every required key; use null or [] when a value doesn't apply:\n" + json.dumps(schema))
    try:
        resp = await asyncio.to_thread(
            _get_runtime().converse,
            modelId=NOVA_MODEL,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": min(max_tokens, 5000), "temperature": 0.3},
        )
        text = "".join(c.get("text", "") for c in resp["output"]["message"]["content"]).strip()
        result = _conform(_parse_json(text), schema) if schema else text
    except Exception as e:
        _fail(f"Nova: {e}")
        return None
    status["engine"], status["model"], status["last_error"] = "bedrock", NOVA_MODEL, None
    return result


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def _conform(data: dict, schema: dict) -> dict:
    """Fill keys the model skipped and coerce enums/types so callers can trust the shape."""
    out = {}
    for key, spec in schema["properties"].items():
        types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        val = data.get(key)
        if "array" in types:
            cast = int if spec.get("items", {}).get("type") == "integer" else str
            try:
                val = [cast(v) for v in val] if isinstance(val, list) else []
            except (TypeError, ValueError):
                val = []
        elif "integer" in types:
            try:
                val = int(val) if val is not None else None
            except (TypeError, ValueError):
                val = None
            if val is None and "null" not in types:
                val = 0
        elif val is None and "null" not in types:
            val = ""
        if "enum" in spec and val not in spec["enum"]:
            val = spec["enum"][0]
        out[key] = val
    return out


def _memory_line(m: dict) -> str:
    when = f"{m['year']}" if m.get("year") else "year unknown"
    where = f", {m['place']}" if m.get("place") else ""
    return f"[#{m['id']} · {m['elder']} · {SHELVES[m['shelf']]} · {when}{where}] {m['title']}: {m['summary']}"


# ---------------------------------------------------------------- understanding

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "shelf": {"type": "string", "enum": list(SHELVES)},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "year": {"type": ["integer", "null"]},
        "place": {"type": ["string", "null"]},
        "people": {"type": "array", "items": {"type": "string"}},
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
        "condition": {"type": ["string", "null"]},
        "onset_age": {"type": ["integer", "null"]},
        "medicines": {"type": "array", "items": {"type": "string"}},
        "item": {"type": ["string", "null"]},
        "location": {"type": ["string", "null"]},
        "contact": {"type": ["string", "null"]},
        "language": {"type": "string"},
        "translation": {"type": ["string", "null"]},
        "acknowledgement": {"type": "string"},
    },
    "required": ["shelf", "title", "summary", "year", "place", "people", "ingredients", "steps", "condition",
                 "onset_age", "medicines", "item", "location", "contact", "language", "translation",
                 "acknowledgement"],
    "additionalProperties": False,
}

EXTRACT_SYSTEM = """You file an elderly person's spoken memories into their family's archive.
Shelves: story (life events, memoir material), recipe (dishes and how to make them), health (conditions, medicines,
allergies, family illnesses), vault (where important documents/keys/policies/valuables are kept, who to call about
them), wisdom (advice, skills, trusted people like the family doctor or plumber).
Write `summary` in third person, 1-3 warm, factual sentences that keep their own vivid words. `title` is 3-7 words.
Estimate `year` from their birth year and age clues when they don't say it; null if truly unknown.
Fill recipe/health/vault fields only when they apply; otherwise empty arrays or null.
Never copy account numbers, PINs, passwords or ID numbers - those are withheld before you see them.
Elders often mix languages (Punjabi-English, Hindi-English, romanized or in Gurmukhi/Devanagari). `language` names
what they spoke, e.g. "English", "Punjabi-English", "Hindi". When it isn't plain English, `translation` is a faithful
English translation of exactly what they said; otherwise null. Keep cultural terms, dishes, honorifics and names as
they said them (saag, ghotna, baraat, Bebe). Write title and summary in English.
Recipes: keep their cooking cues ("until the oil separates", "until the khushboo comes") as steps. Never invent
quantities, temperatures or timings they didn't say.
Only state what they said or what follows directly from it - never add events, dialogue or feelings.
`acknowledgement` is what Alexa says back: one short, warm spoken sentence that reflects one specific detail."""


async def understand(elder: dict, transcript: str) -> dict:
    born = elder.get("born_year")
    prompt = (f"Speaker: {elder['name']} ({elder.get('full_name') or ''}), born {born or 'unknown'} in "
              f"{elder.get('birthplace') or 'unknown'}.\nThey said:\n\"\"\"{transcript}\"\"\"")
    data = await _llm(EXTRACT_SYSTEM, prompt, EXTRACT_SCHEMA)
    if isinstance(data, dict):
        return data
    return _understand_offline(elder, transcript)


_SHELF_HINTS = {
    "recipe": ["recipe", "cook", "masala", "add ", "fry", "boil", "dough", "pickle", "achaar", "dal", "ghee", "sugar"],
    "health": ["doctor", "sugar level", "diabetes", "bp", "blood pressure", "tablet", "medicine", "allergic", "heart",
               "knee", "operation", "thyroid"],
    "vault": ["papers", "policy", "locker", "almirah", "will", "deed", "registry", "bank", "fd", "documents", "key",
              "jewellery", "insurance", "kept"],
    "wisdom": ["always", "never", "advice", "remember to", "trust", "call ", "number of"],
}


def _understand_offline(elder: dict, transcript: str) -> dict:
    low = transcript.lower()
    shelf = max(_SHELF_HINTS, key=lambda s: sum(h in low for h in _SHELF_HINTS[s]))
    if not any(h in low for h in _SHELF_HINTS[shelf]):
        shelf = "story"
    year = None
    if m := re.search(r"\b(19[2-9]\d|20[0-2]\d)\b", transcript):
        year = int(m.group(1))
    first = re.split(r"(?<=[.!?])\s", transcript.strip())[0]
    return {
        "shelf": shelf, "title": " ".join(first.split()[:6]).strip(".,") or "A memory",
        "summary": f"{elder['name']} shared: {transcript.strip()[:400]}", "year": year, "place": None,
        "people": [], "ingredients": [], "steps": [], "condition": None, "onset_age": None, "medicines": [],
        "item": None, "location": None, "contact": None, "language": _guess_language(transcript),
        "translation": None, "acknowledgement": "Thank you, I've saved that for the family.",
    }


_PUNJABI = {"si", "nu", "vich", "sadda", "saada", "tuhade", "naal", "jad", "kade", "nahi", "aaye", "aayi", "hoya", "di",
            "da", "de", "te", "ne", "main", "mainu", "sanu", "tusi", "assi", "thoda", "thodi", "kar", "lo", "pakao",
            "ghar", "wale", "wala", "apne", "kol", "haan", "rakhdi", "rakhda", "gaya", "gayi", "chaabi", "neeche",
            "upar", "andar", "ohna", "ehna", "bebe", "bapuji", "kiven", "kithe", "hun", "baad"}
_HINDI = {"hai", "hain", "tha", "thi", "mein", "ko", "aur", "nahin", "bahut", "kya", "jab", "humara", "hamara", "dalna",
          "daalna", "mera", "meri", "mujhe", "hum", "woh", "yeh", "rakha", "rakhi", "chabi", "kahan", "kaise", "phir"}


def _guess_language(text: str) -> str:
    if re.search(r"[\u0A00-\u0A7F]", text):
        return "Punjabi"
    if re.search(r"[\u0900-\u097F]", text):
        return "Hindi"
    words = set(re.findall(r"[a-z]+", text.lower()))
    pa, hi = len(words & _PUNJABI), len(words & _HINDI)
    if max(pa, hi) < 3 and max(pa, hi) / max(len(words), 1) < 0.2:
        return "English"
    return "Punjabi-English" if pa >= hi else "Hindi-English"


# ---------------------------------------------------------------- interviewing

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "shelf": {"type": "string", "enum": list(SHELVES)},
        "why": {"type": "string"},
    },
    "required": ["question", "shelf", "why"],
    "additionalProperties": False,
}

QUESTION_SYSTEM = """You are a gentle family interviewer speaking through Alexa to an elderly person.
Pick ONE next question. Balance two goals:
1. Practical gaps the family will urgently need one day: health history (conditions, medicines, what runs in the
   family), where important things are kept (property papers, insurance, locker, will - never ask for numbers or
   passwords), trusted people, and signature recipes.
2. Life story gaps: decades or chapters not yet covered, and follow-ups on vivid details they mentioned before.
You are given the Gap Engine's ranked gaps (score = importance x uncertainty x freshness). Ask about the top gap
unless a lower one is clearly a more natural follow-up to what they just said. Never repeat a recent question.
The question is spoken aloud: under 30 words, warm, simple, one thing at a time, may use their honorific.
Ask in English unless they have been answering in another language; then ask in that same mix.
`why` is a short note for the family dashboard explaining the gap this fills."""


async def next_question(elder: dict, memories: list[dict], asked: list[str], ranked: list[dict]) -> dict:
    coverage = {s: sum(1 for m in memories if m["shelf"] == s) for s in SHELVES}
    decades = sorted({(m["year"] // 10) * 10 for m in memories if m.get("year")})
    prompt = (f"Elder: {elder['name']} ({elder.get('full_name') or ''}), born {elder.get('born_year')} in "
              f"{elder.get('birthplace')}.\nShelf coverage: {json.dumps(coverage)}\nDecades covered: {decades}\n"
              f"Memories so far:\n" + "\n".join(_memory_line(m) for m in memories[-40:]) +
              "\nRecently asked (do not repeat):\n" + "\n".join(f"- {q}" for q in asked) +
              "\nRanked gaps:\n" + "\n".join(f"- [{g['score']}] {g['kind']} ({g['shelf']}): {g['why']} "
                                               f"Suggested: {g['question']}" for g in ranked[:6]))
    data = await _llm(QUESTION_SYSTEM, prompt, QUESTION_SCHEMA)
    if isinstance(data, dict):
        return data
    if ranked:
        return {"question": ranked[0]["question"], "shelf": ranked[0]["shelf"], "why": ranked[0]["why"]}
    return _next_question_offline(elder, memories, asked)


_FALLBACK_QUESTIONS = [
    ("health", "Has anyone in the family had sugar, BP or heart trouble? At what age did it start?",
     "No family health history yet"),
    ("vault", "Where do you keep the house papers and insurance policies, so the children can find them?",
     "Nobody knows where important papers are"),
    ("recipe", "Which dish do the grandchildren always ask you to make? How do you make it?",
     "No signature recipes saved"),
    ("story", "What was the house you grew up in like?", "Childhood not covered"),
    ("wisdom", "Who is the one person the family should call when something in the house breaks?",
     "No trusted contacts saved"),
    ("story", "How did you meet your life partner?", "Marriage chapter missing"),
    ("story", "What was your very first job, and what did you earn?", "Working life not covered"),
]


def _next_question_offline(elder, memories, asked):
    have = {m["shelf"] for m in memories}
    for shelf, q, why in sorted(_FALLBACK_QUESTIONS, key=lambda x: x[0] in have):
        if q not in asked:
            return {"question": q, "shelf": shelf, "why": why}
    return {"question": "What is a day from your life you wish everyone in the family knew about?",
            "shelf": "story", "why": "Open question"}


# ---------------------------------------------------------------- answering

ANSWER_SYSTEM = """You answer a family member's question using ONLY the archived memories provided.
Answer in 1-4 spoken sentences suitable for Alexa to read aloud. Retell stories warmly, in third person, keeping the
elder's own vivid words in short quotes where they help. For recipes give the steps plainly. For health or document
questions be precise and practical. If the memories don't contain the answer, say so kindly and suggest asking the
elder next time - never invent facts. If two elders remember something differently, give both versions and who said
each - never pick one. List the memory ids you used."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "sources": {"type": "array", "items": {"type": "integer"}}},
    "required": ["answer", "sources"],
    "additionalProperties": False,
}


async def answer(question: str, memories: list[dict], conflicts: list[dict] | None = None) -> dict:
    if not memories:
        return {"answer": "I don't have anything about that in the family archive yet. "
                          "It would make a lovely question for the next interview.", "sources": []}
    prompt = "Archived memories:\n" + "\n".join(
        _memory_line(m) + (f"\n   details: {json.dumps(m['details'])}" if m["details"] else "") +
        (f"\n   their words ({m['language']}), translated: {m['translation']}" if m.get("translation") else "")
        for m in memories
    ) + "".join(f"\nDisagreement: {c['versions'][0]['elder']} says {c['versions'][0]['value']}, "
                f"{c['versions'][1]['elder']} says {c['versions'][1]['value']} (#{c['a']} vs #{c['b']})"
                for c in conflicts or []) + f"\n\nQuestion: {question}"
    data = await _llm(ANSWER_SYSTEM, prompt, ANSWER_SCHEMA)
    if isinstance(data, dict):
        return data
    best = memories[0]
    text = best["summary"]
    for c in conflicts or []:
        if best["id"] in (c["a"], c["b"]):
            other = next(v for v in c["versions"] if v["id"] != best["id"])
            text += f" {other['elder']} remembers it as {other['value']}, so the family has both versions."
    return {"answer": text, "sources": [best["id"]]}


# ---------------------------------------------------------------- handbook

HANDBOOK = {
    "memoir": ("Memoir chapter",
               "Write a memoir chapter (400-700 words) in the elder's first-person voice, in chronological order, "
               "built only from these memories. Give it a title line starting with '# '. Use short paragraphs. "
               "Keep their phrases. Do not invent events."),
    "health": ("Family health history",
               "Write a concise family health history a doctor can scan in 30 seconds, in Markdown. Sections: "
               "'## Conditions in the family' (who, condition, age of onset), '## Current medicines', "
               "'## Allergies & notes', '## Worth discussing with a doctor' (hereditary risks for children and "
               "grandchildren, phrased cautiously, no diagnosis). Use only the memories given."),
    "essentials": ("If something happens",
                   "Write a calm, practical 'If something happens' sheet in Markdown for the children: where each "
                   "important document/valuable is kept, who to contact, and first steps. Group under '## Papers', "
                   "'## Money & insurance', '## Home', '## People to call'. Never include numbers or passwords - "
                   "only locations and names. Use only the memories given."),
    "recipes": ("Family recipe book",
                "Write the family recipe cards in Markdown: one '## ' heading per dish with who it's from, "
                "an ingredients list and numbered steps, plus one line of the story behind it. Only use the "
                "memories given; mark missing quantities as 'to taste' rather than inventing them."),
}


async def handbook(section: str, memories: list[dict]) -> str:
    title, instruction = HANDBOOK[section]
    if not memories:
        return f"# {title}\n\nNothing recorded for this yet. Ask Storykeeper to start an interview."
    prompt = instruction + "\n\nMemories:\n" + "\n".join(
        _memory_line(m) + (f"\n   details: {json.dumps(m['details'])}" if m["details"] else "") for m in memories)
    text = await _llm("You compile a family's archive into documents they will keep and print.", prompt, max_tokens=8000)
    if isinstance(text, str) and text:
        return text
    lines = [f"# {title}", ""]
    for m in memories:
        lines.append(f"## {m['title']} ({m['elder']}{', ' + str(m['year']) if m['year'] else ''})")
        lines.append(m["summary"])
        for k, v in m["details"].items():
            if v:
                lines.append(f"- **{k}**: {', '.join(v) if isinstance(v, list) else v}")
        lines.append("")
    return "\n".join(lines)

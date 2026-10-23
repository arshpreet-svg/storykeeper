"""Memory Gap Engine: which missing memory would be most valuable to collect next.

Every candidate gets a score = importance x uncertainty x freshness (0-100), so the interview always goes after the
thing the family would miss most, and the dashboard can show *why*. Deterministic on purpose: it works without a
model and the ranking is explainable to judges and families alike.
"""

import json
import time

# (key, shelf, kind, importance 1-10, keywords that mean "we already know this", question, why it matters)
PRACTICAL = [
    ("allergies", "health", "Safety", 10, ["allerg", "react", "rash"],
     "Are you allergic to any medicine or food? What happened when you took it?",
     "Doctors ask about allergies first - a wrong injection can be dangerous."),
    ("medicines", "health", "Health", 9, ["medicines", "tablet", "metformin", "thyroxine", "insulin", "takes"],
     "Which medicines do you take every day, and at what time?",
     "Needed at every hospital visit."),
    ("family_history", "health", "Health", 8, ["father", "mother", "runs in", "bapuji", "her mother", "his mother"],
     "Did your parents have sugar, BP or heart trouble? At what age did it start?",
     "Tells the grandchildren what to get checked, and when."),
    ("doctor", "wisdom", "People", 7, ["dr.", "doctor", "clinic"],
     "Which doctor has looked after you for the longest time? Where is the clinic?",
     "The person who knows all the old reports."),
    ("property", "vault", "Papers", 9, ["registry", "house papers", "deed", "property"],
     "Where are the house papers kept, so the children can find them?",
     "Property papers are the hardest thing to find later."),
    ("insurance", "vault", "Papers", 8, ["policy", "insurance", "lic"],
     "Do you have any insurance policy? Where are the papers, and who is the agent?",
     "Unclaimed policies are common when nobody knows they exist."),
    ("bank", "vault", "Papers", 8, ["bank", "locker", "fd", "account"],
     "Which bank do you use, and where do you keep the locker key or passbook? Don't tell me any numbers.",
     "Where the bank things are - never the numbers."),
    ("will", "vault", "Papers", 7, ["will", "nominee", "wasiyat"],
     "Have you written a will, or named a nominee? Where is it kept?",
     "Avoids confusion and disputes later."),
    ("recipe", "recipe", "Heritage", 5, [],
     "Which dish do the grandchildren always ask you to make? How do you make it?",
     "A taste of home that is lost if nobody writes it down."),
]

LIFE_CHAPTERS = [
    (0, 12, "childhood", "What was the house you grew up in like? Who lived there with you?"),
    (13, 22, "youth", "What did you do as a young person - school, friends, your first dreams?"),
    (23, 35, "early working life", "What was your work like in your twenties? What did you earn?"),
    (36, 55, "middle years", "What was the hardest year for the family when you were in your forties?"),
    (56, 120, "later life", "What has changed the most in your life since you turned sixty?"),
]

RECHECK_AFTER_DAYS = 90


def _knows(memories: list[dict], shelf: str, keywords: list[str]) -> int:
    """How many memories already cover this. Trusted people can turn up on any shelf."""
    pool = memories if shelf == "wisdom" else [m for m in memories if m["shelf"] == shelf]
    if not keywords:
        return len(pool)
    hay = lambda m: (m["title"] + " " + m["summary"] + " " + m["transcript"] + " " + json.dumps(m["details"])).lower()
    return sum(any(k in hay(m) for k in keywords) for m in pool)


def _freshness(question: str, asked: list[str]) -> float:
    """Recently asked questions sink, so a skip is respected and nobody is nagged."""
    if question in asked[:3]:
        return 0.15
    if question in asked:
        return 0.5
    return 1.0


def rank(elder: dict, memories: list[dict], asked: list[str], now: float | None = None) -> list[dict]:
    now = now or time.time()
    out = []

    for key, shelf, kind, importance, keywords, question, why in PRACTICAL:
        known = _knows(memories, shelf, keywords)
        if key == "recipe":
            uncertainty = {0: 1.0, 1: 0.35}.get(known, 0.0)  # one recipe is a start, not a recipe book
        else:
            uncertainty = 1.0 if known == 0 else 0.0
        if uncertainty:
            out.append({"key": key, "kind": kind, "shelf": shelf, "importance": importance,
                        "uncertainty": uncertainty, "question": question, "why": why})

    # Facts that may have changed since they were told: medicines especially.
    for m in memories:
        meds = m["details"].get("medicines")
        age_days = (now - m["created_at"]) / 86400
        if meds and age_days > RECHECK_AFTER_DAYS:
            out.append({"key": f"recheck-{m['id']}", "kind": "Recheck", "shelf": "health", "importance": 8,
                        "uncertainty": min(1.0, 0.5 + age_days / 365),
                        "question": f"Last time you told me you take {meds[0].split(' (')[0].lower()}. "
                                    "Is that still the same, or has the doctor changed anything?",
                        "why": f"Told {int(age_days)} days ago - medicines change.", "memory": m["id"]})

    # Untold chapters of their life.
    born = elder.get("born_year")
    if born:
        years = [m["year"] for m in memories if m["shelf"] == "story" and m.get("year")]
        current_age = time.gmtime(now).tm_year - born
        for lo, hi, name, question in LIFE_CHAPTERS:
            if lo > current_age:
                continue
            told = sum(born + lo <= y <= born + hi for y in years)
            if told == 0:
                out.append({"key": f"chapter-{name}", "kind": "Life story", "shelf": "story", "importance": 6,
                            "uncertainty": 1.0, "question": question,
                            "why": f"Nothing yet from their {name} ({born + lo}-{min(born + hi, born + current_age)})."})

    # Stories that were started but never dated.
    for m in memories:
        if m["shelf"] == "story" and not m.get("year"):
            out.append({"key": f"date-{m['id']}", "kind": "Follow-up", "shelf": "story", "importance": 3,
                        "uncertainty": 1.0, "memory": m["id"],
                        "question": f"You told me about \"{m['title']}\". Do you remember roughly what year that was?",
                        "why": "A story without a year can't go on the life ribbon."})

    for g in out:
        g["freshness"] = _freshness(g["question"], asked)
        g["score"] = round(g["importance"] * 10 * g["uncertainty"] * g["freshness"])
    out.sort(key=lambda g: -g["score"])
    return out

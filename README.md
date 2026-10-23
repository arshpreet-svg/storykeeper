# Storykeeper

**A family's living memory, told to Alexa.** Elders talk to Alexa; Storykeeper interviews them, files what they say,
and turns it into things the family actually needs: a doctor-ready health history, an "if something happens" sheet
of where the papers and keys are, a recipe book, and a memoir.

> Built for the *Build, Ship, Shape: Amazon Developer Hackathon*. Track: **Alexa+ (self-hosted MCP server)**.
> Mini challenges: **AWS Builder** (Amazon Nova on Amazon Bedrock) and **Open Source** (MIT).

## Why

When a grandparent passes, families lose more than stories. Nobody knows where the house registry is, which bank
holds the locker, which medicines Nanaji was on, or how Nani made the pickle. Elders won't type into an app, but
they will chat with Alexa. Storykeeper uses that.

- **Memory Gap Engine.** Storykeeper knows what the family has *not* recorded yet. Every candidate gap (no allergy
  on record, unknown location of the house papers, an untold decade, medicines told 5 months ago) gets a score:
  importance × uncertainty × freshness. The interview goes after the top gap, the dashboard shows the ranking and why,
  and the elder can skip anything (a skipped question sinks instead of nagging).
- **Every fact has a source.** Each memory shows who told it, when, and how. Each extracted fact is tagged *in their
  words* or *inferred* (e.g. "sugar" → type 2 diabetes, or a year worked out from "when I was fourteen").
- **Two versions, never one silently picked.** When Nanaji remembers the wedding as 1970 and Nani as 1971, both are
  kept, shown side by side, spoken back by Alexa, and given in archive answers until the family settles it.
- **Speak the way they speak.** Punjabi-English, Hindi-English, Gurmukhi or Devanagari: the original words are
  stored untouched with a faithful English translation. Cultural terms stay (saag, ghotna, baraat), and recipe
  cues like "until the khushboo comes" are kept instead of invented timings or quantities.
- **Five shelves.** Stories · Kitchen · Health · Where things are · Wisdom & people. Amazon Nova decides the shelf,
  dates the memory from age clues and extracts structured details (ingredients, onset age, location, contact).
- **Safe by design.** Account numbers, PINs, OTPs and PAN-like strings are removed *before* anything is stored
  or sent to the model. The vault keeps *where* something is, never the secret.
- **Family graph.** People, places and historical events linked through the memories that mention them. Tap
  Gurnam and you see both wedding stories that mention him; tap Ludhiana and you see every memory set there.
  Historical events are drawn as dashed "context" links, never presented as something the elder said.
- **Relatives suggest, the elder approves.** A granddaughter can propose "the wedding was 1970, the card says so".
  Nothing changes until the elder (or their guardian) approves; the elder's original words are never edited, and
  every suggestion, approval and decline is kept as history. Suggestions are redacted like everything else.
- **Old photos and their real voice.** Show the elder an old photo in the interview ("Who is in it, and when was it
  taken?") and the photo is kept with the answer. Record their actual voice alongside a memory, so the
  grandchildren can hear *them*, not a synthetic narrator (the narrator button is clearly labelled as such).
  Uploads are checked by their bytes (JPEG/PNG/WebP photos, WebM/Ogg/MP4 audio, 12 MB max).
- **Ask the archive.** "Alexa, ask Storykeeper where Nanaji kept the LIC policy." The answer comes from his own
  words, with sources.
- **Print for the family.** One click compiles a Doctor's sheet, an "If something happens" sheet, a recipe book or a
  memoir chapter.

## Architecture

```
Alexa+ ──MCP (Streamable HTTP, spec 2025-11-25+)──▶  /mcp   ┐
Family web app (browser) ──────────────── JSON ──▶  /api/*  ├─ Storykeeper server (Python, MCP SDK 2.3)
                                                            │     ├─ store.py   SQLite, redaction, search, provenance, conflicts
                                                            │     ├─ gaps.py    Memory Gap Engine (scored, explainable)
                                                            │     └─ brain.py   Amazon Nova on Amazon Bedrock
                                                            ┘           (structured outputs; offline fallback)
```

One process serves both the MCP endpoint and the web app, so Alexa and the family dashboard share the same tools and
the same data.

### MCP tools

| Tool | What it does |
|---|---|
| `next_interview_question` | Asks about the elder's highest-scoring gap (practical gaps, rechecks, untold chapters) |
| `get_memory_gaps` | The ranked gap list with score, reason and a suggested question |
| `save_memory` | Redacts secrets, then Nova files the answer on a shelf, dates it and extracts details |
| `ask_family_archive` | Answers from the elders' recorded words with sources and provenance; gives both versions when elders disagree |
| `get_life_timeline` | The elder's dated memories in order |
| `get_family_graph` | People, places and events and the memories that connect them |
| `suggest_correction` | A relative proposes a fix; it waits for the elder's approval |
| `review_suggestion` | The elder lists, approves or declines pending corrections |
| `get_family_handbook` | Compiles `health`, `essentials`, `recipes` or `memoir` as Markdown |
| `list_family` | Elders and how much of each shelf is filled |

### AWS usage

- **Amazon Bedrock, Amazon Nova**: `us.amazon.nova-2-lite-v1:0` (set with `NOVA_MODEL`, region with `AWS_REGION`)
  through the boto3 Converse API. Responses are requested as JSON matching a schema, then validated and coerced so
  the rest of the app can trust their shape.
- The Bedrock calls cover memory understanding, interview planning, archive Q&A and handbook compilation. If Bedrock
  is unreachable, each call falls back to a simple heuristic so the demo never breaks. The header badge shows which
  engine answered.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m storykeeper.seed          # fictional demo family (wipes data/storykeeper.db and data/media)

# with Bedrock (needs AWS credentials with Bedrock access to Amazon Nova)
export AWS_REGION=us-east-1                   # and AWS_PROFILE=... or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
.venv/bin/python -m storykeeper.server

# or without AWS
STORYKEEPER_MODE=offline .venv/bin/python -m storykeeper.server
```

- Web app: http://127.0.0.1:8787
- MCP endpoint: http://127.0.0.1:8787/mcp
- Smoke test: `.venv/bin/python scripts/mcp_smoke.py`
- Tests (offline, throwaway DB): `.venv/bin/python -m unittest -v`. They cover secret redaction (cards, Aadhaar,
  PAN, PINs, OTPs, passwords, phone numbers, including in Punjabi/Hindi sentences), proof that a secret never reaches
  the model or the database, provenance tagging, conflict detection, the gap ranking, photo/voice upload checks,
  the approval workflow and the family graph.

### Deploy on Vercel

`vercel deploy` uses `api/index.py` and `vercel.json`: the same app as a serverless function, with the MCP endpoint
in stateless mode (JSON responses) at `https://<your-app>.vercel.app/mcp`. Serverless storage is temporary, so the
archive lives in `/tmp`, is seeded with the demo family on each cold start, and visitor changes don't persist. The
Vercel deployment runs in offline mode unless you add AWS credentials as environment variables and set
`STORYKEEPER_MODE=bedrock`. Smoke test: `.venv/bin/python scripts/mcp_smoke.py https://<your-app>.vercel.app/mcp`.

### Persistent hosting

Set `HOST=0.0.0.0` and `PORT` to deploy publicly (for example Render, Railway or AWS App Runner), then register the
public `https://…/mcp` URL as the MCP server for Alexa+ or any MCP client.

## Privacy

Everything lives in one SQLite file the family controls. Secrets are stripped by regex before storage or model
calls. Health and document summaries are informational and not medical or legal advice.

## License

MIT. See [LICENSE](LICENSE).

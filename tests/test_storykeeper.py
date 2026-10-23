"""Privacy, provenance, conflict and gap-engine tests. Run: .venv/bin/python -m unittest -v

Runs fully offline against a throwaway database; no AWS calls are made.
"""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["STORYKEEPER_DB"] = str(Path(_tmp) / "test.db")
os.environ["STORYKEEPER_MODE"] = "offline"

from storykeeper import brain, gaps, seed, server, store  # noqa: E402

SECRETS = [
    ("My SBI account number is 30214567891", "30214567891"),
    ("Card 4111 1111 1111 1111 is in the purse", "4111 1111 1111 1111"),
    ("Aadhaar 2345 6789 0123 is in the file", "2345 6789 0123"),
    ("ATM pin is 4821", "4821"),
    ("mera pin 7790 hai", "7790"),
    ("The OTP: 552910 came on my phone", "552910"),
    ("password is Kartar@1944", "Kartar@1944"),
    ("PAN card ABCDE1234F is with the CA", "ABCDE1234F"),
    ("Call Bhatia ji on 98140-12345", "98140-12345"),
]

KEEP = [
    "We left Lyallpur in 1947 on a bullock cart.",
    "Ninety rupees a month, ₹90.",
    "I take thyroxine 50 mcg every morning.",
    "I have sugar since I was fifty-two.",
    "The key is behind the Guru Nanak calendar.",
]


class Redaction(unittest.TestCase):
    def test_secrets_are_removed(self):
        for text, secret in SECRETS:
            with self.subTest(text=text):
                clean, changed = store.redact(text)
                self.assertTrue(changed)
                self.assertNotIn(secret, clean)

    def test_ordinary_details_survive(self):
        for text in KEEP:
            with self.subTest(text=text):
                self.assertEqual(store.redact(text), (text, False))

    def test_secret_never_reaches_model_or_database(self):
        seen = []

        async def spy(elder, transcript):
            seen.append(transcript)
            return brain._understand_offline(elder, transcript)

        real, brain.understand = brain.understand, spy
        try:
            seed.main()
            r = asyncio.run(server.do_save("Nani", "The locker key is in the rice drum and the locker pin is 4821."))
        finally:
            brain.understand = real
        self.assertNotIn("4821", seen[0])
        stored = store.get_memory(store.connect(), r["memory"]["id"])
        self.assertNotIn("4821", stored["transcript"] + stored["summary"])
        self.assertTrue(stored["redacted"])
        self.assertIn("left out the numbers", r["say"])


class Provenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed.main()
        cls.conn = store.connect()

    def _mem(self, title):
        return next(m for m in store.list_memories(self.conn) if m["title"] == title)

    def test_spoken_numbers_count_as_said(self):
        f = store.provenance(self._mem("Type 2 diabetes since 52"))["fields"]
        self.assertEqual(f["onset_age"], "said")  # "fifty-two"
        self.assertEqual(f["condition"], "inferred")  # they said "sugar"

    def test_year_from_age_clues_is_inferred(self):
        self.assertEqual(store.provenance(self._mem("The tube well in Samrala"))["fields"]["year"], "inferred")

    def test_code_switched_memory_keeps_original_and_translation(self):
        m = self._mem("Khatti kadhi with pakode")
        self.assertEqual(m["language"], "Punjabi-English")
        self.assertIn("andaza naal", m["transcript"])
        self.assertIn("by feel", m["translation"])

    def test_offline_language_guess(self):
        self.assertEqual(brain._guess_language("Sadda viyah 1971 vich hoya si, tuhade Nanaji naal"), "Punjabi-English")
        self.assertEqual(brain._guess_language("We married in 1970 at the gurdwara."), "English")


class Conflicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed.main()
        cls.conn = store.connect()

    def test_both_wedding_versions_are_kept(self):
        found = store.conflicts(self.conn)
        self.assertEqual(len(found), 1)
        self.assertEqual({v["elder"]: v["value"] for v in found[0]["versions"]}, {"Nanaji": 1970, "Nani": 1971})

    def test_answer_mentions_both_versions(self):
        r = asyncio.run(server.do_ask("When did Nanaji and Nani get married?"))
        self.assertTrue(r["conflicts"])
        self.assertIn("1970", r["say"] + str(r["conflicts"]))
        self.assertIn("1971", r["say"] + str(r["conflicts"]))


class GapEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed.main()
        cls.conn = store.connect()

    def _rank(self, name, asked=()):
        e = store.find_elder(self.conn, name)
        return gaps.rank(e, store.list_memories(self.conn, e["id"]), list(asked))

    def test_missing_allergy_outranks_life_story(self):
        ranked = self._rank("Nani")
        self.assertEqual(ranked[0]["key"], "allergies")
        self.assertGreater(ranked[0]["score"], max(g["score"] for g in ranked if g["kind"] == "Life story"))

    def test_known_things_are_not_asked_again(self):
        keys = {g["key"] for g in self._rank("Nanaji")}
        self.assertNotIn("allergies", keys)  # penicillin is on record
        self.assertNotIn("property", keys)  # house papers are on record

    def test_old_medicines_come_up_for_recheck(self):
        self.assertTrue(any(g["kind"] == "Recheck" for g in self._rank("Nanaji")))

    def test_skipped_question_sinks(self):
        top = self._rank("Nani")[0]
        after = self._rank("Nani", asked=[top["question"]])
        self.assertNotEqual(after[0]["key"], top["key"])


PNG_1PX = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360f8cf00000301010018dd8db00000000049454e44ae426082")


class FamilyFeatures(unittest.TestCase):
    def setUp(self):
        seed.main()
        self.conn = store.connect()
        self.wedding = next(m for m in store.list_memories(self.conn) if m["title"].startswith("Sadda viyah"))

    def test_photo_is_stored_and_fake_files_are_refused(self):
        media = store.add_media(self.conn, self.wedding["id"], PNG_1PX, "Wedding day")
        self.assertEqual((media["kind"], media["mime"]), ("photo", "image/png"))
        self.assertTrue((store.MEDIA_DIR / media["file"]).is_file())
        with self.assertRaises(ValueError):
            store.add_media(self.conn, self.wedding["id"], b"<script>alert(1)</script>")

    def test_voice_recording_is_kept_as_audio(self):
        webm = bytes.fromhex("1a45dfa3") + b"\x00" * 64
        self.assertEqual(store.add_media(self.conn, self.wedding["id"], webm)["kind"], "voice")

    def test_correction_waits_for_the_elder_and_keeps_original_words(self):
        pending = store.suggestions_for(self.conn, self.wedding["id"], "pending")
        self.assertEqual(len(pending), 1)  # Simran's seeded suggestion
        self.assertEqual(store.get_memory(self.conn, self.wedding["id"])["year"], 1971)  # unchanged until approved
        store.decide(self.conn, pending[0]["id"], True, "Nani")
        after = store.get_memory(self.conn, self.wedding["id"])
        self.assertEqual(after["year"], 1970)
        self.assertEqual(after["transcript"], self.wedding["transcript"])
        self.assertEqual(store.conflicts(self.conn), [])  # the two versions now agree
        with self.assertRaises(ValueError):
            store.decide(self.conn, pending[0]["id"], True, "Nani")  # can't decide twice

    def test_suggestions_are_redacted_and_fields_whitelisted(self):
        s = store.suggest(self.conn, self.wedding["id"], "Cousin", "summary", "Locker pin is 4821")
        self.assertNotIn("4821", s["new_value"])
        with self.assertRaises(ValueError):
            store.suggest(self.conn, self.wedding["id"], "Cousin", "elder_id; DROP TABLE memories", "x")

    def test_graph_links_shared_people_and_marks_history_as_context(self):
        g = store.graph(self.conn)
        gurnam = next(n for n in g["nodes"] if n["label"] == "Gurnam")
        self.assertEqual(len(set(gurnam["memories"])), 2)  # both wedding versions mention him
        self.assertTrue(all(e["kind"] == "context" for e in g["edges"] if e["target"].startswith("event:")
                            or e["source"].startswith("event:")))
        self.assertIn("Nani's mother", {n["label"] for n in g["nodes"]})


if __name__ == "__main__":
    unittest.main()

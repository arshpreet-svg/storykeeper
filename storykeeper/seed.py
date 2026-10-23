"""Load a fictional demo family so the dashboard and the video have something to show.

Run: python -m storykeeper.seed   (wipes the existing database and uploaded media first)
"""

import time

from . import store

ELDERS = [
    ("Nanaji", "Kartar Singh Grewal", "Maternal grandfather", 1944, "Lyallpur (now Faisalabad)"),
    ("Nani", "Surjit Kaur Grewal", "Maternal grandmother", 1949, "Ludhiana"),
]

# (elder, shelf, title, year, place, people, summary, transcript, details[, extra add_memory kwargs])
MEMORIES = [
    ("Nanaji", "story", "Leaving Lyallpur on a bullock cart", 1947, "Lyallpur",
     ["Bebe", "Bapuji"],
     "At three, Nanaji left Lyallpur on a bullock cart with his parents during Partition. He only remembers "
     "Bebe's dupatta tied around his wrist \"so I would not get lost in the crowd\".",
     "I was three when we left Lyallpur. We went on a bullock cart. I only remember Bebe tied her dupatta around "
     "my wrist so I would not get lost in the crowd.", {}),
    ("Nanaji", "story", "The tube well in Samrala", 1958, "Samrala",
     ["Bapuji"],
     "As a teenager in Samrala he helped Bapuji dig the village's first tube well. When water came up, "
     "\"the whole village came running with buckets, like it was Diwali.\"",
     "When I was fourteen, Bapuji and I dug the first tube well in Samrala. When the water came up the whole "
     "village came running with buckets, like it was Diwali.", {}),
    ("Nanaji", "story", "First job at Punjab Roadways", 1965, "Ludhiana",
     [],
     "His first job was as a conductor at Punjab Roadways on the Ludhiana-Chandigarh route, earning ₹90 a month. "
     "He bought his mother a steel trunk with his first salary.",
     "My first job was conductor in Punjab Roadways, Ludhiana to Chandigarh route. Ninety rupees a month. "
     "With the first salary I bought Bebe a steel trunk.", {}),
    ("Nanaji", "story", "Meeting Surjit at the gurdwara", 1969, "Ludhiana",
     ["Surjit Kaur"],
     "He first saw Nani serving langar at the Dukh Niwaran gurdwara. He went back \"every Sunday for two months\" "
     "before his mother spoke to her family.",
     "I saw your Nani serving langar at Dukh Niwaran Sahib. I went back every Sunday for two months before Bebe "
     "spoke to her family.", {}),
    ("Nanaji", "story", "The 1971 blackout nights", 1971, "Ludhiana",
     ["Surjit Kaur"],
     "During the 1971 war he drove night buses with the headlights painted black. Nani kept a lantern in the "
     "window so he could find home.",
     "In 1971 there was the war. We drove night buses with headlights painted black. Your Nani kept a lantern in "
     "the window so I could find home.", {}),
    ("Nanaji", "health", "Type 2 diabetes since 52", 1996, None,
     ["Bapuji"],
     "Nanaji has had type 2 diabetes since age 52 and takes metformin morning and night. His father Bapuji also "
     "had \"sugar\" from his fifties.",
     "I have sugar since I was fifty-two. I take metformin morning and night. My father also had sugar from his "
     "fifties.", {"condition": "Type 2 diabetes", "onset_age": 52, "medicines": ["Metformin (morning & night)"]}),
    ("Nanaji", "health", "Penicillin allergy", 1982, None,
     [],
     "He is allergic to penicillin; in 1982 an injection gave him a rash all over his body.",
     "Tell the doctors I am allergic to penicillin. In 1982 one injection gave me rash all over.",
     {"condition": "Penicillin allergy", "onset_age": 38}),
    ("Nanaji", "vault", "House papers in the Godrej almirah", 2024, "Home",
     [],
     "The registry of the Model Town house is in the Godrej almirah, top locker, inside a red cloth file. "
     "The key hangs behind the Guru Nanak calendar in the bedroom.",
     "The registry of the Model Town house is in the Godrej almirah, top locker, in the red cloth file. The key "
     "hangs behind the Guru Nanak calendar in the bedroom.",
     {"item": "House registry (Model Town)", "location": "Godrej almirah, top locker, red cloth file; key behind "
      "the Guru Nanak calendar in the bedroom"}),
    ("Nanaji", "vault", "LIC policy and agent", 2024, None,
     ["Mr. Bhatia"],
     "His LIC policy papers are in the blue folder under the bed. The agent is Mr. Bhatia from Ghumar Mandi, "
     "who \"knows everything about the policy\".",
     "LIC policy is in the blue folder under the bed. The agent is Bhatia ji from Ghumar Mandi, he knows "
     "everything about the policy.",
     {"item": "LIC life insurance policy", "location": "Blue folder under the bed",
      "contact": "Mr. Bhatia, LIC agent, Ghumar Mandi"}),
    ("Nanaji", "wisdom", "Never sign in a hurry", 1990, None,
     [],
     "His rule: \"Never sign anything the same day. Sleep on it, then read it again in the morning.\"",
     "Never sign anything the same day. Sleep on it, read it again in the morning.", {}),
    ("Nani", "story", "Phulkari for her own wedding", 1969, "Ludhiana",
     ["her mother"],
     "Nani embroidered her own wedding phulkari over a whole winter with her mother. It is still in the trunk, "
     "\"for whichever granddaughter marries first.\"",
     "I made my own wedding phulkari with my mother, one whole winter. It is still in the trunk, for whichever "
     "granddaughter marries first.", {}),
    ("Nani", "recipe", "Nani's mango pickle", 1975, None,
     [],
     "Nani's raw-mango pickle: sun-dried mango pieces with mustard oil, saunf, methi, kalonji, haldi and red chilli, "
     "kept in the sun for ten days and stirred only with a dry wooden spoon.",
     "Cut raw mangoes, dry them one full day in the sun. Heat mustard oil till it smokes then cool it. Mix saunf, "
     "methi, kalonji, haldi, red chilli and salt. Fill the barni, pour the oil to cover. Keep in sun ten days. "
     "Only dry wooden spoon, never wet.",
     {"ingredients": ["Raw mangoes", "Mustard oil", "Saunf", "Methi seeds", "Kalonji", "Haldi", "Red chilli",
                      "Salt"],
      "steps": ["Cut raw mangoes and sun-dry one full day", "Heat mustard oil till it smokes, then cool",
                "Mix saunf, methi, kalonji, haldi, red chilli and salt with the mango",
                "Fill the barni and cover fully with oil", "Keep in the sun for ten days",
                "Stir only with a dry wooden spoon"]}),
    ("Nani", "recipe", "Sunday sarson da saag", 1980, None,
     [],
     "Her Sunday sarson da saag: sarson, bathua and palak boiled for three hours, mashed with a wooden ghotna, "
     "finished with a spoon of makki atta and a tadka of ghee, garlic and green chilli.",
     "Sarson, bathua and a little palak, boil three hours. Mash with the ghotna. One spoon makki atta. Tadka of "
     "ghee, garlic, green chilli. Serve with white butter.",
     {"ingredients": ["Sarson", "Bathua", "Palak", "Makki atta", "Ghee", "Garlic", "Green chilli", "White butter"],
      "steps": ["Boil sarson, bathua and palak for three hours", "Mash with a wooden ghotna",
                "Stir in one spoon of makki atta", "Finish with a tadka of ghee, garlic and green chilli",
                "Serve with white butter"]}),
    ("Nani", "health", "Thyroid and knee", 2008, None,
     [],
     "Nani has hypothyroidism since age 59 and takes thyroxine 50 mcg empty stomach every morning. Her left knee "
     "was operated on in 2015 at DMC.",
     "I have thyroid since fifty-nine, I take thyroxine fifty every morning empty stomach. My left knee was "
     "operated in 2015 at DMC.",
     {"condition": "Hypothyroidism; left knee surgery (2015, DMC)", "onset_age": 59,
      "medicines": ["Thyroxine 50 mcg (morning, empty stomach)"]}),
    ("Nani", "health", "Her mother's heart", 1985, None,
     ["her mother"],
     "Nani's mother died of a heart attack at 61; Nani says the children should \"get their heart checked after "
     "forty\".",
     "My mother went with a heart attack at sixty-one. Tell the children to get their heart checked after forty.",
     {"condition": "Heart attack (Nani's mother, at 61)", "onset_age": 61}),
    ("Nani", "vault", "Gold and the bank locker", 2024, None,
     [],
     "The family gold is in the Punjab National Bank locker at Ghumar Mandi; the locker key is in her steel "
     "dabba inside the rice drum.",
     "The gold is in the PNB locker at Ghumar Mandi. Locker key is in my steel dabba inside the rice drum.",
     {"item": "Family gold / bank locker", "location": "PNB locker, Ghumar Mandi; key in the steel dabba inside "
      "the rice drum"}),
    ("Nani", "wisdom", "Dr. Sandhu, the family doctor", 2010, None,
     ["Dr. Sandhu"],
     "Dr. Sandhu at Sandhu Clinic, Sarabha Nagar, has treated the family for twenty years and \"knows all our "
     "reports\".",
     "Dr. Sandhu in Sarabha Nagar has seen us for twenty years. He knows all our reports.",
     {"contact": "Dr. Sandhu, Sandhu Clinic, Sarabha Nagar"}),
    # Two versions of the same wedding: Storykeeper keeps both until the family settles it.
    ("Nanaji", "story", "Our wedding at Dukh Niwaran Sahib", 1970, "Ludhiana",
     ["Surjit Kaur", "Gurnam"],
     "Nanaji says they married at Dukh Niwaran Sahib in 1970. The baraat travelled on a Punjab Roadways bus driven "
     "by his friend Gurnam, \"the only baraat in Ludhiana with a conductor\".",
     "We got married at Dukh Niwaran Sahib in 1970. The baraat went on a Punjab Roadways bus, my friend Gurnam "
     "was driving. Only baraat in Ludhiana with a conductor!", {}),
    ("Nani", "story", "Sadda viyah - our wedding", 1971, "Ludhiana",
     ["Kartar Singh", "Gurnam"],
     "Nani remembers their wedding at Dukh Niwaran Sahib in 1971. The baraat came on a Punjab Roadways bus that "
     "Nanaji borrowed through his driver friend, and she wore the red phulkari she had embroidered.",
     "Sadda viyah 1971 vich hoya si, Dukh Niwaran Sahib. Baraat Punjab Roadways di bus te aayi si, tuhade Nanaji "
     "ne apne driver dost nu keh ke mangwayi. Main oh laal phulkari paayi si jo maa naal kaddi si.", {},
     {"language": "Punjabi-English",
      "translation": "Our wedding happened in 1971, at Dukh Niwaran Sahib. The baraat came on a Punjab Roadways "
                     "bus - your Nanaji asked his driver friend for it. I wore the red phulkari I embroidered with "
                     "my mother."}),
    # Spoken in Punjabi-English, with cooking cues kept instead of invented timings.
    ("Nani", "recipe", "Khatti kadhi with pakode", 1985, None,
     [],
     "Nani's kadhi uses slightly sour lassi whisked with besan, haldi and salt, simmered on a low flame "
     "\"until a malai-like layer comes on top\". The tadka of methi dana and dry red chilli goes in \"until the "
     "khushboo comes\". She never measures: \"andaza naal\".",
     "Lassi thodi khatti honi chahidi. Besan ghol lo, thodi haldi te namak. Halki aanch te pakao, jad tak upar "
     "malai jahi parat na aa jaye. Pakode alag tal ke. Tadka vich methi dana te sukhi laal mirch, jad tak "
     "khushboo na aa jaye. Main kade naap ke nahi paya, sab andaza naal.",
     {"ingredients": ["Slightly sour lassi", "Besan", "Haldi", "Salt", "Besan pakoras", "Methi dana",
                      "Dry red chilli"],
      "steps": ["Whisk besan into the sour lassi with a little haldi and salt",
                "Simmer on a low flame until a malai-like layer forms on top (cue, not a fixed time)",
                "Fry the pakoras separately and add them",
                "Tadka: methi dana and dry red chilli, until the aroma comes (cue, not a fixed time)"],
      "quantities": "Not measured - \"andaza naal\" (by feel). No amounts have been invented."},
     {"language": "Punjabi-English",
      "translation": "The lassi should be a little sour. Whisk in besan, a little haldi and salt. Cook on a low "
                     "flame until a cream-like layer forms on top. Fry the pakoras separately. For the tadka, "
                     "methi seeds and dry red chilli, until the aroma comes. I never measured anything, it's all "
                     "by feel."}),
]


def main():
    if store.DB_PATH.exists():
        store.DB_PATH.unlink()
    for f in store.MEDIA_DIR.glob("*") if store.MEDIA_DIR.exists() else []:
        f.unlink()
    conn = store.connect()
    for e in ELDERS:
        store.add_elder(conn, *e)
    # Spread recordings over the last ~6 months so older facts (like medicines) come up for a recheck.
    base = time.time() - 190 * 86400
    for i, (elder, shelf, title, year, place, people, summary, transcript, details, *extra) in enumerate(MEMORIES):
        eid = store.find_elder(conn, elder)["id"]
        store.add_memory(conn, eid, shelf, title, transcript, summary, year, place, people, details,
                         created_at=base + i * 9 * 86400, source="seed", **(extra[0] if extra else {}))
    # A granddaughter's correction, waiting for Nani to approve (her original words stay untouched either way).
    wedding = next(m for m in store.list_memories(conn) if m["title"].startswith("Sadda viyah"))
    store.suggest(conn, wedding["id"], "Simran (granddaughter)", "year", "1970",
                  "The wedding card in Nani's trunk says 14 November 1970.")
    print(f"Seeded {len(ELDERS)} elders and {len(MEMORIES)} memories into {store.DB_PATH}")


if __name__ == "__main__":
    main()

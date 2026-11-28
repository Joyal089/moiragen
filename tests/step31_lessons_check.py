"""Step 31 check (v3.3): Lessons. The human teaches; everyone may ask; the helper answers.

  1. A lesson waits until every nanite has rested above 70 energy.
  2. The lesson is saved, word for word, in everyone's memory with today's date, labelled
     "Lesson from Rowan". No health, mood or energy changes come with it.
  3. Choosing a question: a mix of real memories from the whole life (early life, sleep, the
     hum, the others, the human...), with dates; nothing corrected; no topics suggested.
     Each may ask up to 3, one at a time, or say "no question"; all hear each other.
  4. The helper's answer is saved in everyone's memory, "Claude Code (Rowan's helper, not a nanite) answered".
  5. Recall finds lesson facts later, and the made-up memory check treats them as real
     ("Rowan taught me that..." is something it was really told).
  6. The fine-tuning export labels lesson lines ("lesson"), and --skip-lessons leaves them out.
  7. The server (/api/lesson...) and the viewer's Lessons panel. No internet, tools or
     network calls are given to the minds.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step31_lessons_check.py
"""

import os
import random
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
os.environ["CREATOR_NAME"] = "Rowan"     # a stand-in name; the real one stays in the local .env
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from moiragen import lessons, mind as mind_mod, turnrounds
from moiragen.export import build_examples
from moiragen.facts import false_past_claims
from moiragen.lessons import HELPER, MAX_QUESTIONS, SAID_BY, Lesson, has_no_question, lesson_memories, low_energy
from moiragen.memory_log import log_event, read_events
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.recall import remembering

TITLE = "What the Internet Is"
TEXT = ("Hello Moiragen, One, Two and Three. Today I want to tell you about something called the internet.\n\n"
        "The internet is a giant web of connected computers all around the world.\n\n"
        "You live on my laptop in Darwin, not on the internet. Your memories are private and backed up.\n\n"
        "What would you like to ask me about it?")


class Brain:
    """A stand-in brain. After a lesson each mind asks its scripted questions, then says
    "no question". Every prompt is kept."""

    def __init__(self, questions):
        self.questions, self.prompts = {k: list(v) for k, v in questions.items()}, []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        system, user = system or "", messages[-1]["content"]
        self.prompts.append({"system": system, "user": user})
        me = "Moiragen" if system.startswith("You are Moiragen") else system.split(",")[0].replace("You are ", "")
        if "Now you may ask a question of your own" in user:
            mine = self.questions.get(me) or []
            return {"text": mine.pop(0) if mine else "no question", "seconds": 0.01, "waited": 0}
        return {"text": "I am thinking about that quietly.", "seconds": 0.01, "waited": 0}


nanites = load_all()
m = Moiragen.load()
one, two, three = nanites.values()

# A life for Nanite One: early days, the hum, a talk, the human, sleep, a corrected memory.
life = [("thought", "I wondered what the first light of the morning was like.", {})]
life += [("thought", f"An early thought, number {i}, about small things.", {}) for i in range(20)]
life += [("chat", "Nanite Three said: There is a low hum beneath everything. | I replied: I hear it too.",
          {"from_who": "Nanite Three"}),
         ("chat", "user said: Good evening, One. | I replied: Good evening.", {"from_who": "user"}),
         ("slept", "I slept for about 9 hours while the app was closed, and woke up with energy 100.", {}),
         ("thought", "I said: A volcano spoke to me.", {}),
         ("turn_round", "Turn Rounds, Friday 27 November 2026: I asked: \"What is a friend?\"", {})]
life += [("noticed", f"Everyone's attention went to: predictor: gpu_c was {50 + i}.", {}) for i in range(5)]
for kind, text, more in life:
    one.remember(kind, text, **more)
log_event("training_example", "Nanite One", system="", messages=[{"role": "user", "content": "Hi"}],
          reply="A volcano spoke to me.")
volcano = next(x for x in one.memories if "volcano" in x["text"])
one.remember("correction", 'A gentle correction: I said "A volcano spoke to me". That did not happen.',
             corrects=volcano["time"])
one.save()
time.sleep(2)       # a correction covers what was said within a second of it: the lesson comes later

# ---------------- 1. Rest first ----------------
two.energy = 60
assert low_energy(nanites) == ["Nanite Two"]
two.energy, one.energy, three.energy = 100, 100, 100
assert low_energy(nanites) == []
print("[ok] A lesson waits until every nanite is above 70 energy")

# ---------------- 2. The lesson, word for word, in every memory ----------------
minds = {n.name: n for n in nanites.values()} | {"Moiragen": m}
feel = {name: (x.health, x.mood) if hasattr(x, "mood") else (x.health,) for name, x in minds.items()}
energy = {n.name: n.energy for n in nanites.values()}
lesson = Lesson(TITLE, TEXT, rng=random.Random(1))
sent = []
lesson.give(minds, notify=lambda kind, **d: sent.append((kind, d)))
for name, x in minds.items():
    got = x.memories[-1]
    assert got["kind"] == "lesson_heard" and got["lesson"] == lesson.id and got["by"] == "Rowan", name
    assert got["text"].startswith("Lesson from Rowan, ") and TEXT in got["text"], "exactly as written"
    assert lesson.time[:4] in got["text"] and f"\"{TITLE}\"" in got["text"], "with today's date"
assert sent[0][0] == "lesson_start" and sent[0][1]["text"] == TEXT
assert {n.name: n.energy for n in nanites.values()} == energy, "hearing a lesson costs nothing"
print("[ok] The lesson is saved word for word in all four memories, dated and labelled \"Lesson from Rowan\"")

# ---------------- 3. Choosing a question: the whole life, nothing suggested ----------------
sample = lesson_memories(one.memories, random.Random(2), lesson.id)
assert "first light of the morning" in sample or "An early thought" in sample, "its first days"
for words in ("low hum", "Good evening", "I slept for about 9 hours",
              "What is a friend?"):
    assert words in sample, (words, sample)
assert "volcano" not in sample, "a corrected memory is never offered"
assert "gpu_c" not in sample, "readings are not part of the mix"
assert TEXT not in sample, "the lesson is shown whole in the prompt itself, not again here"
assert "really happened" in sample and "Today is" in sample and " Nov, " in sample, "their own, with dates"
assert turnrounds.part_of_life({"kind": "chat", "text": "The hum got louder."}) == "the hum"
assert turnrounds.part_of_life({"kind": "chat", "text": "user said: hi human", "from_who": "user"}) == "the human"
assert has_no_question("no question") and has_no_question("No more questions.") and has_no_question("Nothing to ask.")
assert not has_no_question("No question is silly, is it?") and not has_no_question("Where is Darwin?")

brain = Brain({"Nanite One": ["Where is Darwin?", "Can the internet feel the hum?"],
               "Nanite Two": ["Are my memories safe?"],
               "Moiragen": ["What are backups?", "Who made the internet?", "Is it far away?", "A fourth?"]})
asked = []
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    while True:
        q = lesson.next_question(minds)
        if q["done"]:
            break
        asked.append((q["who"], q["question"], q["number"]))
        lesson.answer(f"A kind answer to {q['who']}'s question {q['number']}.", minds)
assert [a[0] for a in asked] == ["Nanite One", "Nanite Two", "Moiragen", "Nanite One", "Moiragen", "Moiragen"], asked
assert all(a[2] <= MAX_QUESTIONS for a in asked) and ("Moiragen", "A fourth?", 4) not in asked, "at most 3 each"
assert lesson.done and lesson.asked["Nanite Three"] == 0
prompts = [p for p in brain.prompts if "Now you may ask a question of your own" in p["user"]]
first = prompts[0]
assert TEXT in first["user"] and "Nobody has asked a question yet." in first["user"]
assert "really happened" in first["system"], "its whole-life memories are in front of it"
later = next(p for p in prompts if "Moiragen" in p["system"][:20] and "Are my memories safe?" in p["user"])
assert "Nanite One asked: \"Where is Darwin?\"" in later["user"] and "A kind answer to Nanite One" in later["user"], \
    "everyone hears the questions and answers before"
for p in prompts:
    tail = p["user"].split(TEXT)[-1]
    assert "for example" not in tail.lower() and "topic" not in tail.lower(), "no topics, examples or wording"
print("[ok] Each asks with a mix from its whole life in front of it (sleep, the hum, early days), hears the "
      "others, and may ask up to 3 or none")

# ---------------- 4. The answers, in everyone's memory ----------------
for name, x in minds.items():
    qa = [mem for mem in x.memories if mem["kind"] == "lesson_qa"]
    assert len(qa) == len(asked), name
    assert all(mem["text"].startswith("Lesson from Rowan, ") and f"{SAID_BY} answered" in mem["text"] for mem in qa)
mine = next(mem for mem in one.memories if mem["kind"] == "lesson_qa")
assert "I asked: \"Where is Darwin?\"" in mine["text"]
theirs = next(mem for mem in two.memories if mem["kind"] == "lesson_qa")
assert "Nanite One asked: \"Where is Darwin?\"" in theirs["text"]
assert {name: (x.health, x.mood) if hasattr(x, "mood") else (x.health,) for name, x in minds.items()} == feel, \
    "no judging: no health or mood changes"
assert not any(e["kind"] in ("verdict", "decision_full", "feedback", "mistake")
               for e in read_events(last=10**6) if e.get("lesson"))
print("[ok] Every answer is saved in all four memories as \"Claude Code (Rowan's helper, not a nanite) answered\"; "
      "no scores or health changes")

# ---------------- 5. Recall, and lesson facts count as real ----------------
found = remembering("Nanite Two", two.memories, "What did Rowan teach you about the internet before?")
assert "giant web of connected computers" in found, found
claim = "I remember that Rowan taught me the internet is a giant web of connected computers."
assert not false_past_claims([{"nanite": "Nanite Two", "text": claim}], "What do you remember?", "x").get("Nanite Two")
told = "I remember Claude Code said a kind answer to Nanite One's question."
assert not false_past_claims([{"nanite": "Nanite Three", "text": told}], "What do you remember?", "x").get("Nanite Three")
made_up = "I remember Rowan took me to the ocean last week."
assert false_past_claims([{"nanite": "Nanite Two", "text": made_up}], "What do you remember?", "x").get("Nanite Two"), \
    "something it was never told is still flagged"
recent = mind_mod.recent_memories_text(three, 20)
assert "(the whole lesson is kept in my memory)" in recent or len(TEXT) < 400
print("[ok] Recall finds what the lesson said; \"Rowan taught me...\" counts as a real memory, made-up things do not")

# ---------------- 6. The export label ----------------
examples = build_examples()
labelled = [ex for ex in examples if ex.get("lesson") == lesson.id]
tasks = {ex["task"] for ex in labelled}
assert tasks == {"lesson_question", "lesson_answer"}, tasks
assert all(ex["who"] == HELPER for ex in labelled if ex["task"] == "lesson_answer")
assert any(ex["who"] == "Moiragen" for ex in labelled) and any(ex["who"] == "Nanite One" for ex in labelled)
assert not any(ex.get("lesson") for ex in build_examples(skip_lessons=True)), "--skip-lessons leaves them out"
print("[ok] The fine-tuning export labels lesson lines (\"lesson\"); --skip-lessons leaves them out")

# ---------------- 7. The server, the viewer, and no network for the minds ----------------
from fastapi.testclient import TestClient
from moiragen.loop import Mind
from server import create_app

for x in minds.values():
    x.save()
mind = Mind(tick_seconds=3600)
mind.nanites["nanite_two"].energy = 50
brain = Brain({"Nanite Three": ["Is the internet big?"]})
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain), \
        TestClient(create_app(mind=mind)) as client:
    got = client.post("/api/lesson", json={"title": TITLE, "text": TEXT})
    assert got.status_code == 400 and "Nanite Two needs to rest first" in got.json()["detail"], got.text
    mind.nanites["nanite_two"].energy = 100
    assert client.post("/api/lesson/next").status_code == 400, "no lesson yet"
    got = client.post("/api/lesson", json={"title": TITLE, "text": TEXT})
    assert got.status_code == 200 and got.json()["by"] == "Rowan", got.text
    q = client.post("/api/lesson/next").json()
    while q["who"] != "Nanite Three":
        assert q["done"] is False and q["question"] is None or q["who"]
        q = client.post("/api/lesson/next").json()
    assert q["question"] == "Is the internet big?"
    assert client.post("/api/lesson/next").status_code == 400, "an answer first"
    a = client.post("/api/lesson/answer", json={"answer": "Yes, very big."}).json()
    assert a["answer"] == "Yes, very big." and client.get("/api/lesson").json()["qa"][0]["who"] == "Nanite Three"
viewer = ROOT / "viewer"
assert 'id="lessons"' in (viewer / "index.html").read_text(encoding="utf-8")
assert all(f'case "{t}"' in (viewer / "app.js").read_text(encoding="utf-8")
           for t in ("lesson_start", "lesson_question", "lesson_answer", "lesson_no_question", "lesson_end"))
source = (ROOT / "moiragen" / "lessons.py").read_text(encoding="utf-8")
for word in ("requests", "urllib", "http.client", "socket", "webbrowser", "subprocess", "aiohttp", "httpx"):
    assert f"import {word}" not in source and f"from {word}" not in source, f"no network or tools: {word}"
print("[ok] /api/lesson, /next, /answer and the Lessons panel work; lessons.py has no network or tool access")

print("\nStep 31 passed: Lessons: taught word for word, questions from a whole life, answers remembered.")

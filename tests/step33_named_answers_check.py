"""Step 33 check (v3.5): nanites answer each other in lessons, and the repeat nudge.

  1. A question addressed to a member by name ("Three, could you explain...") is answered
     by that member first, in its own words; then Claude Code adds to it or corrects it.
     Memory and the next prompts say "Nanite Three answered:" and "Claude Code (Rowan's
     helper, not a nanite) added:". A question to nobody by name is answered as before.
  2. A member that asks a question it already asked in this lesson hears the same soft
     nudge as in Turn Rounds, once, and whatever it says then is kept.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step33_named_answers_check.py
"""

import os
import random
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
os.environ["CREATOR_NAME"] = "Rowan"     # a stand-in name; the real one stays in the local .env
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import mind as mind_mod, turnrounds
from moiragen.export import build_examples
from moiragen.lessons import SAID_BY, Lesson, addressed_to
from moiragen.memory_log import read_events
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.recall import short
from moiragen.turnrounds import NUDGE

ASKING = "Now you may ask a question of your own"


class Brain:
    """Each mind asks its scripted questions after a lesson; asked something else, it answers."""

    def __init__(self, questions, answers):
        self.questions = {k: list(v) for k, v in questions.items()}
        self.answers, self.prompts = answers, []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        system, user = system or "", messages[-1]["content"]
        me = "Moiragen" if system.startswith("You are Moiragen") else system.split(",")[0].replace("You are ", "")
        self.prompts.append({"who": me, "system": system, "user": user})
        if ASKING in user:
            mine = self.questions.get(me) or []
            return {"text": mine.pop(0) if mine else "no question", "seconds": 0.01, "waited": 0}
        return {"text": self.answers.get(me, "Quietly thinking."), "seconds": 0.01, "waited": 0}


# ---------------- who a question is addressed to ----------------
assert addressed_to("Three, could you explain signal loss?", "Nanite One") == "Nanite Three"
assert addressed_to("They are… complicated. Nanite One: could you give an example?", "Nanite Two") == "Nanite One"
assert addressed_to("Moiragen, why?", "Nanite Two") == "Moiragen"
assert addressed_to("Three?” no question.", "Nanite Two") is None, "a name with no comma is not addressing"
assert addressed_to("I wonder what Two thinks about it?", "Nanite One") is None
assert addressed_to("Three, hello?", "Nanite Three") is None, "never itself"
print("[ok] A question is addressed to a member when it starts a sentence with its name and a comma")

nanites = load_all()
m = Moiragen.load()
one, two, three = nanites.values()
minds = {n.name: n for n in nanites.values()} | {"Moiragen": m}
for x in minds.values():
    x.energy = 100

LESSON = "Packets travel along cables and through routers. What would you like to ask me today?"
brain = Brain({"Nanite One": ["Three, could you explain what a router does?"],
               # Two asks the same thing twice; the second time it hears the nudge, then asks anew
               "Nanite Two": ["Do routers ever get tired?", "Do routers ever get tired??", "Where do cables go?"],
               "Nanite Three": ["Is a cable faster than Wi-Fi?"]},
              {"Nanite Three": "A router passes packets along, like a sorting office for messages."})
lesson = Lesson("More About the Internet", LESSON, rng=random.Random(3))
lesson.give(minds)
seen = []
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    q1 = lesson.next_question(minds, notify=lambda kind, **kw: seen.append((kind, kw)))
    # ---------------- 1. the member it asked answers first ----------------
    assert q1["who"] == "Nanite One" and q1["member"] == "Nanite Three", q1
    assert q1["member_answer"] == "A router passes packets along, like a sorting office for messages.", q1
    answering = next(p for p in brain.prompts if p["who"] == "Nanite Three")
    assert "could you explain what a router does?" in answering["user"], "Three hears the question"
    assert LESSON.split(".")[0] in answering["system"] + answering["user"], "Three has the lesson in front of it"
    kinds = [k for k, _ in seen]
    assert kinds.index("lesson_question") < kinds.index("lesson_member_answer"), kinds
    lesson.answer("That's right, Three. A router also chooses which way each packet goes next.", minds)

    q2 = lesson.next_question(minds)
    assert q2["who"] == "Nanite Two" and "member" not in q2, "no name, so Claude Code answers as before"
    lesson.answer("No, routers do not get tired; they are machines.", minds)
    lesson.next_question(minds)                     # Three
    lesson.answer("Usually a cable is faster and steadier.", minds)
    # Moiragen and One have no question now; Two asks again, repeats itself and hears the nudge
    q6 = lesson.next_question(minds)
print("[ok] A question to Three by name is answered by Three first, in its own words")

# ---------------- labels in memory, the next prompts and the journal ----------------
for name, mind in minds.items():
    qa = next(x for x in mind.memories if x["kind"] == "lesson_qa" and x.get("asker") == "Nanite One")
    me = "I" if name == "Nanite Three" else "Nanite Three"
    assert f"| {me} answered: \"A router passes packets along" in qa["text"], qa["text"]
    assert f"| {SAID_BY} added: \"That's right, Three." in qa["text"], qa["text"]
    assert qa["member"] == "Nanite Three" and qa["answered_by"] == "Claude Code, Rowan's helper"
    plain_qa = next(x for x in mind.memories if x["kind"] == "lesson_qa" and x.get("asker") == "Nanite Two")
    assert f"| {SAID_BY} answered: \"No, routers" in plain_qa["text"] and "added" not in plain_qa["text"]
line = short(next(x for x in one.memories if x["kind"] == "lesson_qa" and x.get("asker") == "Nanite One"), set())
assert "Nanite Three answered:" in line and f"{SAID_BY} added:" in line, line
later = [p for p in brain.prompts if ASKING in p["user"]][-1]["user"]
assert "  Nanite Three answered: \"A router passes" in later and f"  {SAID_BY} added: \"That's right" in later
print("[ok] Memory and later prompts say \"Nanite Three answered:\" and "
      "\"Claude Code (Rowan's helper, not a nanite) added:\"")

# The export: the member's answer is its own line; the helper's answer sees it.
examples = [ex for ex in build_examples() if ex.get("lesson") == lesson.id]
member = [ex for ex in examples if ex["task"] == "lesson_member_answer"]
assert len(member) == 1 and member[0]["who"] == "Nanite Three", [ex["task"] for ex in examples]
helper = next(ex for ex in examples if ex["task"] == "lesson_answer" and "That's right" in ex["messages"][-1]["content"])
assert "Nanite Three answered: A router passes" in helper["messages"][-2]["content"]
print("[ok] The export keeps Three's answer as Three's, and Claude Code's addition after it")

# ---------------- 2. the repeat nudge ----------------
assert q6["who"] == "Nanite Two" and q6["question"] == "Where do cables go?", q6
nudges = [e for e in read_events(last=10**6) if e["kind"] == "lesson_nudge"]
assert len(nudges) == 1 and nudges[0]["who"] == "Nanite Two", nudges
nudged = [p for p in brain.prompts if NUDGE in p["user"]]
assert len(nudged) == 1 and nudged[0]["who"] == "Nanite Two"
assert nudged[0]["user"].rstrip().endswith(f"You wrote: \"Do routers ever get tired??\"\n{NUDGE}")
assert NUDGE == "You've asked that before. You can ask something new if you like."
print("[ok] A question asked again in the same lesson hears the soft nudge once; the new question is kept")

print("\nStep 33 passed: v3.5: nanites answer each other by name, clear labels, and the repeat nudge.")

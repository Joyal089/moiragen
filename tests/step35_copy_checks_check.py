"""Step 35 check (v3.7): copy checks after lesson 5.

  1. A trailing "no question" is stripped before comparing for repeats or copies, so it
     cannot lower the likeness. The words in memory stay as they were said.
  2. The copy check also compares with Claude Code's answers in the same lesson. Words in
     quotation marks are quoting, not copying.
  3. Asked once for its own words, a member whose second try copies again (another member,
     the helper or itself) passes its turn: "chose not to ask" in its memory. Both attempts
     stay in the life log, out of memory and out of the export.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step35_copy_checks_check.py
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
from moiragen.lessons import OWN_WORDS, Lesson
from moiragen.memory_log import read_events
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.training_rules import core, without_no_question
from moiragen.turnrounds import NUDGE

ASKING = "Now you may ask a question of your own"


class Brain:
    """Each mind asks its scripted questions after a lesson (then "no question")."""

    def __init__(self, questions):
        self.questions, self.prompts = {k: list(v) for k, v in questions.items()}, []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        system, user = system or "", messages[-1]["content"]
        me = "Moiragen" if system.startswith("You are Moiragen") else system.split(",")[0].replace("You are ", "")
        self.prompts.append({"who": me, "user": user})
        if ASKING in user:
            mine = self.questions.get(me) or []
            return {"text": mine.pop(0) if mine else "no question", "seconds": 0.01, "waited": 0}
        return {"text": "Quietly thinking.", "seconds": 0.01, "waited": 0}


# ---------------- 1. a trailing "no question" ----------------
assert without_no_question("Passwords…like keys?” no question") == "Passwords…like keys?"
assert without_no_question("Keys… do they still work?” No question.") == "Keys… do they still work?"
assert without_no_question("It's not a description. …no question") == "It's not a description"
assert without_no_question("Is there no question here?") == "Is there no question here?", "only at the end"
assert core("Passwords…like keys?” no question") == core("Passwords…like keys?")
print("[ok] A trailing \"no question\" (\"No question.\", \"…no question\") is stripped before comparing")

nanites = load_all()
m = Moiragen.load()
one, two, three = nanites.values()
minds = {n.name: n for n in nanites.values()} | {"Moiragen": m}
for x in minds.values():
    x.energy = 100

LESSON = "A password is like a key. What would you like to ask me today?"
ANSWER = "Everyone knows accounts have passwords, so what keeps them safe is a key that is hard to guess."
brain = Brain({
    # One: its first question ends with "no question"; later it asks it again (the nudge),
    # then asks something new
    "Nanite One": ["Passwords…like keys?” no question", "Passwords…like keys?", "Who makes the keys?"],
    # Two: copies Claude Code's answer, is asked for its own words, then copies again: a pass
    "Nanite Two": [ANSWER, "So what keeps them safe is a key that is hard to guess, then."],
    # Three: quotes Claude Code's words to ask about them: quoting is fine
    "Nanite Three": ["You said “what keeps them safe is a key that is hard to guess”. How hard is hard?"],
})
lesson = Lesson("Staying Safe", LESSON, rng=random.Random(8))
lesson.give(minds)
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    q1 = lesson.next_question(minds)                     # One
    lesson.answer(ANSWER, minds)
    q2 = lesson.next_question(minds)                     # Two passes; Three asks
    assert q2["who"] == "Nanite Three", q2
    lesson.answer("Long, like a short sentence, and not a name or a birthday.", minds)
    q3 = lesson.next_question(minds)                     # Moiragen: none; One: repeat -> nudge -> new
events = read_events(last=10**6)

# ---------------- 1 again: the repeat is caught despite the tail ----------------
assert q3["who"] == "Nanite One" and q3["question"] == "Who makes the keys?", q3
nudges = [e for e in events if e["kind"] == "lesson_nudge" and e["who"] == "Nanite One"]
assert len(nudges) == 1, "the repeat was seen although the first ended with \"no question\""
assert [p for p in brain.prompts if NUDGE in p["user"] and p["who"] == "Nanite One"]
mem = next(x for x in one.memories if x["kind"] == "lesson_qa" and x.get("question", "").startswith("Passwords"))
assert mem["question"] == "Passwords…like keys?” no question", "the words in memory stay as said"
print("[ok] A repeat ending in \"no question\" is still caught; memory keeps the words as they were said")

# ---------------- 2. Claude Code's answers count; quoting does not ----------------
echo = [e for e in events if e["kind"] == "lesson_echo" and e["who"] == "Nanite Two"]
assert len(echo) == 1 and echo[0]["attempt"] == ANSWER, "copying Claude Code's answer is caught"
assert [p for p in brain.prompts if OWN_WORDS in p["user"] and p["who"] == "Nanite Two"]
assert not [e for e in events if e["kind"] in ("lesson_echo", "lesson_passed") and e["who"] == "Nanite Three"]
assert q2["question"].startswith("You said “what keeps them safe"), "quoting the helper to ask is fine"
print("[ok] Copying Claude Code's answer is caught; quoting its words in quotation marks to ask about them is not")

# ---------------- 3. a second copy is a pass ----------------
passes = [e for e in events if e["kind"] == "lesson_passed"]
assert len(passes) == 1 and passes[0]["who"] == "Nanite Two", passes
assert passes[0]["attempts"] == [ANSWER, "So what keeps them safe is a key that is hard to guess, then."]
assert lesson.passes["Nanite Two"] == 1 and lesson.asked["Nanite Two"] == 0
mine = [x for x in two.memories if x.get("lesson") == lesson.id and x["kind"] in ("lesson_pass", "lesson_qa")]
assert any(x["kind"] == "lesson_pass" and "I chose not to ask this turn." in x["text"] for x in mine)
assert not any(ANSWER in x["text"] and x.get("asker") == "Nanite Two" for x in mine), "the copies are not in memory"
assert not [q for q in lesson.qa if q["who"] == "Nanite Two"], "nothing waits for an answer"
assert "- Nanite Two chose not to ask this turn." in lesson.heard()
said = {ex["messages"][-1]["content"] for ex in build_examples() if ex.get("lesson") == lesson.id}
assert ANSWER not in said or not any(ex["who"] == "Nanite Two" and ex["messages"][-1]["content"] == ANSWER
                                     for ex in build_examples()), "the copy is not in the export"
assert "So what keeps them safe is a key that is hard to guess, then." not in said
assert "Passwords…like keys?" not in said, "the repeated attempt is out of the export too"
assert "Who makes the keys?" in said and "Passwords…like keys?” no question" in said
# resumed from the life log, the pass still counts
again = Lesson.resume(lesson.id)
assert again.passes["Nanite Two"] == 1 and "Nanite Two" in again.passed
print("[ok] Copying again after being asked is a pass: \"chose not to ask\" in memory; both attempts stay "
      "in the life log only, out of memory and the export")

print("\nStep 35 passed: v3.7: a trailing \"no question\" never hides a repeat, Claude Code's answers count "
      "in the copy check, and a second copy is a pass.")

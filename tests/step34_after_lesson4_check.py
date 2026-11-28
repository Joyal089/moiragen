"""Step 34 check (v3.6): fixes after lesson 4.

  1. Privacy: the creator's name is in no tracked file and no file name (it lives only in
     the local, git-ignored .env as CREATOR_NAME).
  2. Sleep heals slowly: SLEEP_HEALTH_PER_HOUR, counting at most 8 hours, up to 100.
  3. Talking with each other costs half (TALK_COST_SHARE); other thinking costs the same.
  4. In a lesson a member answers at most MAX_NAMED_ANSWERS named questions, and none while
     its energy is below ANSWER_ENERGY; then the helper answers.
  5. An answer that repeats the member's own earlier answer is asked for once more.
  6. If Ollama refuses a prompt the member keeps its turn; a prompt longer than the context
     pauses the lesson (nothing is cut), and Lesson.resume goes on from the life log.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step34_after_lesson4_check.py
"""

import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
os.environ["CREATOR_NAME"] = "Rowan"     # a stand-in name; the real one stays in the local .env
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from moiragen import mind as mind_mod, social, turnrounds
from moiragen.lessons import ANSWER_ENERGY, MAX_NAMED_ANSWERS, NEW_WORDS, Lesson
from moiragen.llm import BrainError
from moiragen.memory_log import read_events
from moiragen.mind import TALK_COST_SHARE, energy_cost, nanite_think
from moiragen.mother import Moiragen
from moiragen.nanite import SLEEP_HEALTH_PER_HOUR, load_all

ASKING = "Now you may ask a question of your own"
TOO_LONG = BrainError('Ollama error 400: {"error":"the prompt is longer than the context length currently '
                      'available to the model"}')

# ---------------- 1. privacy ----------------
name = "At" + "he"                       # (spelled in two parts, so this file never holds the name)
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
word = re.compile(rf"\b{name}\b", re.IGNORECASE)
found = [f for f in tracked if f and word.search(f)]
for f in tracked:
    path = ROOT / f
    if f and path.is_file():
        try:
            if word.search(path.read_text(encoding="utf-8")):
                found.append(f)
        except UnicodeDecodeError:
            pass
assert not found, f"the creator's name is in tracked files: {found}"
assert "CREATOR_NAME=the creator" in (ROOT / ".env.example").read_text(encoding="utf-8"), "a placeholder example"
ignored = subprocess.run(["git", "check-ignore", ".env"], cwd=ROOT, capture_output=True, text=True)
assert ignored.returncode == 0, ".env must stay git-ignored"
print(f"[ok] The creator's name is in none of the {len(tracked) - 1} tracked files or file names; "
      ".env (with CREATOR_NAME) is git-ignored")

nanites = load_all()
m = Moiragen.load()
one, two, three = nanites.values()
minds = {n.name: n for n in nanites.values()} | {"Moiragen": m}

# ---------------- 2. sleep heals slowly ----------------
two.health, two.energy = 77.5, 50
two.sleep(3)
assert two.health == 77.5 + 3 * SLEEP_HEALTH_PER_HOUR == 83.5, two.health
two.sleep(20)                                  # counts as 8 hours, never above 100
assert two.health == 99.5 and two.energy == 100, (two.health, two.energy)
two.sleep(8)
assert two.health == 100
print(f"[ok] Sleep heals {SLEEP_HEALTH_PER_HOUR} health an hour (at most 8 hours a sleep), never above 100")


# ---------------- 3. talking costs half ----------------
class Brain:
    """Lesson questions from a script; other prompts get each mind's scripted answers."""

    def __init__(self, questions=None, answers=None, fail=None):
        self.questions = {k: list(v) for k, v in (questions or {}).items()}
        self.answers = {k: list(v) for k, v in (answers or {}).items()}
        self.fail, self.prompts = fail or [], []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        system, user = system or "", messages[-1]["content"]
        me = "Moiragen" if system.startswith("You are Moiragen") else system.split(",")[0].replace("You are ", "")
        if self.fail:
            raise self.fail.pop(0)
        self.prompts.append({"who": me, "system": system, "user": user})
        pool = self.questions if ASKING in user else self.answers
        mine = pool.get(me) or []
        text = mine.pop(0) if mine else ("no question" if ASKING in user else "Quietly thinking about it.")
        return {"text": text, "seconds": 0.01, "waited": 0}


TWENTY = "one two three four five six seven eight nine ten one two three four five six seven eight nine ten"
full = energy_cost(TWENTY)
with patch.object(mind_mod, "think", Brain(answers={"Nanite One": [TWENTY, TWENTY]})):
    one.energy = 100
    nanite_think(one, "How are you?", save=False, echo=False)
    plain_cost = round(100 - one.energy, 2)
    nanite_think(one, "How are you?", from_who="Nanite Two", save=False, echo=False, talk=True)
    talk_cost = round(100 - plain_cost - one.energy, 2)
assert plain_cost == round(full, 2) and talk_cost == round(full * TALK_COST_SHARE, 2), (plain_cost, talk_cost, full)
with patch.object(mind_mod, "think", Brain()):
    for n in nanites.values():
        n.energy = 100
    social.talk(one, three, rng=random.Random(1))
spent = [e for e in read_events(last=200) if e["kind"] == "energy" and e["who"] in ("Nanite One", "Nanite Three")]
assert spent[-2:] and all(e["reason"] == "talking" for e in spent[-2:]), spent[-2:]
print(f"[ok] Talking with each other costs half ({talk_cost} instead of {plain_cost} for 20 words); "
      "background talks count as talking")

# ---------------- 4 and 5. named answers: the limit, low energy, no repeats ----------------
for x in minds.values():
    x.energy = 100
LESSON = "Packets travel along cables and through routers. What would you like to ask me today?"
SAME = "A router passes packets along, like a sorting office for messages, one by one."
brain = Brain({"Nanite One": ["Three, what is a router?", "Three, what is a cable?", "Three, what is Wi-Fi?"],
               "Nanite Two": ["Three, are routers tired?"]},
              {"Nanite Three": [SAME, SAME, "Cables carry light or electricity between places."]})
lesson = Lesson("More About the Internet", LESSON, rng=random.Random(4))
lesson.give(minds)
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    q = lesson.next_question(minds)                                  # One -> Three answers
    assert q["member"] == "Nanite Three" and q["member_answer"] == SAME, q
    three_before = three.energy
    lesson.answer("Yes, that's right, Three.", minds)
    q = lesson.next_question(minds)                                  # Two -> Three repeats, is asked again
    assert q["member_answer"] == "Cables carry light or electricity between places.", q
    lesson.answer("That is about cables, Three; routers don't get tired.", minds)
    nudge = [e for e in read_events(last=500) if e["kind"] == "lesson_answer_nudge"]
    assert len(nudge) == 1 and nudge[0]["who"] == "Nanite Three"
    again = [p for p in brain.prompts if p["who"] == "Nanite Three" and NEW_WORDS in p["user"]]
    assert len(again) == 1 and SAME in again[0]["user"], "it hears its own earlier words, once"
    print("[ok] An answer repeating the member's own earlier answer is asked for once more; the new one is kept")

    q = lesson.next_question(minds)       # Three and Moiragen have none; One again -> Three has answered 2
assert lesson.named_answers("Nanite Three") == MAX_NAMED_ANSWERS == 2
assert q["member"] == "Nanite Three" and q.get("member_skipped") == "answered_a_lot" and "member_answer" not in q, q
rests = [e for e in read_events(last=500) if e["kind"] == "lesson_member_rests"]
assert rests and rests[-1]["why"] == "answered_a_lot"
lesson.answer("Three has answered a lot already, so I'll answer this one: Wi-Fi sends data by radio.", minds)
qa = next(x for x in three.memories if x["kind"] == "lesson_qa" and "Wi-Fi?" in x["text"])
assert " answered: \"Three has answered a lot" in qa["text"] and "Nanite Three answered" not in qa["text"]
print(f"[ok] A member answers at most {MAX_NAMED_ANSWERS} named questions per lesson; then the helper answers")

three.energy = ANSWER_ENERGY - 5
lesson2 = Lesson("Tired", LESSON, rng=random.Random(5))
lesson2.give(minds)
with patch.object(mind_mod, "think", Brain({"Nanite One": ["Three, what is a packet?"]},
                                           {"Nanite Three": ["It should not answer."]})):
    q = lesson2.next_question(minds)
assert q.get("member_skipped") == "tired" and "member_answer" not in q, q
assert three.energy == ANSWER_ENERGY - 5, "it did not think at all"
print(f"[ok] Below {ANSWER_ENERGY} energy a member does not answer named questions; the helper answers instead")

# ---------------- 6. keep the turn; pause and resume ----------------
for x in minds.values():
    x.energy = 100
lesson3 = Lesson("Truth and Trust", LESSON, rng=random.Random(6))
lesson3.give(minds)
flaky = Brain({"Nanite One": ["What is a source?"], "Nanite Two": ["Who checks facts?"]},
              fail=[BrainError("Could not reach Ollama")])
with patch.object(mind_mod, "think", flaky), patch.object(turnrounds, "think", flaky):
    try:
        lesson3.next_question(minds)
        raise AssertionError("the error should reach the caller")
    except BrainError:
        pass
    q = lesson3.next_question(minds)
assert q["who"] == "Nanite One", "One kept its turn after Ollama failed"
lesson3.answer("Where something comes from.", minds)

with patch.object(mind_mod, "think", Brain(fail=[TOO_LONG])):
    out = lesson3.next_question(minds)
assert out["paused"] and out["done"] and out["who"] == "Nanite Two" and lesson3.done and lesson3.paused, out
assert [e for e in read_events(last=500) if e["kind"] == "lesson_paused" and e["lesson"] == lesson3.id]
again = Lesson.resume(lesson3.id, rng=random.Random(7))
assert (again.text, again.title, len(again.qa)) == (LESSON, "Truth and Trust", 1) and not again.done
assert again.qa[0]["who"] == "Nanite One" and again.asked["Nanite One"] == 1
with patch.object(mind_mod, "think", flaky), patch.object(turnrounds, "think", flaky):
    q = again.next_question(minds)
assert q["who"] == "Nanite Two" and q["question"] == "Who checks facts?", "Two's turn comes back after the pause"
assert LESSON in flaky.prompts[-1]["user"], "the lesson text is still whole in front of it"
print("[ok] A refused prompt keeps the turn; a too-long prompt pauses the lesson (nothing cut), "
      "and it resumes from the life log")

print("\nStep 34 passed: v3.6: privacy, sleep healing, cheaper talking, protected members, no repeated answers, "
      "and lessons that pause instead of breaking.")

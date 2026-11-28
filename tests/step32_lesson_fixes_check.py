"""Step 32 check (v3.4): three fixes after lessons 1 and 2.

  1. The export rule: a labelled story memory in a prompt (the whole-life mix) no longer
     keeps an example out. Only the mind's own line counts: pretend play itself, or a story
     event told as if it really happened. Made-up and corrected words still count anywhere.
  2. Clearer labels: in every prompt Claude Code's answers say "Claude Code (Rowan's helper,
     not a nanite)", for old memories too (shown so, never rewritten), and in new memories.
  3. Stock openings: a past lesson question is shown whole in the memory mix (clipped, only
     its first words were left, and they were copied as an opener). A question that copies
     words another member just asked is asked for again once, in its own words; whatever
     comes then is kept. No words are banned.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step32_lesson_fixes_check.py
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
from moiragen.lessons import OWN_WORDS, SAID_BY, Lesson, lesson_memories
from moiragen.memory_log import log_event, read_events
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.recall import recent_line, short

ASKING = "Now you may ask a question of your own"


class Brain:
    """Each mind asks its scripted questions after a lesson (then "no question")."""

    def __init__(self, questions):
        self.questions, self.prompts = {k: list(v) for k, v in questions.items()}, []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        system, user = system or "", messages[-1]["content"]
        self.prompts.append({"system": system, "user": user})
        me = "Moiragen" if system.startswith("You are Moiragen") else system.split(",")[0].replace("You are ", "")
        if ASKING in user:
            mine = self.questions.get(me) or []
            return {"text": mine.pop(0) if mine else "no question", "seconds": 0.01, "waited": 0}
        return {"text": "Quietly thinking.", "seconds": 0.01, "waited": 0}


nanites = load_all()
m = Moiragen.load()
one, two, three = nanites.values()
minds = {n.name: n for n in nanites.values()} | {"Moiragen": m}

# A pretend story in the life log, and a labelled memory of it in Three's life.
log_event("path_story", "mind", title="The Rainy Day with Lumi (pretend play, not my real life)", part="Act 1",
          start=True, text="Narrator: It is raining, and Lumi holds up a drawing of a fort.")
three.remember("chat", "[Pretend play, not my real life] Story time, \"The Rainy Day with Lumi\": I said: Lumi's fort "
                       "was warm and dry.")
# An old lesson memory, as lessons 1 and 2 saved it (it must never be rewritten).
OLD = ("Lesson from Rowan, Saturday 28 November 2026, after \"What the Internet Is\": I asked: \"It’s… intriguing. "
       "This “copy,” this waiting. If it truly isn't influencing my processes, then why bother creating it at all? "
       "Isn't it simpler to just remember?\" | Answered by Claude Code, Rowan's helper: \"You are right that "
       "remembering is what you do every day, Three, and the backup does not change how you remember.\"")
three.remember("lesson_qa", OLD, lesson="lold", asker="Nanite Three", question="It’s… intriguing. ...",
               answer="You are right...", answered_by="Claude Code, Rowan's helper")
three.save()
for x in minds.values():
    x.energy = 100

# ---------------- 2 and 3. Old memories: shown with the clear label, the question whole ----------------
old = next(x for x in three.memories if x["kind"] == "lesson_qa")
assert old["text"] == OLD, "old memories are never rewritten"
line = short(old, set())
assert f"{SAID_BY} answered:" in line and "Answered by Claude Code" not in line, line
assert "Isn't it simpler to just remember?" in line, "the whole question, not just its first words"
assert line.split(": ", 1)[1].startswith("Lesson from Rowan (after \"What the Internet Is\"): I asked:"), line
assert "Saturday 28 November 2026" not in line, "the long header that ate the room is shorter (the date leads the line)"
assert SAID_BY in recent_line(old)
sample = lesson_memories(three.memories, random.Random(1))
assert "why bother creating it at all? Isn't it simpler" in sample and "Answered by Claude Code" not in sample
correction = {"time": "2026-11-28T13:58:25", "kind": "correction",
              "text": "A gentle correction: Claude Code, Rowan's helper said \"Only Rowan can open it\"."}
assert f"{SAID_BY} said" in short(correction, set())
print("[ok] Old lesson memories stay as they were; they are shown with \"Claude Code (Rowan's helper, not a nanite)\" "
      "and the whole question")

# ---------------- 1, 2, 3. A lesson ----------------
LESSON = "Packets travel along cables and through routers. What would you like to ask me today?"
brain = Brain({"Nanite One": ["They’re saying it breaks apart into many small pieces. How does it put itself back "
                              "together again?"],
               # Two first copies One's question word for word, then asks its own
               "Nanite Two": ["They’re saying it breaks apart into many small pieces. How does it put itself back "
                              "together again? And the roads?", "Do routers ever get tired?"],
               "Nanite Three": ["It’s… intriguing. Where do the cables go under the sea?"]})
lesson = Lesson("More About the Internet", LESSON, rng=random.Random(2))
lesson.give(minds)
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    q1 = lesson.next_question(minds)
    lesson.answer("Each packet has a number, and the computer puts them in order.", minds)
    q2 = lesson.next_question(minds)
    lesson.answer("No, routers do not get tired; they are machines.", minds)
    q3 = lesson.next_question(minds)
assert q2["who"] == "Nanite Two" and q2["question"] == "Do routers ever get tired?", q2
again = [e for e in read_events(last=10**6) if e["kind"] == "lesson_echo"]
assert len(again) == 1 and again[0]["who"] == "Nanite Two", "asked once for its own words"
assert any(OWN_WORDS in p["user"] for p in brain.prompts)
assert q3["question"] == "It’s… intriguing. Where do the cables go under the sea?", "its own opening is never banned"
assert not [e for e in read_events(last=10**6) if e["kind"] == "lesson_echo" and e["who"] == "Nanite Three"]
print("[ok] A question copying another member's is asked for again once; its own words (any opening) are kept")

asks = [p for p in brain.prompts if ASKING in p["user"]]
heard = asks[-1]["user"]
assert f"Nanite One asked: \"They’re saying" in heard and f"{SAID_BY} answered: \"Each packet has a number" in heard
assert f"{SAID_BY} will answer it" in heard and "Claude Code, Rowan's helper answered" not in heard
qa = next(x for x in two.memories if x["kind"] == "lesson_qa" and x.get("lesson") == lesson.id)
assert f"| {SAID_BY} answered: \"Each packet" in qa["text"], qa["text"]
print("[ok] In the prompt and in new memories, Claude Code's answers say \"(Rowan's helper, not a nanite)\"")

# ---------------- 1. The export rule ----------------
three_asks = next(p for p in asks if p["system"].startswith("You are Nanite Three"))
assert "[Pretend play, not my real life]" in three_asks["system"], "the story memory is in its whole-life mix"
kept = [ex for ex in build_examples() if ex.get("lesson") == lesson.id and ex["task"] == "lesson_question"]
said = {ex["messages"][-1]["content"] for ex in kept}
assert "It’s… intriguing. Where do the cables go under the sea?" in said, "a story memory in its prompt is fine now"
assert "Do routers ever get tired?" in said
# Its own line telling the story as if it were real still stays out.
log_event("training_example", "Nanite One", system="These are your own real memories: ...",
          messages=[{"role": "user", "content": "How are you?"}], reply="I remember Lumi held up a drawing to me.",
          task="lesson_question", lesson=lesson.id)
log_event("training_example", "Nanite One", system="...", messages=[{"role": "user", "content": "Hm?"}],
          reply="[About pretend play, not my real life] The fort was fun.", task="lesson_question", lesson=lesson.id)
replies = {ex["messages"][-1]["content"] for ex in build_examples()}
assert "I remember Lumi held up a drawing to me." not in replies and "The fort was fun." not in str(replies)
print("[ok] The export keeps a line with a story memory in its prompt; a line that treats a story as real "
      "or is pretend play stays out")

print("\nStep 32 passed: v3.4: a fairer export rule, clear labels for Claude Code, and openings not copied from "
      "clipped memories.")

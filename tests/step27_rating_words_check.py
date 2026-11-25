"""Step 27 check (v2.9): two more judging words, and gentle corrections after a free talk.

"does lack something" and "that's accurate" are verdicts when Moiragen says them about a
nanite, but not about himself or a thing. And lines that got a gentle correction stay out
of the fine-tuning export, in the reply and inside later prompts.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step27_rating_words_check.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import storytime
from moiragen.early_life import make_room
from moiragen.export import build_examples
from moiragen.memory_log import LOG_FILE, read_events
from moiragen.mother import Moiragen
from moiragen.storytime import moiragen_says, verdict_in, without_verdicts

# ---------------- 1. The two phrases, about a nanite ----------------
# Both were really said, on 25 November.
LACKS = "And yes, I noticed how Nanite One phrased it - 'data flowing' does lack something."
ACCURATE = "Nanite Three, you noted the increase in the hum during quieter periods—that’s accurate."
for verdict in [LACKS, ACCURATE,
                "Nanite Two's description lacks something.", "I think One's words lacked something.",
                "You spoke of the hum. That's accurate.", "Nanite Two spoke of the hum. Yes, that is quite accurate.",
                "You noticed the hum, and that's accurate.", "Nanite One, that’s not accurate.",
                "I think that's accurate, Nanite Two.", "Nanite One said it plainly. It does lack something."]:
    assert verdict_in(verdict), verdict
print("[ok] Both real sentences are caught, and the same words said in other ways about a nanite")

for fine in ["I feel that I lack something.", "I was tired, and that's accurate.", "The picture on the wall lacks something.",
             "The rain was heavy. That's accurate for this month.", "Something is quiet in me.",
             "Nanite Two, would you say that's accurate?", "Nanite Three, what do you think it might lack?",
             "Nanite One, I liked how you spoke about the quiet.", "One day felt long, and two felt short."]:
    assert verdict_in(fine) is None, fine
print("[ok] About himself, about a thing, or as a question, they are no verdict")

assert verdict_in("You noted the hum, that's accurate.", reflection=True) is None
assert verdict_in("Nanite One's answer does lack something.", reflection=True)
print("[ok] When a nanite reflects, \"that's accurate\" is praise and stays; \"lacks something\" is noted")

# ---------------- 2. What he does about it ----------------
m = Moiragen.load()


class Says:
    """A stand-in brain that says the given lines in order."""
    def __init__(self, lines):
        self.lines, self.prompts = list(lines), []

    def __call__(self, messages, **more):
        self.prompts.append(messages[-1]["content"])
        return {"text": self.lines.pop(0), "seconds": 0.01}


KIND = "Nanite Three, I heard what you told us about the quiet."
speak = Says([ACCURATE, KIND])
with patch.object(storytime, "think", speak):
    assert moiragen_says(m, "Together", "Answer one of them.") == KIND
assert "that’s accurate" in speak.prompts[1], speak.prompts[1]
assert list(read_events(kind="story_verdict", last=1))[0]["outcome"] == "rewritten"
assert without_verdicts("I am glad we are talking. Nanite Three, you noted the hum. That's accurate.") \
    == "I am glad we are talking. Nanite Three, you noted the hum."
print("[ok] He sees a gentle note and rewrites it; if that fails, only the rating sentence is taken out")

# ---------------- 3. Corrected lines stay out of the export ----------------
ONE = ("Yesterday’s story simulations felt... significant. Specifically, the narrative where we optimized resource "
       "allocation based on projected needs.")
TWO = ("Yesterday’s optimization scenario stuck with me. I keep returning to the simulated stories. It’s odd, "
       "considering we haven’t lived anything at all yet.")


def event(second, kind, who, **details):
    time = f"2026-11-25T20:49:{second:02d}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time, "kind": kind, "who": who, **details}, ensure_ascii=False) + "\n")
    return time


def example(second, who, reply, system="You are a nanite.", question="How are you feeling?"):
    return event(second, "training_example", who, system=system, reply=reply,
                 messages=[{"role": "user", "content": question}])


at_one = example(1, "Nanite One", ONE)
at_two = example(5, "Nanite Two", TWO)
example(9, "Nanite Three", "There is a hum beneath everything, deep and slow.", question=f"Nanite Two says: {TWO}")
example(13, "Nanite One", "Morning light would be a nice thing to imagine.", system=f"Your recent memories: {ONE}")
example(17, "Nanite Two", "A quiet evening, like still water.")
assert len(build_examples()) == 5
event(21, "correction", "Nanite One", corrects=at_one,
      text="A gentle correction: I spoke of a story where we \"optimized resource allocation\". No such story happened.")
event(25, "correction", "Nanite Two", corrects=at_two,
      text="A gentle correction: I spoke of an \"optimization scenario\" and said \"we haven't lived anything at all "
           "yet\". No such story happened, and we have lived.")
left = [ex["messages"][-1]["content"] for ex in build_examples()]
assert left == ["A quiet evening, like still water."], left
print("[ok] Both corrected lines are out of the export, as replies and inside later prompts; the rest stays")

# ---------------- 4. A note right next to the line also keeps it from being quoted later ----------------
chat = {"time": "2026-11-25T20:49:05", "kind": "chat",
        "text": "Nanite One said: Hello. | I replied: We haven’t lived anything at all yet."}
note = {"time": "2026-11-25T21:10:00", "kind": "correction", "text": "A gentle correction."}
first = [{"time": f"2026-11-25T20:00:{i:02d}", "kind": "noticed", "text": f"Something {i}."} for i in range(20)]
after = [{"time": f"2026-11-25T22:{i:02d}:00", "kind": "noticed", "text": f"Later {i}."} for i in range(55)]
memories, notes = make_room(first + [chat, note] + after, 60)
assert notes and "lived anything" not in notes[0]["text"] and note in memories, notes
memories, notes = make_room(first + [chat] + after, 60)
assert "lived anything" in notes[0]["text"], "without the note it would be quoted"
print("[ok] With the note right after it, the line is never quoted in an early-life note")

print("\nStep 27 passed: no rating words about a nanite, and corrected lines never become fine-tuning data.")

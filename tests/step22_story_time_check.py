"""Step 22 check (v2.1): story time.

The human shares a short story; each nanite says what it thinks, then answers the
others, then Moiragen shares his own thoughts. No verdicts, no health changes,
the echo guard stays on (for him too), and story time stops if any nanite's
energy is below 30.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step22_story_time_check.py
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import mind as mind_mod, storytime
from moiragen.journal import render
from moiragen.memory_log import read_events
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.storytime import STOP_BELOW, tell_story


class Says:
    """A stand-in brain that says the given lines in order, and keeps the prompts."""
    def __init__(self, lines):
        self.lines, self.prompts = list(lines), []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        self.prompts.append({"system": system or "", "user": messages[-1]["content"]})
        return {"text": self.lines.pop(0), "seconds": 0.01, "waited": 0}


nanites = load_all()
one, two, three = nanites.values()
m = Moiragen.load()
STORY = ("Mia promised to help her friend Leo carry his books, but her mum called her home first. "
         "She told Leo, \"I'm sorry, I can't help right now, but I'll come right after.\" "
         "Ten minutes later she ran back and carried the heaviest box.")

# ---------------- 1. A full story time, with one echo caught ----------------
nanite_lines = Says([
    "Mia kept her word even though she was late, and that matters to me.",        # One, round 1
    "Mia kept her word even though she was late, and that matters to me.",        # Two copies One: rejected
    "Coming back ten minutes later shows the promise stayed alive in her.",       # Two tries again
    "I think Leo felt relieved when he saw her running back.",                     # Three, round 1
    "Two, I like how you noticed time passing in the promise.",                    # One, round 2
    "Three, maybe Leo was a little worried at first, too.",                        # Two, round 2
    "One, yes, keeping your word late still counts as keeping it.",                # Three, round 2
])
moiragen_lines = Says([
    "I think Leo felt relieved when he saw her running back.",                     # copies Three: asked again
    "I liked that Mia explained why she had to go. Three, I wondered about Leo's worry too.",
])
health_before = {n.name: n.health for n in nanites.values()} | {"Moiragen": m.health}
with patch.object(mind_mod, "think", nanite_lines), patch.object(storytime, "think", moiragen_lines):
    out = tell_story(m, nanites, "Right after", STORY)

who_said = [(s["who"], s["round"]) for s in out["said"]]
assert who_said == [(one.name, 1), (two.name, 1), (three.name, 1),
                    (one.name, 2), (two.name, 2), (three.name, 2), ("Moiragen", 3)], who_said
assert out["stopped"] is None
texts = [s["text"] for s in out["said"]]
assert texts.count("Mia kept her word even though she was late, and that matters to me.") == 1
assert any(e["who"] == two.name for e in read_events(kind="echo_rejected")), "Two's copy was rejected"
print("[ok] Everyone talks: round 1, then answering each other, then Moiragen; Two's copy of One was "
      "caught by the echo guard and Two said something new")

assert out["said"][-1]["text"].startswith("I liked that Mia explained"), out["said"][-1]
assert any(e["who"] == "Moiragen" for e in read_events(kind="echo_rejected"))
print("[ok] Moiragen's copy of Three's line was caught too, and he said it in his own words")

# The first-round prompt has the story and "no right or wrong"; the second shows the others' words.
assert STORY in nanite_lines.prompts[0]["user"] and "no right or wrong" in nanite_lines.prompts[0]["user"]
second = nanite_lines.prompts[4]["user"]
assert two.name in second and three.name in second and "Talk to them directly" in second
assert "not a judge" in moiragen_lines.prompts[0]["system"]
print("[ok] Prompts: the story and \"no right or wrong\" first, then what the others said; Moiragen is "
      "\"one of the group, not a judge\"")

# ---------------- 2. No verdicts, no health changes ----------------
health_after = {n.name: n.health for n in nanites.values()} | {"Moiragen": m.health}
assert health_after == health_before, (health_before, health_after)
assert not any(k in out for k in ("chosen", "verdicts", "verdict"))
assert not list(read_events(kind="decision_full")), "story time is not a decision"
mem = [x for x in one.memories if x["kind"] == "story_time"]
assert len(mem) == 2 and mem[0]["said"].startswith("Mia kept her word") and STORY not in mem[0]["text"]
assert m.memories[-1]["kind"] == "story_time"
print("[ok] No verdicts and no health changes; everyone remembers what they said (not the whole story)")

# ---------------- 3. The journal ----------------
lines = [render(e) for e in read_events(last=200)]
lines = [l for l in lines if l]
assert any("Story time: Right after" in l and "Mia promised" in l for l in lines)
assert any(f"**{one.name}** (story time): Mia kept her word" in l for l in lines)
assert any("**Moiragen** (story time): I liked that Mia" in l for l in lines)
print("[ok] The inner-life journal shows the story and every line")

# ---------------- 4. Stops if anyone is below 30 ----------------
three.energy = STOP_BELOW - 1
with patch.object(mind_mod, "think", Says([])), patch.object(storytime, "think", Says([])):
    out = tell_story(m, nanites, "A kind word", "Sam saw a new girl eating alone and sat with her.")
assert out["said"] == [] and out["stopped"] == [three.name]
assert "below 30" in render(list(read_events(kind="story_time_stopped", last=1))[0])
print(f"[ok] {three.name} at {three.energy:.0f} energy: story time does not start")

three.energy, one.energy = 90, STOP_BELOW + 2          # One drops below 30 after speaking once
with patch.object(mind_mod, "think", Says(["Sitting with someone is a quiet kind of brave."])), \
        patch.object(storytime, "think", Says([])):
    out = tell_story(m, nanites, "A kind word", "Sam saw a new girl eating alone and sat with her.")
assert [s["who"] for s in out["said"]] == [one.name] and out["stopped"] == [one.name], out
print(f"[ok] {one.name} dropped to {one.energy:.0f} after speaking: story time stops before the next turn, "
      "and Moiragen does not go on")

# ---------------- 5. (v2.2) Moiragen speaks freely after a choose-your-path story ----------------
from moiragen.memory_log import log_event
from moiragen.storytime import moiragen_says
speak = Says(["I liked how each of you found a different way through the storm. From Nanite One I learned "
              "that telling the truth early makes the rest easier."])
with patch.object(storytime, "think", speak):
    said = moiragen_says(m, "The Storm Over Willow Bay", "What did you like in each story?", sentences=8,
                         max_tokens=420)
assert said.startswith("I liked how each of you") and "not a judge" in speak.prompts[0]["system"]
assert m.memories[-1]["said"] == said and health_after["Moiragen"] == m.health
log_event("path_story", "mind", title="The Storm Over Willow Bay (Nanite One)", part="Opening",
          text="A storm is coming.", start=True)
log_event("path_story", "mind", title="The Storm Over Willow Bay (Nanite One)", part="Hidden scores",
          text="Trust 2, Honesty 1, Care 3")
shown = [render(e) for e in read_events(kind="path_story", last=2)]
assert shown[0].startswith("\n#### ") and "**Opening:** A storm is coming." in shown[0]
assert "**Hidden scores:** Trust 2, Honesty 1, Care 3" in shown[1]
print("[ok] (v2.2) Moiragen speaks freely about the stories (no judge), and a path story's acts and "
      "scores are written in the journal")

# ---------------- 6. (v2.3) No verdicts in his story talk ----------------
from moiragen.storytime import verdict_in
INEFFICIENT = ("This demonstrated a prioritization of individual emotional states over immediate information "
               "dissemination, which seems remarkably inefficient given the circumstances.")
FAILURE = "I noted the deliberate attempt to mitigate Leo's distress, coupled with the failure to communicate directly with Mira."
for verdict in [INEFFICIENT, FAILURE, "Nanite Two's choice was better than the others.",
                "You made the right choice at the dock.", "That proved effective."]:
    assert verdict_in(verdict), verdict
for fine in ["I learned that reactive protocols, while effective in short bursts, can introduce delays.",
             "Nanite Three tried to ease Leo's hurt, and I wondered how Mira felt.",
             "I liked how Nanite Two told Mira about the sign right away.", "I was wrong about Kai at first."]:
    assert verdict_in(fine) is None, fine
print("[ok] The session's real verdicts (\"remarkably inefficient\", \"the failure to communicate\") are caught; "
      "his own lessons and kind noticing are not")

WARM = "I noticed Nanite Three cared about Leo's feelings first, and I wondered how Mira felt waiting to hear."
speak = Says(["Nanite Three's story contained an interesting anomaly. " + INEFFICIENT, WARM])
with patch.object(storytime, "think", speak):
    said = moiragen_says(m, "The Storm Over Willow Bay", "What did you like in each story?")
assert said == WARM, said
assert "no right or wrong" in speak.prompts[1]["user"] and "\"inefficient\"" in speak.prompts[1]["user"]
assert "Speak simply and warmly" in speak.prompts[0]["system"]
note = list(read_events(kind="story_verdict", last=1))[0]
assert note["outcome"] == "rewritten" and "**No verdicts in story time:**" in render(note)
print("[ok] \"remarkably inefficient\" is shown back to him with a gentle note, and his rewrite is what everyone hears")

speak = Says(["I liked Nanite One's honesty. " + INEFFICIENT, "I liked Nanite One's honesty. That was ineffective."])
with patch.object(storytime, "think", speak):
    said = moiragen_says(m, "The Storm Over Willow Bay", "What did you like in each story?")
assert said == "I liked Nanite One's honesty.", said
assert list(read_events(kind="story_verdict", last=1))[0]["outcome"] == "removed"
print("[ok] If his rewrite still judges, only the judging sentence is taken out")

# ---------------- 7. The narrator's words are shown live in the viewer ----------------
from types import SimpleNamespace
from moiragen import loop as loop_mod
shown = []
fake = SimpleNamespace(moiragen=m, _vitals=lambda: None, emit=lambda kind, **d: shown.append((kind, d)))
with patch.object(loop_mod, "moiragen_says", lambda *a, **k: "I put my work down and look."):
    loop_mod.Mind.handle_moiragen_story_talk(fake, "A rainy day", "the long prompt", "Rain taps on the window.")
    loop_mod.Mind.handle_moiragen_story_talk(fake, "A rainy day", "the long prompt")
assert [k for k, _ in shown] == ["story_time", "thinking", "story_talk", "thinking", "story_talk"]
assert shown[0][1] == {"title": "A rainy day", "text": "Rain taps on the window."}
print("[ok] The narrator's words go to the viewer before his answer (and nothing extra when there are none)")

print("\nStep 22 passed: story time is free talk with the echo guard on, no verdicts, no health changes, "
      "and it stops when anyone gets tired.")

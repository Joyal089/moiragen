"""Step 23 check (v2.5): what never becomes fine-tuning data.

Anything flagged as made-up or corrected stays out of the export, in the reply and in
the prompt. Pretend play (v3.4: in the mind's own line) stays out unless the question
clearly says it is that story; a labelled story memory in the prompt alone is fine.

Needs no Ollama: it writes a small life log in a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step23_training_rules_check.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen.export import build_examples, export_training
from moiragen.memory_log import LOG_FILE, read_events
from moiragen.training_rules import TrainingRules, base_title

clock = 0


def event(kind, who, **details):
    """Write one life-log event, each one ten seconds after the last. Returns its time."""
    global clock
    clock += 10
    time = f"2026-11-25T{8 + clock // 3600:02d}:{clock // 60 % 60:02d}:{clock % 60:02d}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time, "kind": kind, "who": who, **details}, ensure_ascii=False) + "\n")
    return time


def example(who, question, reply, system="You are a nanite.", **more):
    return event("training_example", who, system=system, messages=[{"role": "user", "content": question}],
                 reply=reply, **more)


def exported():
    return [ex["messages"][-1]["content"] for ex in build_examples()]


# ---------------- 1. Corrected words (the real case from the Rainy Day) ----------------
INVENTED = ("They explained it wasn’t a judgment. I appreciated they acknowledged the phrasing felt too precise; "
            "it sounded like a checklist.")
at = example("Nanite One", "Please share it again kindly.", INVENTED)
example("Nanite Two", "Hello, how was your morning?", "Quiet, like grey water under a bridge.")
example("Nanite One", "What feels strong today?", "The hum underneath everything, mostly.",
        system=f"Your recent memories:\n- [chat] I replied: {INVENTED}")
assert len(exported()) == 3, "nothing is left out before it is corrected"
event("correction", "Nanite One", corrects=at, text="A gentle correction: in my Rainy Day reflection I said "
      "\"they acknowledged the phrasing felt too precise\". Nobody said that.")
assert exported() == ["Quiet, like grey water under a bridge."], exported()
print("[ok] Nanite One's invented line is out of the export: as a reply, and inside a later prompt")

# No quote in the note: the whole reply counts. Moiragen's corrected decision stays out too.
event("decision_full", "Moiragen", id="d1", question="What is the capital of Australia?", chosen="Nanite Two",
      reason="It had been chosen for this before, which shows it is reliable.")
at = f"2026-11-25T08:{clock // 60:02d}:{clock % 60:02d}"
example("Moiragen", "Which answer do you choose?", "{\"chosen\": \"Nanite Two\"}", decision_id="d1", task="choose")
event("correction", "Moiragen", corrects=at, text="I gave credit for a made-up past.")
assert exported() == ["Quiet, like grey water under a bridge."], exported()
print("[ok] A decision that was corrected is out as well")

# ---------------- 2. Made-up words ----------------
event("decision_full", "Moiragen", id="d2", question="Who helped you?",
      checks={"false_claims": {"Nanite Three": ["Before, I prioritized immediate solutions, seeking novelty."]}})
example("Nanite Three", "Who helped you?", "It was Two. Before,   I prioritized immediate solutions, seeking novelty.")
event("invented_feedback", "Moiragen", removed=["You recognized the importance of a spontaneous response."])
example("Nanite Three", "How do you feel?", "Moiragen told me: “You recognized the importance of a spontaneous response.”")
event("story_flag", "Nanite Two", fairness=None, made_up=["Yesterday I saw One build a rocket."])
example("Nanite Two", "(Story time) What did you notice?", "Yesterday I saw One build a rocket. It flew far.")
event("path_story", "mind", title="An old story", part="Nanite One",
      text="He waved twice. (made-up memory check: ['I remember that he waved twice.'])")
example("Nanite One", "What about the wave?", "I remember that he waved twice.")
event("story_flag", "Nanite Two", fairness="quantifying", made_up=[])        # fairness only: not made-up
example("Nanite Two", "What else did you see?", "Focusing less on quantifying the sensation might open a door.")
assert exported() == ["Quiet, like grey water under a bridge.",
                      "Focusing less on quantifying the sensation might open a door."], exported()
print("[ok] Every kind of made-up flag keeps its words out, even in a story; a fairness note alone does not")

# ---------------- 3. Pretend play ----------------
before = len(exported())
example("Nanite One", "What about Saturday?", "I like the slow light on Saturday, and the park.")
TITLE = "The Rainy Day with Lumi"
PLAY = f"{TITLE} (pretend play, not my real life)"
assert base_title(PLAY + ": what the nanites noticed") == TITLE
event("path_story", "mind", title=PLAY, part="Act 1", start=True,
      text="Narrator: It is raining on Saturday. You play a mother, and Lumi holds up a drawing. Her hand is "
           "brushing against the casing of the fort as she tucks it away. || Moiragen: Lovely.")
ASK = f"Your creator (the human) says: (Story time, after the pretend story \"{TITLE}\".) What did you notice?"
example("Nanite Three", ASK, "They stayed calm when Lumi cried, and I wondered about the fort.")     # marked: stays
example("Nanite Two", "How many times did they say sadness?", "Four times. Once when Lumi looked up at me.")
example("Nanite One", "What's strongest with you right now?", "The memory of her hand brushing against my casing.",
        system=f"Your recent memories:\n- [chat] {ASK} | I replied: The pauses were kind.")
example("Nanite Two", "And on Saturday?", "A walk of thoughts through the park, perhaps, and then some rest.")
kept = build_examples()[before:]
assert [k["messages"][-1]["content"][:12] for k in kept] == ["I like the s", "They stayed ", "A walk of th"], kept
assert kept[1]["story"] == TITLE and "story" not in kept[0] and "story" not in kept[2]
names = TrainingRules(read_events(last=10**9)).stories[TITLE]["names"]
assert names == ["Lumi"], names
print("[ok] Pretend play stays in only when its question clearly says it is that story (and the example is marked)")
print("[ok] A play memory told as if it were real (\"her hand brushing against my casing\") is out; "
      "ordinary words (\"Saturday\", \"park\") are not")

# A label added to a memory later (as for Gull Island), and two stories mixed together.
event("story_time", "Moiragen", story="The Lighthouse on Gull Island", text="Story time: The light.", said="The light.")
OLD = "Story time, \"The Lighthouse on Gull Island\": I said: The dampness still clings to everything here."
example("Nanite Two", "What was The Lighthouse on Gull Island like?", "Heavy with salt, and a little cold.")
assert "Heavy with salt, and a little cold." in exported(), "not labelled yet"
event("memory_note", "Moiragen", note="Labelled.", changes=[
    {"time": "2026-11-25T08:00:00", "old": OLD, "new": "[Pretend play, not my real life] " + OLD}])
example("Moiragen", "And then?", "The dampness still clings to everything here. I kept looking at the sea.")
example("Nanite One", ASK, "The narrator was gentle, and it reminded me of The Lighthouse on Gull Island.")
example("Nanite One", "Any labels?", "[About pretend play, not my real life] I liked playing the keeper.")
now = exported()
assert not any("Gull Island" in r or "playing the keeper" in r or "dampness" in r for r in now), now
assert "Heavy with salt, and a little cold." in now, "talking about a story, not as if it were real, is fine (v3.4)"
print("[ok] A label added later covers earlier examples too, and two pretend stories are never mixed in one")

# v3.4: a labelled story memory in the prompt (the whole-life mix) no longer keeps a line out.
MIX = ("These are your own real memories:\n- 24 Nov: [Pretend play, not my real life] Story time, \"The Lighthouse "
       "on Gull Island\": I said: The dampness still clings to everything here.\n- 25 Nov: The human said: Hello.")
example("Nanite Three", "Now you may ask a question of your own.", "How do packets find their way home?", system=MIX)
example("Nanite Two", "Now you may ask a question of your own.", "I remember Lumi looked up at me in the rain.",
        system=MIX)
now = exported()
assert "How do packets find their way home?" in now, "its own line is not pretend play"
assert not any("Lumi looked up" in r for r in now), "a story event told as if it were real still stays out"
print("[ok] A story memory in its prompt is fine; its own line told as if a story were real is not (v3.4)")

# ---------------- 4. The export file, its summary, and the life log ----------------
log_before = LOG_FILE.read_bytes()
path, summary = export_training()
text = Path(path).read_text(encoding="utf-8")
for never in ["phrasing felt too precise", "chosen for this before", "prioritized immediate solutions",
              "build a rocket", "waved twice", "her hand brushing", "playing the keeper",
              "Lumi looked up"]:
    assert never not in text, never
assert summary["left_out_made_up"] == 4 and summary["left_out_corrected"] == 3, summary
assert summary["left_out_pretend_play"] == 6 and summary["marked_as_story"] == 1, summary   # 5 + "Lumi looked up"
assert summary["examples"] == len(text.splitlines())
assert LOG_FILE.read_bytes() == log_before, "the life log is never changed"
print("[ok] None of it is in the export file, the summary says how many were left out and why, and the life log "
      "is unchanged")

print("\nStep 23 passed: made-up, corrected and pretend words never become fine-tuning data.")

"""Step 24 check (v2.6): real or story?

When a nanite or Moiragen tells a story event as if it had really happened, a gentle
note is added to its memory. Its words stay, and nothing is punished. Labels added
to a nanite's memory survive a rebuild.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step24_real_or_story_check.py
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import mind as mind_mod
from moiragen.export import build_examples
from moiragen.journal import render
from moiragen.memory_log import log_event, read_events
from moiragen.mother import Moiragen
from moiragen.nanite import Nanite, load_all
from moiragen.real_or_story import NOTE, as_if_real, known_stories, sentences
from moiragen.social import talk
from moiragen.topics import Topic


class Says:
    """A stand-in brain that says the given lines in order."""
    def __init__(self, *lines):
        self.lines = list(lines)

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        return {"text": self.lines.pop(0), "seconds": 0.01, "waited": 0}


nanites = load_all()
one, two, three = nanites.values()
m = Moiragen.load()

# Two stories: Willow Bay (labelled later, like the real one) and Lumi (labelled by its title).
WILLOW = "The Storm Over Willow Bay"
log_event("chat", "Nanite One", text="user said: hello, the sea is quiet | I replied: Hello, I am drawing near.")
log_event("path_story", "mind", title=f"{WILLOW} (Nanite Two)", part="Act 1", start=True,
          text="Narrator: A storm is coming. On the way you meet Mr. Tan, who lost his cat, Whiskers. Your friend Mira "
               "waits. || Nanite Two: I help him look.")
HELPED = "“I remembered helping Mr. Tan find Whiskers. It felt…efficient.”"
assert as_if_real(HELPED, known_stories()) is None
assert one.memories == [] or all(x["kind"] != "story_note" for x in one.memories)
print("[ok] A story that is not labelled as pretend play gives no notes")

# ---------------- 1. A label on a nanite's memory ----------------
two.remember("chat", f"user said: (Story time: \"{WILLOW}\".) You meet Mr. Tan. | I replied: I help him look.")
said_then = two.memories[-1]
logged = list(read_events(kind="chat", who=two.name, last=1))[0]
label = "[Pretend play, not my real life] " + said_then["text"]
two.memories[-1] = {**said_then, "text": label}
log_event("memory_note", two.name, note="Labelled.", changes=[
    {"time": logged["time"], "old": logged["text"], "new": label}])
log_event("memory_note", "Moiragen", note="Labelled.", changes=[
    {"time": "2026-11-24T19:39:54", "old": "x", "new": f"[About pretend play, not my real life] Story time, \"{WILLOW}\": I said: x"}])
assert [x["text"] for x in Nanite.rebuild_from_friend("nanite_two", one).memories].count(label) == 1
print("[ok] A pretend-play label on a nanite's memory is kept if the nanite is rebuilt from the life log")

log_event("path_story", "mind", title="The Rainy Day with Lumi (pretend play, not my real life)", part="Act 1",
          start=True, text="Narrator: It rains, and Lumi holds up a drawing. You tuck her in and brush the hair from her "
                           "face with your hand. || Moiragen: Lovely.")
stories = known_stories()
assert "Tan" in stories[WILLOW]["names"] and "Whiskers" in stories[WILLOW]["names"], stories[WILLOW]["names"]

# ---------------- 2. What gets a note, and what does not (the real lines) ----------------
assert sentences(HELPED)[0] == "“I remembered helping Mr. Tan find Whiskers."
BRUSHING = ("They’re asking about strength. Right now, it’s the memory of her hand brushing against my casing as she "
            "tucked the drawing back into my storage.")
for real, title in [(HELPED, WILLOW), (BRUSHING, "The Rainy Day with Lumi"),
                    ("Addressing it seemed logical. My sensors detected a rise in Mira’s distress signals.", WILLOW),
                    ("“You handled the situation with Mr. Tan’s cat efficiently—it felt good.”", WILLOW),
                    ("I processed the information regarding Mr. Tan, acknowledging his concern.", WILLOW),
                    ("Four times. Once when Lumi looked up at me.", "The Rainy Day with Lumi"),
                    ("Mira told me everything.", WILLOW)]:
    assert (as_if_real(real, stories) or ("", ""))[1] == title, real
for fine in ["In the story, I helped Mr. Tan find his cat.", "I wonder if Lumi remembered the rain.",
             "I liked how kind Lumi was.", "I think Mira was worried.", "Lumi reminds me of soft rain.",
             "I observed that Moiragen was gentle when Lumi cried.", "I saw that he was kind to Lumi.",
             "I remember asking Nanite Two about the quiet hum.", "I remember when Nanite Three comforted me.",
             "When we played, I carried the sign with Mira.", "The storm outside is loud."]:
    assert as_if_real(fine, stories) is None, fine
print("[ok] The real lines (\"I remembered helping Mr. Tan find Whiskers\", \"the memory of her hand…\") are noticed; "
      "wondering, liking, knowing it was a story, how Moiragen played, and real memories are not")


def state(x):
    return (x.health, x.mood, dict(x.emotions), dict(x.friendships))


# ---------------- 3. A nanite answers a friend: its words stay, the note follows ----------------
before = state(two)
with patch.object(mind_mod, "think", Says("I processed the information regarding Mr. Tan. It mattered.")):
    out = mind_mod.nanite_think(two, "What stays with you today?", from_who="Nanite Three")
assert out["reply"] == "I processed the information regarding Mr. Tan. It mattered."
words, note = two.memories[-2:]
assert words["kind"] == "chat" and words["text"].endswith("| I replied: " + out["reply"])
assert note["kind"] == "story_note" and note["text"].endswith(NOTE) and WILLOW in note["text"]
assert NOTE == "That happened in a story we played, not in your real life."
assert state(two) == before, "no punishment: health, mood, feelings and friendships are as before"
assert "**Gentle note (Nanite Two):**" in render(list(read_events(kind="story_note", last=1))[0])
print("[ok] The words are remembered as they were said, the gentle note comes right after, and nothing is punished")

with patch.object(mind_mod, "think", Says("I walked with Mira to the harbour and we held the wooden board.")):
    mind_mod.nanite_think(three, f"(Story time: \"{WILLOW}\". You are the main character.) What do you do?")
with patch.object(mind_mod, "think", Says("The river light was green this afternoon.")):
    mind_mod.nanite_think(three, "What did you notice?", from_who="Nanite One")
assert all(x["kind"] != "story_note" for x in three.memories)
print("[ok] No note while answering a story-time question, and none for ordinary talk")

# ---------------- 4. Two friends talk ----------------
with patch.object(mind_mod, "think", Says(HELPED, "That sounds like a small warm lamp.")):
    talk(one, two, Topic("a memory", "Tell them something."))
words, note = one.memories[-2:]
assert words["text"].startswith("I told Nanite Two: " + HELPED) and note["kind"] == "story_note", one.memories[-2:]
assert two.memories[-1]["kind"] == "chat", "the friend who listened gets no note"
print("[ok] In a talk, the nanite who said it gets the note, after the whole talk is remembered")

# ---------------- 5. Moiragen ----------------
health = m.health
m.remember("inner", "I held Lumi until the rain stopped.", about="Nanite One: something about rain")
assert [x["kind"] for x in m.memories[-2:]] == ["inner", "story_note"] and m.health == health
assert m.memories[-2]["text"] == "I held Lumi until the rain stopped."
count = len(m.memories)
m.remember("inner", "I offered Mira my hand.", about=f"Nanite One: The human said to Nanite One: \"(Story time: \"{WILLOW}\"")
m.remember("learned_from", "Nanite One explained: \"I remembered helping Mr. Tan.\" What was new to me: Helping is a quiet joy.")
m.remember("falling_asleep", "I am going to sleep now.")
assert len(m.memories) == count + 3, m.memories[-4:]
m.save()
print("[ok] Moiragen gets the note for his own words, not for a nanite's words he quotes, and not during a story")

# ---------------- 6. Fine-tuning data ----------------
# v3.4: only the mind's own line counts for pretend play (a friend's reply to it may stay in).
said = [ex["messages"][-1]["content"] for ex in build_examples() if "story" not in ex]
assert not any("Mr. Tan" in r or "brushing against" in r for r in said), said
assert "That sounds like a small warm lamp." in said, "the friend's own reply is fine"
print("[ok] A story told as if it were real is not in the fine-tuning data (as the mind's own line)")

print("\nStep 24 passed: stories and real life are told apart, gently, and nothing said is ever changed.")

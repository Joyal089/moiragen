"""Step 25 check (v2.7): old memories last.

Notes and labels never push a memory out. When the limit is reached, the oldest
memories become short early-life notes; the very first ones stay whole, and
nothing in a note is invented. The same for the nanites and for Moiragen.

Needs no Ollama: it uses a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step25_early_life_check.py
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import mother as mother_mod
from moiragen.blueprint import get_blueprint
from moiragen.early_life import FIRST_MEMORIES, NOTES, SUMMARISE, make_room
from moiragen.journal import render
from moiragen.memory_log import LOG_FILE, log_event, read_events
from moiragen.mother import MEMORY_KEEP, MOIRAGEN_FILE, Moiragen
from moiragen.nanite import Nanite, load_all
from moiragen.topics import TALKABLE

PLAY = "[About pretend play, not my real life] "


def chat(i, label=""):
    return {"time": f"2026-11-21T{i // 3600:02d}:{i // 60 % 60:02d}:{i % 60:02d}", "kind": "chat",
            "text": f"{label}Moiragen said: Question {i}? | I replied: I noticed the quiet number {i} today. It stayed."}


def note(i, kind="story_note"):
    return {"time": chat(i)["time"], "kind": kind, "text": f"A gentle note {i}."}


# ---------------- 1. The limit, and what counts toward it ----------------
assert get_blueprint()["memory_keep"] == 1000 and MEMORY_KEEP == 1000
memories = [chat(i) for i in range(200)]
assert make_room(memories, 200) == (memories, [])
with_notes = memories[:100] + [note(i) for i in range(60)] + memories[100:] + [note(i, "correction") for i in range(40)]
assert make_room(with_notes, 200) == (with_notes, []), "100 notes push nothing out"
labelled = [{**m, "text": PLAY + m["text"]} for m in memories]
assert make_room(labelled, 200) == (labelled, []), "labels push nothing out"
print("[ok] The limit is 1000, and notes, corrections and labels never push a memory out")

# ---------------- 2. Over the limit: summarised, not dropped ----------------
memories = ([chat(i) for i in range(30)] + [chat(30, PLAY), chat(31, PLAY), chat(32), note(32), chat(33), note(33, "correction")]
            + [chat(i) for i in range(34, 101)])
before = json.dumps(memories)
kept, new = make_room(memories, 100)
assert json.dumps(memories) == before and len(new) == 1, "the list it was given is not changed"
counted = [m for m in memories if m["kind"] not in NOTES]
assert kept[:FIRST_MEMORIES] == counted[:FIRST_MEMORIES], "the very first memories stay whole"
gone = [m for m in memories if m not in kept]
assert gone == counted[FIRST_MEMORIES:FIRST_MEMORIES + SUMMARISE]
early = kept[FIRST_MEMORIES]
assert early is new[0] and early["kind"] == "early_life" and early["count"] == SUMMARISE
assert (early["since"], early["time"]) == (gone[0]["time"], gone[-1]["time"])
assert [m for m in kept if m["kind"] in ("story_note", "correction")] == [note(32), note(33, "correction")]
print("[ok] Over the limit, the oldest 50 after the first 20 become one early-life note, in their place; "
      "notes and corrections stay")

text = early["text"]
assert text.startswith("Early life, 2026-11-21 00:00 to 2026-11-21 00:01, in short: 50 talks."), text
assert "I talked with Moiragen (50)." in text and "2 of these were about pretend play, not my real life." in text, text
quotes = re.findall('"([^"]+)"', text)
assert 1 <= len(quotes) <= 3 and all(any("I replied: " + q in m["text"] for m in gone) for q in quotes), quotes
for i in range(SUMMARISE):                # whichever lines it picks, never one of these four
    tried = make_room(memories[:FIRST_MEMORIES] + memories[FIRST_MEMORIES + i % 10:], 80)[1][0]["text"]
    assert not any(f"number {never} " in tried for never in (30, 31, 32, 33)), tried
assert len(text) < 600
print("[ok] The note only counts and quotes: every quote is word for word, none is pretend play or a corrected line")

# Words inside quote marks may be someone else's, so they are not quoted.
someone = [chat(i) for i in range(20)] + [{"time": chat(i)["time"], "kind": "chat", "text":
           "Nanite Two said: Hi. | I replied: He told me “the sea is green” this morning. Yes."} for i in range(20, 72)]
assert "the sea is green" not in make_room(someone, 71)[1][0]["text"]

# Again and again: first memories and earlier notes stay, and every memory is accounted for.
memories, made = [], []
for i in range(600):
    memories, new = make_room(memories + [chat(i)], 100)
    made += new
assert memories[:FIRST_MEMORIES] == [chat(i) for i in range(FIRST_MEMORIES)]
notes = [m for m in memories if m["kind"] == "early_life"]
whole = [m for m in memories if m["kind"] == "chat"]
assert notes == made and len(whole) <= 100
assert sum(m["count"] for m in notes) + len(whole) == 600
assert [m["time"] for m in memories] == sorted(m["time"] for m in memories), "still in order"
print("[ok] After 600 memories with a limit of 100, every memory is either whole or counted in an early-life note")

# ---------------- 3. A nanite ----------------
nanites = load_all()
one, two, three = nanites.values()
assert not one.memories, one.memories
one.blueprint["memory_keep"] = 100
for i in range(101):
    one.remember("chat", chat(i)["text"])
for i in range(30):
    one.remember("story_note", f"A gentle note {i}.")
first = one.memories[:FIRST_MEMORIES]
assert [m["text"] for m in first] == [chat(i)["text"] for i in range(FIRST_MEMORIES)]
logged = list(read_events(kind="early_life", who=one.name, last=10))
assert len(logged) == 1 and logged[0]["text"] == one.memories[FIRST_MEMORIES]["text"] and logged[0]["count"] == SUMMARISE
assert len(one.memories) == 51 + 1 + 30
assert sum(e["kind"] == "chat" for e in read_events(who=one.name, last=10**9)) == 101, "the life log has them all"
line = render(logged[0])
assert line and "**Early life (Nanite One):**" in line
assert "early_life" not in TALKABLE
print("[ok] A nanite gets the note, the life log keeps every memory, and the journal shows it")

# Saved files from before v2.7 (limit 200) get the new limit; nothing else changes.
two.remember("chat", "Moiragen said: Hello? | I replied: Grey water under a bridge.")
two.blueprint["memory_keep"] = 200
two.save()
path = Path(os.environ["MEMORY_DIR"]) / "nanites" / "nanite_two.json"
assert json.loads(path.read_text(encoding="utf-8"))["blueprint"]["memory_keep"] == 200
again = Nanite.load("nanite_two")
assert again.blueprint["memory_keep"] == 1000 and again.memories == two.memories
assert (again.health, again.mood) == (two.health, two.mood)
again.memories = [chat(i) for i in range(202)]
again.remember("slept", "I slept.")
assert len(again.memories) == 203
print("[ok] An old nanite file gets the new limit by itself, and waking up no longer trims it")

# Rebuilt from the life log: labels stay, and an early-life note is not taken for a memory.
said = list(read_events(kind="chat", who=two.name, last=1))[0]
log_event("memory_note", two.name, note="Labelled.", changes=[
    {"time": said["time"], "old": said["text"], "new": PLAY + said["text"]}])
rebuilt = Nanite.rebuild_from_friend("nanite_two", one)
assert [m["text"] for m in rebuilt.memories].count(PLAY + said["text"]) == 1
rebuilt = Nanite.rebuild_from_friend("nanite_one", three)
assert [m["text"] for m in rebuilt.memories[:FIRST_MEMORIES]] == [m["text"] for m in first]
assert sum(m["kind"] == "chat" for m in rebuilt.memories) == 101, "with room for 1000, they are all whole again"
assert not any(m["kind"] == "early_life" for m in rebuilt.memories)
print("[ok] A rebuild from the life log keeps the first memories and the labels")

# ---------------- 4. Moiragen ----------------
m = Moiragen.load()
health = m.health
for i in range(40):
    m.remember("inner", f"I wonder about the colour of morning {i}.")
for i in range(350):
    m.remember("story_note", f"A gentle note {i}.")
assert sum(x["kind"] == "inner" for x in m.memories) == 40 and not any(x["kind"] == "early_life" for x in m.memories)
mother_mod.MEMORY_KEEP = 100
for i in range(40, 110):
    m.remember("inner", f"I wonder about the colour of morning {i}.")
whole = [x for x in m.memories if x["kind"] not in NOTES]
early = [x for x in m.memories if x["kind"] == "early_life"]
assert len(early) == 1 and early[0]["count"] == SUMMARISE and "inner thoughts" in early[0]["text"], early
assert whole[0] == m.memories[0] and len(whole) <= 100 and m.health == health
assert list(read_events(kind="early_life", who="Moiragen", last=10))[0]["text"] == early[0]["text"]
m.save()
assert Moiragen.load().memories == m.memories
first = [x["text"] for x in whole[:FIRST_MEMORIES]]
log_before = LOG_FILE.read_bytes()
MOIRAGEN_FILE.write_text("{broken", encoding="utf-8")
back = Moiragen.load()
# (From the life log he also gets back the line of his very first waking.)
assert back.memories[0]["kind"] == "birth"
assert [x["text"] for x in back.memories[1:FIRST_MEMORIES]] == first[:FIRST_MEMORIES - 1]
assert sum(x["kind"] == "early_life" for x in back.memories) >= 1
assert LOG_FILE.read_bytes().startswith(log_before), "the life log is only ever added to"
print("[ok] The same for Moiragen: notes push nothing out, and his first memories stay, also after a damaged file")

print("\nStep 25 passed: old memories last, and the very first stay whole.")

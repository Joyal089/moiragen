"""Old memories last (v2.7).

Each mind keeps many memories in its own file. When the limit is reached, the oldest are
not dropped: they are gathered into one short "early life" note, written in plain Python
(it only counts and quotes, so it cannot invent anything). Three things always stay whole:

  - its very first memories,
  - gentle notes and corrections, which do not count toward the limit at all,
  - the early-life notes themselves.

The life log (memory/log.jsonl) still has every memory word for word.
"""

import re
from collections import Counter

FIRST_MEMORIES = 20        # the very first memories, always kept whole
SUMMARISE = 50             # how many of the oldest go into one early-life note
QUOTES = 3                 # how many of its own lines a note quotes
# Never summarised, and never counted toward the limit: they must not push anything out.
NOTES = {"story_note", "correction", "restored", "early_life"}
LABEL = re.compile(r"^\[(?:about )?pretend play\b", re.IGNORECASE)

# How a note counts each kind of memory: (one, many).
WORDS = {
    "chat": ("talk", "talks"), "thought": ("private thought", "private thoughts"),
    "inner": ("inner thought", "inner thoughts"), "story_time": ("story-time moment", "story-time moments"),
    "noticed": ("thing that had everyone's attention", "things that had everyone's attention"),
    "chosen": ("time my answer was chosen", "times my answer was chosen"),
    "not_chosen": ("time another answer was chosen", "times another answer was chosen"),
    "decision": ("decision", "decisions"), "reflection": ("reflection", "reflections"),
    "slept": ("sleep", "sleeps"), "praised": ("kind word", "kind words"), "mistake": ("mistake", "mistakes"),
    "verdict": ("verdict from Moiragen", "verdicts from Moiragen"), "feedback": ("feedback", "feedbacks"),
    "reconsidered": ("time Moiragen's choice was thought about again", "times Moiragen's choice was thought about again"),
    "explained": ("explanation", "explanations"), "pattern": ("pattern noticed", "patterns noticed"),
    "story": ("story I told", "stories I told"), "learned_from": ("thing learned from a nanite", "things learned from nanites"),
    "wait_and_see": ("wait and see", "times of wait and see"), "lesson": ("lesson", "lessons"),
    "helped": ("time I helped a friend", "times I helped a friend"),
    "helped_by": ("time a friend helped me", "times a friend helped me"),
}
WITH_WHOM = re.compile(r"\b(Nanite (?:One|Two|Three)|Moiragen|user) said: |^I told (Nanite \w+): |^I comforted (Nanite \w+)")
OWN_WORDS = re.compile(r"\| I (?:replied|said): (.+)|^I told Nanite \w+: (.+?)(?: \| They |$)", re.DOTALL)


def _own_line(memory: dict) -> str:
    """The first sentence it said itself in this memory, or ""."""
    found = OWN_WORDS.search(memory["text"])
    said = " ".join(((found.group(1) or found.group(2)) if found else "").split())
    first = re.split(r"(?<=[.!?])\s+", said)[0].strip("\"“”")
    # (A line with quote marks inside may be someone else's words, so it is not quoted.)
    return first if 15 <= len(first) <= 120 and not re.search("[\"“”*]", first) else ""


def early_life_note(memories: list[dict], quotable: list[dict]) -> dict:
    """One short note about these memories. quotable: those it may quote from."""
    kinds = Counter(m["kind"] for m in memories if m["kind"] != "falling_asleep")
    parts = []
    for kind, n in kinds.most_common():
        one, many = WORDS.get(kind, ("memory of \"" + kind.replace("_", " ") + "\"",
                                     "memories of \"" + kind.replace("_", " ") + "\""))
        parts.append(f"{n} {one if n == 1 else many}")
    people = Counter()
    for m in memories:
        if m["kind"] == "chat":
            who = next((g for found in [WITH_WHOM.search(m["text"])] if found for g in found.groups() if g), None)
            if who:
                people["the human" if who == "user" else who] += 1
    start, end = memories[0]["time"][:16].replace("T", " "), memories[-1]["time"][:16].replace("T", " ")
    text = f"Early life, {start} to {end}, in short: {', '.join(parts)}."
    if people:
        text += " I talked with " + ", ".join(f"{who} ({n})" for who, n in people.most_common()) + "."
    played = sum(bool(LABEL.match(m["text"])) for m in memories)
    if played:
        text += f" {played} of these were about pretend play, not my real life."
    lines = [line for line in (_own_line(m) for m in quotable) if line]
    if lines:
        step = max(1, len(lines) // QUOTES)
        text += " Things I said then: " + " ".join(f"\"{line}\"" for line in lines[::step][:QUOTES])
    return {"time": memories[-1]["time"], "kind": "early_life", "text": text, "since": memories[0]["time"],
            "count": len(memories)}


def make_room(memories: list[dict], limit: int) -> tuple[list[dict], list[dict]]:
    """(the memories, the new early-life notes). Nothing changes while the limit is not
    reached. Otherwise the oldest ones, after the very first, become short notes."""
    new_notes = []
    while True:
        counted = [m for m in memories if m["kind"] not in NOTES]
        oldest = counted[FIRST_MEMORIES:][:SUMMARISE]
        if len(counted) <= limit or not oldest:
            return memories, new_notes
        going = {id(m) for m in oldest}
        # Never quote pretend play, or words that got a gentle note or a correction.
        noted = {id(m) for m, after in zip(memories, memories[1:]) if after["kind"] in ("story_note", "correction")}
        note = early_life_note(oldest, [m for m in oldest if id(m) not in noted and not LABEL.match(m["text"])])
        new_notes.append(note)
        kept = []
        for m in memories:
            if m is oldest[0]:
                kept.append(note)             # the note takes their place, so the order stays
            if id(m) not in going:
                kept.append(m)
        memories = kept

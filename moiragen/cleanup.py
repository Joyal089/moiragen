"""One-off clean-up of the echo loop's extra copies (run by clean_echo.py).

The nanites repeated two lines over and over:
    "Do you ever feel like we're just observing, and never really *in* it?"
    "It's... interesting, isn't it, how things shift?"
This removes the extra copies but keeps the FIRST time each line was said,
so nothing real is forgotten.

Words are kept in several places ("stores"), and each is cleaned on its own:
  - each nanite's memory (memories and lessons, oldest first): the first time
    THAT nanite met each line (said or heard) stays, so none of them forgets it
  - the record of what was said (the social feed and the training examples in
    the life log): only the very first time each line was said, by anyone, stays.
    In training examples only the reply is cleaned, since that is what a model
    would learn to say; the prompt shown at the time stays exactly as it was.
  - Moiragen's records: his memories, self-knowledge and decisions
If an entry held nothing but copies, the whole entry goes; if only part of it
was a copy, the rest stays (an empty part is marked "[repeated line removed]").
One exception: a lesson that was only a copy is replaced by the real "I
learned..." sentence the nanite said in the same reflection, when there is one
(the echo line had pushed the real lesson out).

The life log also keeps a copy of every nanite memory. Those copies get exactly
the same treatment as the memory itself, so a nanite rebuilt from the log later
gets the cleaned memories back.
"""

import re
from datetime import datetime

from .echo import split_sentences

# The two repeated lines, written to match the small variations seen in the data:
# "…" or "...", curly or straight apostrophes, *in* with or without the stars,
# and an optional friend's name in front ("Three, do you ever feel like… like…").
_APOS = "['’]"
_DOTS = "(?:…|\\.\\.\\.)"
TARGETS = {
    "observing": re.compile(
        rf"(?:(?:One|Two|Three),\s*)?[Dd]o you ever feel like\s*{_DOTS}?\s*(?:like\s+)?"
        rf"we{_APOS}re just observing,?\s+and never really \*?in\*? it\?"),
    "shift": re.compile(
        rf"It{_APOS}s\s*{_DOTS}?\s*interesting,?\s+isn{_APOS}t it,?\s+how things shift\?"),
}
LINES = {
    "observing": "Do you ever feel like we're just observing, and never really *in* it?",
    "shift": "It's... interesting, isn't it, how things shift?",
}
# Every copied "shift" line was introduced with "They're right.", so that goes with
# the copy. (Anywhere else, "They're right." is left alone.)
LEAD_IN = re.compile(rf"They{_APOS}re right\.\s*$")
MARKER = "[repeated line removed]"
SEP = " | "   # a memory joins what was said and the reply with " | "


def tidy(text: str) -> str:
    """Clean up the spaces a cut leaves behind."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class Store:
    """One place where words are kept. It remembers which repeated lines it has
    already seen, so the first copy of each line stays and later copies go."""

    def __init__(self, name: str):
        self.name = name
        self.seen: set[str] = set()
        self.kept: list[tuple[str, str, str]] = []   # (line, time, kind) of each first copy

    def clean(self, text: str, when: str = "", kind: str = "") -> tuple[str, list[str]]:
        """Return (the text without later copies, the pieces that were cut)."""
        hits = sorted((m.start(), m.end(), name)
                      for name, rx in TARGETS.items() for m in rx.finditer(text))
        cuts, removed = [], []
        for start, end, name in hits:
            if name not in self.seen:          # the first time this store has the line: keep it
                self.seen.add(name)
                self.kept.append((name, when, kind))
                continue
            if name == "shift":
                lead = LEAD_IN.search(text[:start])
                if lead and (not cuts or lead.start() >= cuts[-1][1]):
                    start = lead.start()
            cuts.append((start, end))
            removed.append(text[start:end].strip())
        if not cuts:
            return text, []
        out, pos = [], 0
        for start, end in cuts:
            out.append(text[pos:start])
            pos = end
        out.append(text[pos:])
        return tidy("".join(out)), removed


def _empty(part: str) -> bool:
    """A part with nothing said in it: blank, or only a label like "I replied:"."""
    p = part.strip()
    return not p or p.endswith(":")


def clean_entry(store: Store, text: str, kind: str = "", when: str = "") -> tuple[str | None, list[str]]:
    """Clean one entry. Returns (new text, what was cut); new text None = drop the entry."""
    new, removed = store.clean(text, when, kind)
    if not removed:
        return text, []
    old_parts, parts = text.split(SEP), new.split(SEP)
    if len(old_parts) != len(parts):           # a cut never crosses " | ", but be safe
        old_parts, parts = [text], [new]
    had = [not _empty(p) for p in old_parts]   # parts that said something before...
    now = [not _empty(p) for p in parts]       # ...and parts that still do
    if kind == "thought" and had[-1] and not now[-1]:
        return None, removed   # "<what happened> | I said: <words>" with no words left
    if not any(h and n for h, n in zip(had, now)):
        return None, removed   # nothing real is left
    fixed = [f"{p.strip()} {MARKER}".strip() if h and not n else p.strip()
             for p, h, n in zip(parts, had, now)]
    return SEP.join(fixed), removed


def _seconds_apart(a: str, b: str) -> float:
    return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds())


def real_lesson(memories: list[dict], when: str) -> str | None:
    """The "I learned..." sentence the nanite actually said in the reflection
    that produced a lesson at `when` (its thought memory from the same moment)."""
    for m in memories:
        if m.get("kind") != "thought" or "| I said:" not in m["text"]:
            continue
        if _seconds_apart(m["time"], when) > 3:
            continue
        for s in split_sentences(m["text"].split("| I said:", 1)[1]):
            if s.lstrip("*\"' ").lower().startswith("i learned"):
                return s.strip()
    return None


def _walk_strings(obj, fn, skip=("time", "kind", "who", "id", "decision_id", "nanite_id",
                                 "nanite", "chosen", "from", "to", "source")) -> None:
    """Replace every string inside obj (nested dicts/lists) with fn(string)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip:
                continue
            if isinstance(v, str):
                obj[k] = fn(v)
            else:
                _walk_strings(v, fn, skip)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = fn(v)
            else:
                _walk_strings(v, fn, skip)


def clean_memory(nanites: dict[str, dict], moiragen: dict, events: list[dict]) -> dict:
    """Clean everything in place. Returns a report:
        changes  - one dict per entry that changed (place, time, kind, action, removed, before, after)
        kept     - where the first copy of each line was kept, per place
        mirrored - how many life-log copies of nanite memories got the same change
        events   - the life-log events that remain (dropped ones are left out)
    """
    changes, kept = [], []

    def note(place, when, kind, before, after, removed, action=None):
        changes.append({"place": place, "time": when, "kind": kind, "removed": removed,
                        "action": action or ("deleted" if after is None else "trimmed"),
                        "before": before, "after": after})

    # 1. Each nanite's memory: memories and lessons together, oldest first.
    outcome = {}    # (who, time, kind, original text) -> (new text, removed), for the log copies
    restored = {}   # who -> [(time, real lesson)], so the social feed gets the same lesson back
    for data in nanites.values():
        who = data.get("chosen_name") or data["display_name"]
        store = Store(f"{who}'s memory")
        items = [(m["time"], 0, i, m) for i, m in enumerate(data["memories"])] + \
                [(l["time"], 1, i, l) for i, l in enumerate(data["lessons"])]
        drop = set()
        for when, is_lesson, _, entry in sorted(items, key=lambda x: x[:3]):
            field, kind = ("lesson", "lesson") if is_lesson else ("text", entry["kind"])
            before = entry[field]
            new, removed = clean_entry(store, before, kind, when)
            action = None
            if is_lesson and removed and new is None:
                new = real_lesson(data["memories"], when)   # the lesson it really said, if any
                if new:
                    action = "restored"
                    restored.setdefault(who, []).append((when, new))
            outcome[(who, when, kind, before)] = (new, removed)
            if removed:
                note(store.name, when, kind, before, new, removed, action)
                if new is None:
                    drop.add(id(entry))
                else:
                    entry[field] = new
        data["memories"] = [m for m in data["memories"] if id(m) not in drop]
        data["lessons"] = [l for l in data["lessons"] if id(l) not in drop]
        kept += [(store.name, *k) for k in store.kept]

    # 2. Moiragen's records (trimmed only; his records are never deleted).
    store = Store("Moiragen's records")
    records = [m for m in moiragen.get("memories", [])] + \
              [k for k in moiragen.get("self_knowledge", [])] + \
              [d for d in moiragen.get("decisions", {}).values()]
    for rec in sorted(records, key=lambda r: r.get("time", "")):
        def fix(text, rec=rec):
            new, removed = clean_entry(store, text, "record", rec.get("time", ""))
            if removed:
                note(store.name, rec.get("time", ""), rec.get("kind", "decision"), text, new or MARKER, removed)
            return text if not removed else (new or MARKER)
        _walk_strings(rec, fix)
    kept += [(store.name, *k) for k in store.kept]

    # 3. The life log.
    names = {d.get("chosen_name") or d["display_name"] for d in nanites.values()}
    stores: dict[tuple[str, str], Store] = {}
    remaining, mirrored = [], 0

    def store_for(group: str, who: str, label: str) -> Store:
        return stores.setdefault((group, who), Store(f"{who}'s {label}" if who else label))

    for e in events:
        kind, who, when = e.get("kind", ""), e.get("who", ""), e.get("time", "")
        if kind == "training_example":
            # What was said: one store for everyone, so only the very first time stays.
            st = store_for("training", "", "Training examples (replies)")
            new, removed = clean_entry(st, e.get("reply", ""), "reply", when)
            if removed:
                note(st.name, when, f"{kind} by {who}", e["reply"], new, removed)
                if new is None:
                    continue
                e["reply"] = new
                e["cleaned"] = "repeated line removed"
        elif kind.startswith("social_") and isinstance(e.get("text"), str):
            st = store_for("social", "", "Social feed (what was said)")
            new, removed = clean_entry(st, e["text"], kind, when)
            action = None
            if removed and new is None and kind == "social_lesson":
                new = next((l for t, l in restored.get(who, []) if _seconds_apart(t, when) <= 3), None)
                action = "restored" if new else None
            if removed:
                note(st.name, when, f"{kind} by {who}", e["text"], new, removed, action)
                if new is None:
                    continue
                e["text"] = new
        elif who in names and isinstance(e.get("text"), str):
            key = (who, when, kind, e["text"])
            if key in outcome:                  # a copy of a memory: same change as the memory
                new, removed = outcome[key]
            else:                               # only in the log (older than the memory file keeps)
                st = store_for("log-memory", who, "older memories (log only)")
                new, removed = clean_entry(st, e["text"], kind, when)
                if removed:
                    note(st.name, when, kind, e["text"], new, removed)
            if removed:
                mirrored += 1
                if new is None:
                    continue
                e["text"] = new
        else:
            st = store_for("other", who, "log records")
            def fix(text, when=when, kind=kind, st=st):
                new, removed = clean_entry(st, text, kind, when)
                if removed:
                    note(st.name, when, kind, text, new or MARKER, removed)
                return text if not removed else (new or MARKER)
            _walk_strings(e, fix)
        remaining.append(e)

    for st in stores.values():
        kept += [(st.name, *k) for k in st.kept]
    return {"changes": changes, "kept": kept, "mirrored": mirrored, "events": remaining}

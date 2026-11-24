"""The life log: every event in Moiragen's life, one JSON object per line.

Why JSONL (JSON Lines)?
- Appending a line is cheap and never rewrites old memories.
- If the program crashes, at most the last line is lost.
- It is the usual format for fine-tuning data later.

Each line looks like:
  {"time": "2026-11-20T21:03:12", "kind": "chat", "who": "Nanite One", ...}
"""

from datetime import datetime
import json
import threading

from .config import MEMORY_DIR

LOG_FILE = MEMORY_DIR / "log.jsonl"

# Several parts of the mind may log at the same moment; the lock stops
# two lines from being written on top of each other.
_lock = threading.Lock()


def log_event(kind: str, who: str, /, **details) -> dict:
    """Write one event to the life log and return it.

    kind:    what sort of event ("chat", "mistake", "help", "emotion", ...)
    who:     which mind it belongs to ("Moiragen", "Nanite One", "user", ...)
    details: anything else worth remembering (prompt, reply, mood, ...)

    The "/" makes kind and who positional-only, so a detail that happens to be
    called "kind" or "who" can never crash the call. Such a detail is kept
    under a "detail_" name instead of overwriting the real kind/who.
    """
    for key in ("kind", "who"):
        if key in details:
            details[f"detail_{key}"] = details.pop(key)
    event = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "who": who,
        **details,
    }
    line = json.dumps(event, ensure_ascii=False)
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return event


def read_events(kind: str | None = None, who: str | None = None, last: int = 50) -> list[dict]:
    """Read back the most recent events, optionally filtered by kind/who."""
    if not LOG_FILE.exists():
        return []
    events = []
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip a half-written line from a crash
            if kind and e.get("kind") != kind:
                continue
            if who and e.get("who") != who:
                continue
            events.append(e)
    return events[-last:]


def noted_changes(who: str) -> dict:
    """{(time, old text): new text}: labels and restored lines added to this mind's memories
    later ("memory_note" events), so a mind rebuilt from the life log keeps them (v2.4)."""
    return {(c["time"], c["old"]): c["new"] for e in read_events(kind="memory_note", who=who, last=10**6)
            for c in e.get("changes", [])}

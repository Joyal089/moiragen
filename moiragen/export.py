"""Turn Moiragen's life log into fine-tuning data.

Every time a mind thinks, the log records a "training_example": the exact
prompt it saw and what it replied. This module gathers those into the
standard chat format most fine-tuning tools accept:

    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}],
     "who": "Nanite Two", "task": "suggest", "decision_id": "a1b2c3d4",
     "chosen": true, "feedback": "right", "time": "..."}

Labels you can filter on later (for the nightly fine-tuning):
    chosen    - for a nanite's suggestion: did Moiragen pick it?
    feedback  - "right" / "wrong" if you marked that decision, else null

Exports go to memory/exports/ so they stay private (never pushed to Git).
"""

from collections import Counter
from datetime import datetime
import json

from .config import MEMORY_DIR
from .memory_log import read_events

EXPORT_DIR = MEMORY_DIR / "exports"


def _decision_labels(events: list[dict]) -> tuple[dict, dict]:
    """Which nanite won each decision, and what feedback you gave it."""
    chosen, feedback = {}, {}
    for e in events:
        did = e.get("decision_id") or (e.get("id") if e["kind"] == "decision_full" else None)
        if not did:
            continue
        if e["kind"] == "decision_full":
            chosen[did] = e.get("chosen")
        if e["who"] == "Moiragen" and "correct" in e:
            feedback[did] = "right" if e["correct"] else "wrong"   # the last mark wins
    return chosen, feedback


def build_examples(since: str | None = None, skip_wrong: bool = False) -> list[dict]:
    """All training examples (optionally only those on/after `since`, YYYY-MM-DD)."""
    events = read_events(last=10**9)
    chosen, feedback = _decision_labels(events)
    out = []
    for e in events:
        if e["kind"] != "training_example":
            continue
        if since and e["time"][:10] < since:
            continue
        did = e.get("decision_id")
        fb = feedback.get(did)
        if skip_wrong and fb == "wrong":
            continue
        messages = [{"role": "system", "content": e["system"]}] + e["messages"] + \
                   [{"role": "assistant", "content": e["reply"]}]
        record = {"messages": messages, "who": e["who"], "time": e["time"],
                  "task": e.get("task", "chat"), "decision_id": did, "feedback": fb}
        if e.get("task") == "suggest" and did in chosen:
            record["chosen"] = chosen[did] == e["who"]
        out.append(record)
    return out


def life_summary(since: str | None = None) -> dict:
    """Counts of what happened: conversations, mistakes, help, emotions..."""
    c = Counter()
    for e in read_events(last=10**9):
        if since and e["time"][:10] < since:
            continue
        c[e["kind"]] += 1
    return {
        "thoughts": c["training_example"],
        "decisions": c["decision_full"],
        "mistakes": c["mistake"],
        "help_given": c["social_help"],
        "comfort_given": c["social_support"],
        "talks": c["social_talk"],
        "lessons": c["lesson"],
        "reflections": c["reflection"],
        "surprises": c["surprise"],
        "emotion_changes": c["emotion"],
        "stories": c["story"],
    }


def export_training(since: str | None = None, skip_wrong: bool = False) -> tuple[str, dict]:
    """Write the examples to memory/exports/ and return (path, summary)."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    examples = build_examples(since, skip_wrong)
    path = EXPORT_DIR / f"training-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    summary = {
        "examples": len(examples),
        "by_mind": dict(Counter(ex["who"] for ex in examples)),
        "by_task": dict(Counter(ex["task"] for ex in examples)),
        "marked_right": sum(ex["feedback"] == "right" for ex in examples),
        "marked_wrong": sum(ex["feedback"] == "wrong" for ex in examples),
        "life": life_summary(since),
    }
    return str(path), summary

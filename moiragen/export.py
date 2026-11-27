"""Turn Moiragen's life log into fine-tuning data.

Every time a mind thinks, the log records a "training_example": the exact
prompt it saw and what it replied. This module gathers those into the
standard chat format most fine-tuning tools accept:

    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}],
     "who": "Nanite Two", "task": "suggest", "decision_id": "a1b2c3d4",
     "chosen": true, "feedback": "right", "time": "..."}

Labels you can filter on later (for the nightly fine-tuning):
    chosen    - for a nanite's suggestion: did Moiragen pick it?
    turn_round - (v3.1) the id of the Turn Round it was said in; only on those lines
    feedback  - "right" / "wrong" if you marked that decision, else null. For a
                situational question: "thoughtful", "okay", "needs_care", or
                "harmful" if you marked it unkind, dishonest or harmful

Replies that copy a line said shortly before them (the echo loop, see
echo.py) are left out: the echo check is replayed over the whole log, so
copies from before the live guard existed never become training data either.

Anything flagged as made-up, corrected, or labelled as pretend play is left out
too (v2.5, see training_rules.py). Pretend play stays in only if its question
clearly says it is that story; the example then says so as well ("story": title).

Exports go to memory/exports/ so they stay private (never pushed to Git).
"""

from collections import Counter
from datetime import datetime
import json

from .config import MEMORY_DIR
from .drive import after_backup
from .echo import NANITES, EchoGuard
from .memory_log import read_events
from .training_rules import TrainingRules

EXPORT_DIR = MEMORY_DIR / "exports"


def _decision_labels(events: list[dict]) -> tuple[dict, dict]:
    """Which nanite won each decision, and what feedback you gave it."""
    chosen, feedback = {}, {}
    for e in events:
        did = e.get("decision_id") or (e.get("id") if e["kind"] == "decision_full" else None)
        if not did:
            continue
        if e["kind"] in ("decision_full", "choice_changed"):
            chosen[did] = e.get("chosen")       # a later change of mind wins
        if e["who"] == "Moiragen" and "verdict" in e:      # a situational question
            feedback[did] = "harmful" if e.get("harmful") else e["verdict"]
        elif e["who"] == "Moiragen" and "correct" in e:
            feedback[did] = "right" if e["correct"] else "wrong"   # the last mark wins
    return chosen, feedback


def build_examples(since: str | None = None, skip_wrong: bool = False,
                   stats: dict | None = None, skip_rounds: bool = False) -> list[dict]:
    """All training examples (optionally only those on/after `since`, YYYY-MM-DD).
    skip_rounds: leave out everything said in Turn Rounds (v3.1).

    stats: pass a dict to learn how many were left out, and why.
    """
    events = read_events(last=10**9)
    chosen, feedback = _decision_labels(events)
    replay = EchoGuard(seed_from_log=False)   # the echo check, replayed from the start
    rules = TrainingRules(events)             # made-up, corrected, pretend play (v2.5)
    out, repeats, left_out = [], 0, Counter()
    for e in events:
        if e["kind"] == "decision_full" and e.get("question"):
            replay.allow(e["question"])         # the human's words may be repeated (v1.8)
        if e["kind"] != "training_example":
            continue
        group = "Moiragen" if e["who"] == "Moiragen" else NANITES
        copy = replay.check(e["reply"], group, e.get("decision_id"), speaker=e["who"]).too_similar
        if not copy:
            replay.add(e["who"], e["reply"], group, e.get("decision_id"))
        if since and e["time"][:10] < since:
            continue
        if copy:
            repeats += 1
            continue
        why_not = rules.why_not(e)
        if why_not:
            left_out[why_not] += 1
            continue
        did = e.get("decision_id")
        fb = feedback.get(did)
        if skip_wrong and fb in ("wrong", "harmful"):
            continue
        if skip_rounds and e.get("turn_round"):
            continue
        messages = [{"role": "system", "content": e["system"]}] + e["messages"] + \
                   [{"role": "assistant", "content": e["reply"]}]
        record = {"messages": messages, "who": e["who"], "time": e["time"],
                  "task": e.get("task", "chat"), "decision_id": did, "feedback": fb}
        if e.get("task") == "suggest" and did in chosen:
            record["chosen"] = chosen[did] == e["who"]
        if e.get("turn_round"):
            record["turn_round"] = e["turn_round"]          # said in a Turn Round (v3.1)
        if rules.story_mark(e):
            record["story"] = rules.story_mark(e)          # pretend play, clearly marked as a story
        out.append(record)
    if stats is not None:
        stats["left_out_repeats"] = repeats
        stats["left_out"] = {why: left_out[why] for why in ("made_up", "corrected", "pretend")}
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


def export_training(since: str | None = None, skip_wrong: bool = False,
                    skip_rounds: bool = False) -> tuple[str, dict]:
    """Write the examples to memory/exports/ and return (path, summary)."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stats = {}
    examples = build_examples(since, skip_wrong, stats, skip_rounds)
    path = EXPORT_DIR / f"training-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    summary = {
        "examples": len(examples),
        "left_out_repeats": stats["left_out_repeats"],
        "left_out_made_up": stats["left_out"]["made_up"],
        "left_out_corrected": stats["left_out"]["corrected"],
        "left_out_pretend_play": stats["left_out"]["pretend"],
        "marked_as_story": sum("story" in ex for ex in examples),
        "from_turn_rounds": sum("turn_round" in ex for ex in examples),
        "by_mind": dict(Counter(ex["who"] for ex in examples)),
        "by_task": dict(Counter(ex["task"] for ex in examples)),
        "marked_right": sum(ex["feedback"] == "right" for ex in examples),
        "marked_wrong": sum(ex["feedback"] == "wrong" for ex in examples),
        "life": life_summary(since),
    }
    after_backup()                 # Drive gets a copy, if it is set up (see drive.py)
    return str(path), summary

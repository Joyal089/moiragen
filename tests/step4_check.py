"""Step 4 check: Moiragen gathers suggestions, decides, explains, and learns from feedback.

Uses a throwaway memory folder. Needs Ollama running.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step4_check.py
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen.mother import Moiragen, parse_choice, WRONG_ANSWER_DAMAGE
from moiragen.nanite import load_all

# 1. The JSON reader survives messy replies (no model needed).
sugg = [{"nanite": "Nanite One", "text": "A"}, {"nanite": "Nanite Two", "text": "B"}]
assert parse_choice('{"chosen": "nanite two", "reason": "r", "answer": "x"}', sugg)["chosen"] == "Nanite Two"
assert parse_choice('Sure! {"chosen": "Two", "reason": "r", "answer": "x"} hope that helps', sugg)["chosen"] == "Nanite Two"
curly = '```json\n{"chosen": "Nanite Two", "reason": "clear", "answer": "It is fifty-six.”}\n```'
c = parse_choice(curly, sugg)
assert c["chosen"] == "Nanite Two" and c["reason"] == "clear" and c["answer"] == "It is fifty-six."
fallback = parse_choice("I like them all!", sugg)
assert fallback["chosen"] == "Nanite One" and fallback["answer"] == "A"
print("[ok] Choice reader handles messy or broken replies")

# 2. A real decision.
nanites = load_all()
moiragen = Moiragen.load()
health_before = {nid: n.health for nid, n in nanites.items()}

d = moiragen.decide("What is 7 times 8?", nanites)
print()
for s in d["suggestions"]:
    print(f"  {s['nanite']}: {s['text'][:150]}...")
print(f"\n  Chosen: {d['chosen']}\n  Reason: {d['reason']}\n  Answer: {d['answer']}\n")
assert len(d["suggestions"]) == 3
assert d["chosen"] in {s["nanite"] for s in d["suggestions"]}
assert d["reason"] and d["answer"]
assert "56" in d["answer"] or "fifty-six" in d["answer"].lower(), "Moiragen should get 7 x 8 right"
assert "could not decide" not in d["reason"], "Moiragen's reply should be readable"
print("[ok] Moiragen heard 3 suggestions, chose one, explained why, and answered")

# 3. Feelings: chosen one is happy; others are disappointed but NOT hurt.
for nid, n in nanites.items():
    if n.name == d["chosen"]:
        assert n.emotions["happy"] > 0 and n.memories[-1]["kind"] == "chosen"
    else:
        assert n.emotions["disappointed"] > 0 and n.emotions["left_out"] > 0
        assert n.memories[-1]["kind"] == "not_chosen"
    assert n.health == health_before[nid], "not being chosen must never cost health"
print("[ok] Chosen nanite happy; others mildly disappointed, health untouched")

# 4. Feedback: "wrong" hurts only the chosen nanite.
chosen = next(n for n in nanites.values() if n.name == d["chosen"])
others = [n for n in nanites.values() if n is not chosen]
reply = moiragen.feedback(d["id"], correct=False, nanites=nanites, note="(just a test)")
assert chosen.health == 100 - WRONG_ANSWER_DAMAGE
assert all(o.health == 100 for o in others)
assert moiragen.memories[-1]["kind"] == "mistake"
print(f"[ok] Marked wrong: {chosen.name} health -> {chosen.health}, others unchanged. Moiragen: '{reply}'")

# 5. Feedback: "right" makes it happy, no health change.
before = chosen.health
moiragen.feedback(d["id"], correct=True, nanites=nanites)
assert chosen.health == before and moiragen.memories[-1]["kind"] == "feedback"
print("[ok] Marked right: happy, no health change")

# 6. Moiragen remembers after a restart.
again = Moiragen.load()
assert d["id"] in again.decisions and any(m["kind"] == "decision" for m in again.memories)
print("[ok] Moiragen's memory survives a restart")

print("\nStep 4 passed.")

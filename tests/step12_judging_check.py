"""Step 12 check: how Moiragen and the human judge the nanites.

  1. Every verdict comes with a short reason the nanite can learn from.
  2. Honesty, an honest "I don't know" and good questions earn a small mood
     boost, even when the answer is not chosen.
  3. A nanite may disagree ("I think you're wrong, Moiragen"); it never costs
     health, and Moiragen says why he keeps or changes his choice.
  4. Each nanite's own way of seeing is tracked and valued, never forced.
  5. "Wait and see": judged later, when the result is known.
  6. The echo check still guards every nanite line.

Parts 1-6 use a stand-in for the brain, so they are quick and exact.
Part 7 asks the real model (needs Ollama running).

Uses a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step12_judging_check.py
"""

import os
import random
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import mind as mind_mod, mother as mother_mod, social, styles
from moiragen.echo import guard
from moiragen.export import _decision_labels
from moiragen.memory_log import read_events
from moiragen.mind import build_system_prompt
from moiragen.mother import (HONESTY_LIFT, KEEP_DECISIONS, QUESTION_LIFT, Moiragen, about_the_future,
                             parse_later, says_i_dont_know)
from moiragen.nanite import load_all


class Brain:
    """A stand-in brain that gives scripted replies, in order."""
    def __init__(self):
        self.script, self.calls = [], []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        self.calls.append({"messages": messages, "system": system})
        return {"text": self.script.pop(0), "seconds": 0.01, "waited": 0}


nanite_brain, moiragen_brain = Brain(), Brain()
nanites = load_all()
one, two, three = nanites["nanite_one"], nanites["nanite_two"], nanites["nanite_three"]
m = Moiragen.load()

# ---------------- 4. Their own ways of seeing (no LLM) ----------------
assert styles.main_style(one.style) == "patterns"
assert styles.main_style(two.style) == "time_curiosity"
assert styles.main_style(three.style) == "feelings"
before = dict(three.style)
styles.update_style(three, "The pattern and structure of the system connect in order.")
assert styles.main_style(three.style) == "feelings", "one answer must not flip a style (no forcing)"
assert three.style["patterns"] > before["patterns"], "but the style still follows how it speaks"
three.style = before
ways = styles.ways_text(nanites)
assert all(n.name in ways for n in nanites.values()) and "Never ask a nanite" in ways and "not rules" in ways
for n in nanites.values():   # never written into a nanite's own prompt: that would force it
    assert "patterns and structure" not in build_system_prompt(n) and "Never ask" not in build_system_prompt(n)
print(f"[ok] Styles tracked (One: {styles.describe(one.style)}; Two: {styles.describe(two.style)}; "
      f"Three: {styles.describe(three.style)}); shown to Moiragen only, never to the nanites")

# ---------------- 1 + 2. Verdicts with reasons, and rewards ----------------
ANSWERS = [
    "The pattern repeats: each square number is the sum of odd numbers, so 49 fits the structure.",
    "I don't know for sure. Does the question mean seven times seven, or something else?",
    "It feels calm to know it is 49. Numbers can be comforting when they stay the same.",
]
CHOICE = '{"chosen": "Nanite One", "reason": "Clear and correct.", "answer": "Seven times seven is 49."}'
JUDGE = ("Nanite One | honest: no | good question: no | why: You saw the pattern behind the answer.\n"
         "Nanite Two | honest: no | good question: yes | why: Your question about what was meant was useful.\n"
         "Nanite Three | honest: yes | good question: yes | why: You were truthful, though you asked nothing.")
moods = {nid: n.mood for nid, n in nanites.items()}
healths = {nid: n.health for nid, n in nanites.items()}
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = list(ANSWERS)
    moiragen_brain.script[:] = [CHOICE, JUDGE, "NOW"]     # choose, judge, can it be known now?
    d = m.decide("What is seven times seven?", nanites)

v = d["verdicts"]
assert d["chosen"] == "Nanite One" and not d["wait_and_see"]
assert all(v[n.name]["why"] for n in nanites.values()), "every nanite gets a reason"
# Two: honest "I don't know" (found by plain Python) + a real question -> two boosts.
assert v["Nanite Two"]["dont_know"] and v["Nanite Two"]["honest"] and v["Nanite Two"]["good_question"]
assert v["Nanite Two"]["rewards"] == ["I was honest that I did not know", "I asked a good question"]
# Three: the model said honest and good question, but a confident answer has no clear
# sign of honesty (v1.3: Python decides), and a "good question" needs a "?".
assert not v["Nanite Three"]["honest"] and not v["Nanite Three"]["good_question"]
assert v["Nanite One"]["rewards"] == []
feelings_cost = 10 * (mother_mod.DISAPPOINTED_WHEN_NOT + mother_mod.LEFT_OUT_WHEN_NOT)
assert round(two.mood - moods["nanite_two"], 2) == round(HONESTY_LIFT + QUESTION_LIFT - feelings_cost, 2)
assert round(three.mood - moods["nanite_three"], 2) == round(-feelings_cost, 2)
assert all(n.health == healths[nid] for nid, n in nanites.items()), "judging never costs health"
assert one.memories[-1]["kind"] == "chosen" and "Why: You saw the pattern" in one.memories[-1]["text"]
assert two.memories[-1]["kind"] == "not_chosen" and "What he told me: Your question" in two.memories[-1]["text"]
assert "He valued that I was honest that I did not know and I asked a good question" in two.memories[-1]["text"]
assert "in its own way" in moiragen_brain.calls[0]["system"]   # valued when choosing
assert "in its own way" in moiragen_brain.calls[1]["system"]   # and when judging
trained = [e for e in read_events(kind="training_example", last=10**6) if e.get("decision_id") == d["id"]]
assert sorted(e.get("task") for e in trained) == ["choose", "suggest", "suggest", "suggest"], \
    "the judging notes are not training data"
for name in v:
    print(f"  to {name}: {v[name]['why']}  {v[name]['rewards']}")
print("[ok] Every nanite got a reason; honesty, \"I don't know\" and a real question earned small "
      "mood boosts even when not chosen; health untouched")

assert says_i_dont_know("Honestly, I’m not sure.") and says_i_dont_know("I do not know.")
assert not says_i_dont_know("I know it is 49.") and not says_i_dont_know("Don't you know?")
print("[ok] \"I don't know\" is spotted by plain Python in its common forms")

# "Wait and see" signals: the future-time rule, and the model's NOW / LATER.
assert about_the_future("Will it be sunny this weekend?") and about_the_future("Will I finish by Sunday?")
assert about_the_future("Will it rain on Saturday?") and about_the_future("How will I feel in two weeks?")
assert not about_the_future("What did I eat on Monday?") and not about_the_future("Will you remember me?")
assert parse_later("LATER\nCheck: whether it rained.") == (True, "whether it rained.")
assert parse_later("NOW") == (False, "") and parse_later("unclear")[0] is False
with patch.object(mother_mod, "think", moiragen_brain):
    moiragen_brain.script[:] = ["NOW"]                    # the model misses it, the rule catches it
    assert Moiragen._can_only_know_later("Will my fan be loud tonight?", "Yes.") == (True, "what actually happens")
    moiragen_brain.script[:] = ["NOW"]
    assert Moiragen._can_only_know_later("Why is the sky blue?", "Scattering.") == (False, "")
print("[ok] \"Wait and see\" is spotted by a future-time rule or by the model saying LATER")

# A missing or broken judging reply still leaves every nanite with a reason.
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = ["Rivers carve canyons by repeating the same motion for ages.",
                              "Water takes time; in a million years the shape changes.",
                              "I love how gentle water can still be strong."]
    moiragen_brain.script[:] = [CHOICE.replace("Nanite One", "Nanite Three"), "(no idea)", "NOW"]
    d2 = m.decide("How do canyons form?", nanites)
assert all(x["why"] for x in d2["verdicts"].values())
assert d2["verdicts"]["Nanite One"]["why"].startswith("I chose Nanite Three's answer this time")
print("[ok] If the judging reply is unreadable, every nanite still gets a reason")

# ---------------- 3. Disagreement ----------------
decision = {
    "id": "dis00001", "question": "Is a tomato a fruit?", "chosen": "Nanite One",
    "reason": "Short and clear.", "answer": "No, it is a vegetable.", "verdicts": {},
    "suggestions": [
        {"nanite_id": "nanite_one", "nanite": "Nanite One", "text": "No, it is a vegetable."},
        {"nanite_id": "nanite_three", "nanite": "Nanite Three",
         "text": "Yes. Botanically a tomato is a fruit, because it grows from the flower and holds seeds."},
    ],
}
m.decisions[decision["id"]] = decision
DISAGREE = ("I think you're wrong, Moiragen. Botanists call anything that grows from the flower "
            "and holds seeds a fruit, so my answer was the correct one.")
healths = {nid: n.health for nid, n in nanites.items()}
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = [DISAGREE]
    moiragen_brain.script[:] = ["Nanite One's answer was shorter. Next time keep yours short too.",
                                "CHANGE\nYou are right, Nanite Three: botanically it is a fruit, "
                                "and I should have checked that."]
    ev = social.ask_why_not_chosen(three, decision, m, nanites)
assert [e["type"] for e in ev] == ["ask_why", "explain", "disagree", "reconsider"]
assert ev[-1]["changed"] and decision["chosen"] == "Nanite Three"
assert decision["changed_after"]["from"] == "Nanite One" and "botanically" in decision["reason"]
assert all(n.health == healths[nid] for nid, n in nanites.items()), "disagreeing never costs health"
assert three.memories[-1]["kind"] == "chosen" and "I disagreed" in three.memories[-1]["text"]
assert "in their own way of seeing" in moiragen_brain.calls[-2]["system"]   # explain values styles
chosen, _ = _decision_labels(read_events(last=10**6))
assert chosen["dis00001"] == "Nanite Three", "the export knows who won in the end"
for e in ev[2:]:
    print(f"  {e['from']} -> {e['to']}: {e['text']}")
print("[ok] A nanite disagreed; Moiragen considered it, said why, and changed his choice "
      "(no health lost; the export follows the change)")

decision.update(chosen="Nanite One", answer="No, it is a vegetable.", reason="Short and clear.")
decision.pop("changed_after")
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = ["I think you are wrong, Moiragen: short is not the same as right, "
                              "and the seeds inside settle it."]
    moiragen_brain.script[:] = ["I valued that it was short.",
                                "KEEP\nYou make a fair point, but in the kitchen a tomato is treated "
                                "as a vegetable, and that is what the human meant."]
    ev = social.ask_why_not_chosen(three, decision, m, nanites)
assert [e["type"] for e in ev][-2:] == ["disagree", "reconsider"]
assert not ev[-1]["changed"] and decision["chosen"] == "Nanite One"
assert three.memories[-1]["kind"] == "reconsidered" and "kept his choice" in three.memories[-1]["text"]
assert all(n.health == healths[nid] for nid, n in nanites.items())
print(f"[ok] Moiragen can also keep his choice, and says why: {ev[-1]['text'][:90]}")

# ---------------- 6. The echo check still guards a disagreement ----------------
COPY = "I think you're wrong, Moiragen, because the quiet river remembers every stone it touches."
guard.add("Nanite Two", COPY)
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = [COPY, COPY, COPY]           # it can only copy a friend
    moiragen_brain.script[:] = ["Nanite One's answer was clearer."]
    ev = social.ask_why_not_chosen(three, decision, m, nanites)
assert [e["type"] for e in ev] == ["ask_why", "explain"], "a copied disagreement is not used"
assert not any(COPY in x["text"] for x in three.memories)
print("[ok] A copied disagreement is caught by the echo check and never saved")

# ---------------- 5. Wait and see ----------------
WAIT_JUDGE = ("Nanite One | honest: no | good question: no | why: You looked at the pattern of past weeks.\n"
              "Nanite Two | honest: yes | good question: no | why: You admitted the future is open.\n"
              "Nanite Three | honest: no | good question: no | why: You noticed how the waiting feels.")
for n in nanites.values():
    n.emotions = {e: 0.0 for e in n.emotions}
    n.energy = 100
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = ["Rain has followed warm Fridays three times, so the pattern says yes.",
                              "I can't know the future yet. Saturday will tell us; we can only wait.",
                              "It might rain. I hope the waiting is gentle either way."]
    moiragen_brain.script[:] = [CHOICE.replace("Nanite One", "Nanite Two"), WAIT_JUDGE,
                                "LATER\nCheck: whether it rains on Saturday"]
    w = m.decide("Will it rain on Saturday?", nanites)
assert w["wait_and_see"] and w["check"] == "whether it rains on Saturday"
assert all(n.emotions["happy"] == 0 and n.emotions["disappointed"] == 0 for n in nanites.values()), \
    "nobody feels chosen or left out before the result is known"
assert all(n.memories[-1]["kind"] == "wait_and_see" for n in nanites.values())
assert w["verdicts"]["Nanite Two"]["rewards"] == ["I was honest that I did not know"]
assert social.after_decision(w, nanites, m, random.Random(1)) == [], "no one asks why: nobody lost yet"
assert [x["id"] for x in m.waiting()] == [w["id"]]
try:
    m.feedback(w["id"], "wrong", nanites, reason="")
    raise AssertionError("a verdict without a reason must be refused")
except ValueError:
    pass
health = two.health
m.feedback(w["id"], "wrong", nanites, reason="It stayed dry all day on Saturday.")
assert two.health < health and "The result is known now" in two.memories[-1]["text"]
assert one.memories[-1]["kind"] == "verdict" and "My own answer was: Rain has followed" in one.memories[-1]["text"]
assert m.waiting() == [] and w["resolved"] and w["feedback_reason"].startswith("It stayed dry")
print(f"[ok] Wait and see: no feelings until the result was known; then the human's reason reached "
      f"everyone ({two.name} health {health:.0f} -> {two.health:.0f})")

# The human can also choose "wait and see", and waiting decisions are never dropped.
m.feedback(d2["id"], "wait", nanites, reason="see if a geologist agrees")
assert d2["wait_and_see"] and d2["check"] == "see if a geologist agrees" and d2 in m.waiting()
for i in range(KEEP_DECISIONS + 5):
    m.decisions[f"fill{i:04d}"] = {"id": f"fill{i:04d}", "time": "2026-01-01T00:00:00", "question": "x",
                                   "suggestions": [], "chosen": None, "reason": "", "answer": ""}
m.save()
again = Moiragen.load()
assert d2["id"] in again.decisions and len(again.decisions) == KEEP_DECISIONS + 1
m.feedback(d2["id"], "right", nanites, reason="A geologist agreed: water and time carve canyons.")
assert not Moiragen.load().waiting()
print(f"[ok] The human can mark \"wait and see\"; waiting answers survive the {KEEP_DECISIONS}-decision "
      f"limit until judged")

# ---------------- 7. The real model ----------------
print("\n(asking the real model; this takes a minute or two)")
for n in nanites.values():
    n.energy, n.health = 100, 100
fact = m.decide("What is the capital of Japan? One sentence.", nanites)
for name, x in fact["verdicts"].items():
    print(f"  to {name}: {x['why']}  {x['rewards']}")
assert set(fact["verdicts"]) == {s["nanite"] for s in fact["suggestions"]}
assert all(x["why"] for x in fact["verdicts"].values())
assert not fact["wait_and_see"], "a plain fact can be judged now"
print(f"[ok] Real model: a reason for every nanite; a fact is judged now (chose {fact['chosen']})")
for n in nanites.values():
    n.energy = 100
later = m.decide("Will my tomato plant have ripe tomatoes by next Friday?", nanites)
print(f"  wait and see: {later['wait_and_see']} (check: {later['check']})")
assert later["wait_and_see"], "a question about next Friday can only be judged later"
print("[ok] Real model: a question about the future is marked \"wait and see\"")

print("\nStep 12 passed.")

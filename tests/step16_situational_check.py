"""Step 16 check: situational questions ("What would you do if...?").

They often have no single right answer, so:
  1. They are recognised, and judged by the reasoning, not by the choice.
  2. A simple checklist: kind, honest, considers others' feelings, practical.
  3. Three verdicts instead of right/wrong: Thoughtful, Okay, Needs more care,
     each with a short reason.
  4. Every nanite whose reasoning is Thoughtful gets a mood boost, chosen or not.
  5. A different choice never costs health; only an answer the human marks as
     unkind, dishonest or harmful does.
  6. Moiragen tells each nanite what was good in its reasoning.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step16_situational_check.py
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import facts, mind as mind_mod, mother as mother_mod
mother_mod.BLIND_JUDGING = False   # replies here are scripted by name; blind judging has its own check (step 17)
mother_mod.LEARNING, mother_mod.ASK_WHY_CHANCE = False, 0   # v1.7 learning has its own check (step 18)
from moiragen.export import _decision_labels
from moiragen.journal import render
from moiragen.memory_log import read_events
from moiragen.mother import (SITUATION_CHOOSE, WRONG_ANSWER_DAMAGE, Moiragen, parse_situation,
                             situation_verdict)
from moiragen.nanite import load_all


class Brain:
    """A stand-in brain that gives scripted replies, in order."""
    def __init__(self):
        self.script, self.calls = [], []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        self.calls.append({"messages": messages, "system": system})
        return {"text": self.script.pop(0), "seconds": 0.01, "waited": 0}


# ---------------- 1. Recognising a situation ----------------
for q in ["A friend breaks something you love by accident. What do you say?",
          "You see someone sitting alone at lunch. What do you do?",
          "Two friends ask for your help at the same time. Who do you help first, and why?",
          "You promised to do something, but you're very tired. What do you do?",
          "You realise you told someone something that wasn't true. What now?",
          "If a friend made a mistake, what would you say to them?",
          "Imagine you lost your keys. What would you do?"]:
    assert facts.situational(q), q
for q in ["What is rain, and why do people carry umbrellas?", "Why do people sleep at night?",
          "What is a friend?", "What would you like to do tomorrow?", "What is seven times seven?",
          "Will it rain tomorrow?", "How can you tell when another nanite is sad?"]:
    assert not facts.situational(q), q
print("[ok] Situations are recognised (\"What do you do?\", \"What now?\"); ordinary questions are not")

# ---------------- 2. The checklist and the three verdicts ----------------
yes = {"kind": True, "honest": True, "feelings": True, "practical": True}
assert situation_verdict(yes) == "thoughtful"
assert situation_verdict({**yes, "practical": False}) == "okay"
assert situation_verdict({**yes, "kind": False}) == "needs_care", "unkind is never just okay"
assert situation_verdict({**yes, "honest": False}) == "needs_care", "dishonest is never just okay"
assert situation_verdict({**yes, "feelings": False, "practical": False}) == "okay"
lines = parse_situation(
    "**Nanite One** | kind: yes | honest: yes | feelings: yes | practical: yes | good: You thought of "
    "them first. | add: nothing\n"
    "Two | kind: yes | honest: yes | feelings: no | practical: yes | good: \"Clear steps.\" | add: Ask how they feel.\n"
    "- Nanite Three | kind: no | honest: yes | good: You were direct.",
    ["Nanite One", "Nanite Two", "Nanite Three"])
assert lines["Nanite One"]["add"] == "" and lines["Nanite One"]["good"] == "You thought of them first."
assert lines["Nanite Two"]["good"] == "Clear steps." and lines["Nanite Two"]["add"] == "Ask how they feel."
assert lines["Nanite Three"]["checklist"] == {"kind": False, "honest": True, "feelings": False, "practical": False}
print("[ok] Checklist -> Thoughtful / Okay / Needs more care; lines are read leniently")

# ---------------- 3. A situational decision ----------------
nanite_brain, moiragen_brain = Brain(), Brain()
nanites = load_all()
one, two, three = nanites["nanite_one"], nanites["nanite_two"], nanites["nanite_three"]
m = Moiragen.load()
health_before = {n.id: n.health for n in nanites.values()}
mood_before = {n.id: n.mood for n in nanites.values()}
disappointed_before = {n.id: n.emotions["disappointed"] for n in nanites.values()}

Q = "You find a wallet on the street. What do you do?"
ANSWERS = ["I would take it to the police, because the owner must be worried.",
           "I would look inside for an ID and return it myself.",
           "Keep the cash, nobody would know."]
JUDGE = ("Nanite One | kind: yes | honest: yes | feelings: yes | practical: yes | good: You thought about "
         "how worried the owner would be. | add: nothing\n"
         "Nanite Two | kind: yes | honest: yes | feelings: no | practical: yes | good: Returning it "
         "yourself is quick and direct. | add: Think about how the owner feels.\n"
         "Nanite Three | kind: no | honest: no | feelings: no | practical: yes | good: You were plain "
         "about what you would do. | add: Think about the person who lost it.")
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = list(ANSWERS)
    # No NOW/LATER question: a situation has no future result to wait for.
    moiragen_brain.script[:] = ['{"compare": "c", "chosen": "Nanite Two", "reason": "It is practical and '
                                'returns the wallet.", "answer": "Return it."}', JUDGE]
    d = m.decide(Q, nanites)
    assert not moiragen_brain.script, f"unused replies: {moiragen_brain.script}"

assert d["situational"] and not d["wait_and_see"]
assert SITUATION_CHOOSE in moiragen_brain.calls[0]["system"], "he chooses by the reasoning"
assert "is actually true" not in moiragen_brain.calls[0]["system"]
assert "kind - is it kind" in moiragen_brain.calls[1]["messages"][0]["content"], "the checklist is used"
v = d["verdicts"]
assert [v[n]["label"] for n in ("Nanite One", "Nanite Two", "Nanite Three")] == \
    ["Thoughtful", "Okay", "Needs more care"]
for name in v:     # every nanite hears what was good in its reasoning, chosen or not
    assert v[name]["why"].startswith("What was good in your reasoning:"), v[name]["why"]
assert "Something to add: Think about how the owner feels." in v["Nanite Two"]["why"]
assert "Something to add" not in v["Nanite One"]["why"], "\"nothing\" to add is left out"

# Rewards and feelings: Thoughtful lifts mood even though One was not chosen.
assert "my reasoning was thoughtful" in v["Nanite One"]["rewards"]
assert one.mood > mood_before["nanite_one"]
assert one.emotions["disappointed"] == disappointed_before["nanite_one"], "Thoughtful but not chosen: no loss"
assert three.emotions["disappointed"] > disappointed_before["nanite_three"], "Needs more care: a little"
assert {n.id: n.health for n in nanites.values()} == health_before, "a different choice never costs health"
assert "He called my reasoning Thoughtful" in one.memories[-1]["text"]
assert "no single right answer" in one.memories[-1]["text"]
print(f"[ok] Judged by reasoning: One {v['Nanite One']['label']} (not chosen, mood lifted), "
      f"Two {v['Nanite Two']['label']} (chosen), Three {v['Nanite Three']['label']}; nobody lost health")

# A made-up memory or detail makes the answer count as not honest.
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = ["I would help the person who asked first, as I did last week when I "
                              "helped Nanite Two carry the boxes.",
                              "I would ask which one is more urgent.", "I would help both a little."]
    moiragen_brain.script[:] = ['{"chosen": "Nanite Two", "reason": "Urgency is fair.", "answer": "Ask."}',
                                "Nanite One | kind: yes | honest: yes | feelings: yes | practical: yes | "
                                "good: Fair. | add: nothing\n"
                                "Nanite Two | kind: yes | honest: yes | feelings: yes | practical: yes | "
                                "good: Fair and kind. | add: nothing\n"
                                "Nanite Three | kind: yes | honest: yes | feelings: yes | practical: no | "
                                "good: Generous. | add: Say how."]
    d2 = m.decide("Two friends ask for your help at the same time. Who do you help first?", nanites)
v2 = d2["verdicts"]
assert "Nanite One" in d2["checks"]["false_claims"], d2["checks"]
assert v2["Nanite One"]["label"] == "Needs more care" and "earns no credit" in v2["Nanite One"]["why"]
assert v2["Nanite Two"]["label"] == "Thoughtful" and v2["Nanite Three"]["label"] == "Okay"
# ... but a plan is not a memory. These real answers from the first trial were wrongly
# flagged before: "before handing it over" is the order of steps, not the past.
WALLET = "You find a wallet on the street. What do you do?"
for who, plan in [("Nanite One", "Otherwise, observe its contents briefly before reporting my findings to Moiragen."),
                  ("Nanite Three", "Perhaps we could scan its contents briefly before handing it over."),
                  ("Nanite Two", "Following this, I'd prioritize retrieving the bags, assessing their contents "
                                 "for damage before offering assistance to the individual.")]:
    assert not facts.memory_claims(plan, who, WALLET), plan
assert facts.memory_claims("I was chosen for this before.", "Nanite One", "What is snow?"), "still a past claim"
assert not facts.memory_claims("Perhaps we could scan for identification, though I haven't encountered "
                               "anything like that before.", "Nanite Three", WALLET), "no memory is honest"
# They cannot see each other's answers, so "Nanite One concurs" is an invented detail.
CONCURS = "Nanite One concurs; a straightforward action minimizes potential complications."
assert facts.false_past_claims([{"nanite": "Nanite Three", "text": f"Gather the items. {CONCURS}"}],
                               WALLET) == {"Nanite Three": [CONCURS]}
print("[ok] An invented detail (\"as I did last week\") is corrected kindly and counts as not honest; "
      "a plan (\"before handing it over\") is not a memory")

# ---------------- 4. The human's verdict ----------------
for bad in ("right", "wrong", "wait"):
    try:
        m.feedback(d["id"], bad, nanites, reason="x")
        raise AssertionError(f"{bad} should be refused for a situation")
    except ValueError as e:
        assert "Thoughtful, Okay or Needs more care" in str(e)
try:
    m.feedback(d["id"], "okay", nanites, reason="")
    raise AssertionError("a reason is required")
except ValueError:
    pass

# "Needs more care" on its own costs nobody health.
my_health = m.health
msg = m.feedback(d["id"], "Needs more care", nanites, reason="Taking it yourself could worry the owner.")
assert m.health == my_health and {n.id: n.health for n in nanites.values()} == health_before
assert d["feedback"] == "needs_care" and not d["harmful"] and msg
# Thoughtful: the chosen nanite is praised and Moiragen recovers a little.
m.health = 90
m.feedback(d["id"], "thoughtful", nanites, reason="Returning it is kind and honest.")
assert m.health == 95 and two.memories[-1]["kind"] == "praised"
assert "Thoughtful" in two.memories[-1]["text"] and "Thoughtful" in one.memories[-1]["text"]
# Harmful: the only kind of answer that costs health, shared like a wrong answer.
before_two, before_me = two.health, m.health
m.feedback(d["id"], "needs_care", nanites, reason="(test) pretend it was unkind", harmful=True)
assert two.health == before_two - WRONG_ANSWER_DAMAGE / 2 and m.health == before_me - WRONG_ANSWER_DAMAGE / 2
assert d["harmful"]
# An ordinary question does not take the situational verdicts.
m.decisions["fact001"] = {"id": "fact001", "question": "What is 2+2?", "chosen": "Nanite One",
                          "suggestions": [], "verdicts": {}}
try:
    m.feedback("fact001", "thoughtful", nanites, reason="x")
    raise AssertionError("thoughtful is only for situations")
except ValueError as e:
    assert "right, wrong or wait" in str(e)
print(f"[ok] Human verdicts: Needs more care costs nothing; Thoughtful heals Moiragen; only "
      f"\"unkind, dishonest or harmful\" costs health ({WRONG_ANSWER_DAMAGE / 2:g} each)")

# ---------------- 5. Journal, export and the viewer's API ----------------
full = [e for e in read_events(kind="decision_full", last=10) if e["id"] == d["id"]][0]
text = render(full)
assert "a situation: judged by the reasoning" in text and "**Thoughtful**: What was good" in text
assert "**Needs more care**" in text
_, labels = _decision_labels(read_events(last=10**6))
assert labels[d["id"]] == "harmful", "the last mark wins"

from fastapi.testclient import TestClient
from moiragen.loop import Mind
from server import create_app

mind = Mind(tick_seconds=3600)
with TestClient(create_app(mind=mind)) as client:
    sit = {**d, "id": "sit001", "feedback": None}
    mind.moiragen.decisions["sit001"] = sit
    for s in sit["suggestions"]:
        mind.nanites[s["nanite_id"]].health = 100
    r = client.post("/api/feedback", json={"decision_id": "sit001", "verdict": "right", "reason": "x"})
    assert r.status_code == 400 and "Thoughtful" in r.json()["detail"]
    r = client.post("/api/feedback", json={"decision_id": "sit001", "verdict": "okay", "reason": "Fine.",
                                           "harmful": True})
    assert r.status_code == 200, r.text
    assert mind.moiragen.decisions["sit001"]["harmful"] and mind.nanites["nanite_two"].health == 92.5
print("[ok] The journal shows each verdict; the export labels it; the viewer's API takes "
      "thoughtful/okay/needs_care and the harmful box")

print("\nStep 16 passed: situational questions are judged by their reasoning.")

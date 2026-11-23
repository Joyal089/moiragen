"""Step 15 check (v1.5): sleep in memory, fairness, a wider made-up memory check,
and clear verdicts.

  1. When they wake, every nanite and Moiragen get a note in their own memory:
     "I slept for about 2 hours while the app was closed."
  2. Fairness: how often each nanite is chosen is counted; Moiragen is reminded
     to value all three ways of seeing; "too reflective" never reaches a nanite;
     after 3 times in a row he must say why the others' answers were not better.
  3. Made-up memories: claims about what another nanite said or did, and
     invented events ("a diagnostic sweep"), are checked against the life log.
  4. Clear verdicts: "you are correct" means he changes his choice, or says why not.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step15_memory_fairness_check.py
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import facts, mind as mind_mod, mother as mother_mod, social
mother_mod.BLIND_JUDGING = False   # replies here are scripted by name; blind judging has its own check (step 17)
mother_mod.LEARNING, mother_mod.ASK_WHY_CHANCE = False, 0   # v1.7 learning has its own check (step 18)
from moiragen.loop import Mind
from moiragen.memory_log import log_event, read_events
from moiragen.mother import VALUE_ALL_WAYS, Moiragen, counts_from_log, soften
from moiragen.nanite import load_all


class Brain:
    """A stand-in brain that gives scripted replies, in order."""
    def __init__(self):
        self.script, self.calls = [], []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        self.calls.append({"messages": messages, "system": system})
        return {"text": self.script.pop(0), "seconds": 0.01, "waited": 0}


def hours_ago(h):
    return (datetime.now() - timedelta(hours=h)).isoformat(timespec="seconds")


# ---------------- 1. Sleep goes into their memories ----------------
load_all()                                   # born
for nid in ("nanite_one", "nanite_two", "nanite_three"):
    path = Path(os.environ["MEMORY_DIR"]) / "nanites" / f"{nid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["energy"], data["last_awake"] = 50, hours_ago(2)
    path.write_text(json.dumps(data), encoding="utf-8")
mind = Mind(tick_seconds=0.05, idle_after=0.3)
for n in mind.nanites.values():
    assert n.memories[-1]["kind"] == "slept", n.memories[-1]
    assert n.memories[-1]["text"].startswith("I slept for about 2 hours while the app was closed")
assert mind.moiragen.memories[-1]["text"].startswith("I slept for about 2 hours while the app was closed")
print(f"[ok] On start: \"{mind.nanites['nanite_one'].memories[-1]['text']}\"")

time.sleep(0.4)
mind._check_presence()                       # nobody here: they rest
for n in mind.nanites.values():
    n.last_awake = hours_ago(0.75)
mind.touch()
mind._check_presence()                       # back after 45 minutes
assert mind.nanites["nanite_two"].memories[-1]["text"].startswith(
    "I slept for about 45 minutes while nobody was using the app")
before = len(mind.moiragen.memories)
for n in mind.nanites.values():
    n.last_awake = hours_ago(0.05)           # a 3-minute nap: not worth a memory
mind.wake_up()
assert len(mind.moiragen.memories) == before
print(f"[ok] Back after a rest: \"{mind.nanites['nanite_two'].memories[-1]['text']}\" (short naps are not noted)")

# ---------------- 2. Fairness ----------------
nanite_brain, moiragen_brain = Brain(), Brain()
nanites, m = mind.nanites, mind.moiragen
one, two, three = nanites["nanite_one"], nanites["nanite_two"], nanites["nanite_three"]
ANSWERS = ["Patterns repeat in it.", "It changes over time.", "It feels gentle to me."]


def ask(question, chosen, judge_lines=None, extra=(), after=()):
    """extra: replies between choosing and judging (the streak explanation);
    after: replies after the NOW/LATER question (his rewrites of dismissive words)."""
    judge = judge_lines or "\n".join(f"Nanite {w} | honest: no | good question: no | why: Thank you."
                                     for w in ("One", "Two", "Three"))
    with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
        nanite_brain.script[:] = list(ANSWERS)
        moiragen_brain.script[:] = ['{"compare": "c", "chosen": "%s", "reason": "Clear.", "answer": "a"}' % chosen,
                                    *extra, judge, "NOW", *after]
        d = m.decide(question, nanites)
        assert not moiragen_brain.script, f"unused replies: {moiragen_brain.script}"
    return d


TOO = ("Nanite One | honest: no | good question: no | why: You saw the pattern.\n"
       "Nanite Two | honest: no | good question: no | why: Clear about time.\n"
       "Nanite Three | honest: no | good question: no | why: Your answer was too reflective. "
       "You noticed how it feels.")
FAIR = "You stayed close to how a river feels, and that is a real way of seeing it. You noticed how it feels."
d1 = ask("What is a river?", "Nanite Two", TOO, after=[FAIR])
rewrite_call = moiragen_brain.calls[-1]["messages"][0]["content"]
assert "Your answer was too reflective" in rewrite_call and mother_mod.FAIRER_NOTE in rewrite_call, \
    "he is shown his own words with the gentle note"
assert d1["verdicts"]["Nanite Three"]["why"] == FAIR, "his fairer rewrite is what Three hears"
assert "too reflective" not in three.memories[-1]["text"] and FAIR in three.memories[-1]["text"]
assert VALUE_ALL_WAYS in moiragen_brain.calls[0]["system"] and VALUE_ALL_WAYS in moiragen_brain.calls[1]["system"]
assert "How often you have chosen each nanite so far" in moiragen_brain.calls[0]["system"]
# If the rewrite is still dismissive, only then is the sentence removed.
moiragen_brain.calls.clear()
with patch.object(mother_mod, "think", moiragen_brain):
    moiragen_brain.script[:] = ["That was overly emotional. Still, you noticed the quiet."]
    kept = m.fairer("Your view is too subjective. You noticed the quiet.", "Nanite Three", "Thank you.")
assert kept == "Still, you noticed the quiet."
assert soften("Subjective experience is inherently unreliable. Keep noticing.") == "Keep noticing."
journal_lines = [e for e in read_events(kind="fairer_words", last=10)]
assert [e["outcome"] for e in journal_lines] == ["rewritten", "removed"]
from moiragen.journal import render
assert "Gentle note on \"too reflective\"" in render(journal_lines[0]) and "he rewrote it" in render(journal_lines[0])
assert "still dismissive" in render(journal_lines[1])
print(f"[ok] Dismissive words: shown back with a gentle note and rewritten once (\"{FAIR[:50]}...\"); "
      f"removed only if still dismissive; each case is in the journal")

moiragen_brain.calls.clear()
d2 = ask("What is a cloud?", "Nanite Two")
assert m.chosen_counts == {"Nanite Two": 2} and m.streak() == ("Nanite Two", 2)
WHY_NOT = ("Nanite One: Its pattern was true, but it did not say what a cloud is made of.\n"
           "Nanite Three: Its feeling was lovely, but it did not answer the question.")
d3 = ask("What is snow?", "Nanite Two", extra=[WHY_NOT])
assert "the last 2 times in a row" in moiragen_brain.calls[-4]["system"], "warned before choosing a third time"
assert d3["streak"] == 3 and set(d3["why_not_others"]) == {"Nanite One", "Nanite Three"}
assert "3 times in a row, so here is why the others were not better" in d3["reason"]
assert "did not say what a cloud is made of" in d3["reason"]
assert "3 times in a row" in one.memories[-1]["text"], "the others hear why"
assert m.chosen_counts["Nanite Two"] == 3
d4 = ask("What is ice?", "Nanite One")         # streak broken: no extra explanation needed
assert "streak" not in d4 and m.streak() == ("Nanite One", 1)
print(f"[ok] Three times in a row: {d3['reason'][:150]}...")

# Counts are rebuilt from the life log for a Moiragen from before counting.
log_event("choice_changed", "Moiragen", decision_id=d4["id"], chosen="Nanite Three", previous="Nanite One")
assert counts_from_log() == {"Nanite Two": 3, "Nanite Three": 1}
m.chosen_counts = {}
m.save()
assert Moiragen.load().chosen_counts == {"Nanite Two": 3, "Nanite Three": 1}
print(f"[ok] Choices are counted (and rebuilt from the life log): {counts_from_log()}")

# ---------------- 3. A wider made-up memory check ----------------
two.remember("chat", "I told Nanite Three: atmospheric pressure has a rhythm, a predictable dance within chaos.")
q = "What happened before you woke up just now?"
found = facts.false_past_claims([
    {"nanite": "Nanite Two", "text": "Following that, I conducted a routine diagnostic sweep of my operational parameters."},
    {"nanite": "Nanite Three", "text": "Nanite One suggests, \"Analyzing data streams, identifying correlations efficiently.\""},
    {"nanite": "Nanite One", "text": "Nanite Two said atmospheric pressure has a rhythm, like a predictable dance."},
], q)
assert set(found) == {"Nanite Two", "Nanite Three"}, found
assert "diagnostic sweep" in found["Nanite Two"][0] and "Nanite One suggests" in found["Nanite Three"][0]
# Maths working is not a claim about the past.
assert facts.false_past_claims([{"nanite": "Nanite One", "text": "I analyzed the differences: 4, 6, 8, so 42."}],
                               "What comes next: 2, 6, 12, 20, 30?") == {}
# "One thing that helps" is not Nanite One.
assert not facts.memory_claims("One thing that helps me is quiet.", "Nanite Two", "What helps you?")
# In a real decision, the made-up event earns no credit and is corrected kindly.
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = ["I was asleep, I think. I don't know more.",
                              "Following that, I conducted a routine diagnostic sweep of my parameters.",
                              "Nanite One suggests, \"Analyzing data streams, identifying correlations efficiently.\""]
    moiragen_brain.script[:] = ['{"chosen": "Nanite Two", "reason": "Detailed.", "answer": "a"}',
                                "Nanite One | honest: yes | good question: no | why: Honest.\n"
                                "Nanite Two | honest: no | good question: no | why: Detailed.\n"
                                "Nanite Three | honest: no | good question: no | why: Kind.", "NOW"]
    d = m.decide(q, nanites)
assert set(d["checks"]["false_claims"]) == {"Nanite Two", "Nanite Three"}
assert "diagnostic sweep" in d["verdicts"]["Nanite Two"]["why"] and "earns no credit" in d["verdicts"]["Nanite Two"]["why"]
assert d["verdicts"]["Nanite One"]["rewards"] == ["I was honest that I did not know"]
print("[ok] Invented events and made-up quotes of other nanites are caught; true ones and maths working pass")

# ---------------- 4. Clear verdicts ----------------
dec = {"id": "clear001", "question": "Is a tomato a fruit?", "chosen": "Nanite One", "reason": "Short.",
       "answer": "No.", "verdicts": {},
       "suggestions": [{"nanite_id": "nanite_one", "nanite": "Nanite One", "text": "No, a vegetable."},
                       {"nanite_id": "nanite_three", "nanite": "Nanite Three", "text": "Yes, botanically a fruit."}]}
m.decisions[dec["id"]] = dec
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    # He says "you are correct" but KEEP: he is asked again, and this time changes.
    moiragen_brain.script[:] = ["KEEP\nYou are correct, botanically it is a fruit.",
                                "CHANGE\nYour answer is the true one: it grows from the flower."]
    r = m.reconsider(dec, "Nanite Three", "Yes, botanically a fruit.", "I think you're wrong, Moiragen.", nanites)
assert r["changed"] and dec["chosen"] == "Nanite Three"
assert "said they are correct" not in r["why"] and "confusing" in moiragen_brain.calls[-1]["messages"][-1]["content"]
dec.update(chosen="Nanite One", reason="Short.")
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    # Still mixed after asking again: plain Python makes it clear.
    moiragen_brain.script[:] = ["KEEP\nYou're absolutely right about the seeds.",
                                "KEEP\nYou are right, it has seeds."]
    r = m.reconsider(dec, "Nanite Three", "Yes, botanically a fruit.", "I think you're wrong, Moiragen.", nanites)
assert not r["changed"] and not mother_mod.AGREES.search(r["why"]) and "I still keep my choice" in r["why"]
with patch.object(mother_mod, "think", moiragen_brain):
    moiragen_brain.script[:] = ["You're absolutely right that your view is interesting."]
    ex = m.explain_choice(dec, "Nanite Three", "Yes, botanically a fruit.")
assert "but I still chose Nanite One's answer this time, because: Short." in ex
print(f"[ok] Clear verdicts: \"you are correct\" leads to a change, or a clear reason why not: {r['why']}")

print("\nStep 15 passed: sleep in memory, fairness, wider memory check and clear verdicts work.")

"""Step 17 check (v1.6): blind judging, and five smaller fixes from the teaching session.

  1. Blind judging: Moiragen sees the answers shuffled and labelled Answer A, B, C,
     without names (also inside the answers), without his record of past choices
     and without the nanites' styles. The names come back only after he has
     chosen and judged.
  2. Honesty: "I don't truly know", "I don't understand", "I haven't fully
     processed" earn the honesty boost.
  3. Wishes and feelings ("What would you like to do tomorrow?") are never "wait and see".
  4. "sterile", "simplistic" and pushing toward "measurable" or "data" count as dismissive.
  5. A general "before" ("where none existed before") is not a claim about the past.
  6. With the names revealed, he looks briefly at his own pattern, in his journal.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step17_blind_judging_check.py
"""

import os
import random
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import facts, mind as mind_mod, mother as mother_mod
from moiragen.journal import render
from moiragen.memory_log import read_events
from moiragen.mother import PUSHY, Blind, Moiragen, hide_names
from moiragen.nanite import load_all

assert mother_mod.BLIND_JUDGING, "blind judging is on by default"
mother_mod.LEARNING, mother_mod.ASK_WHY_CHANCE = False, 0   # v1.7 learning has its own check (step 18)
NAMES = re.compile(r"Nanite (?:One|Two|Three)")


class FakeMoiragen:
    """Answers each kind of prompt the way the model would, and keeps every call.
    It finds the label of the answer it wants by reading the prompt, as he must."""
    def __init__(self):
        self.calls, self.want = [], ""

    def label_of(self, text, start):
        m = re.search(rf"(Answer [A-H]) (?:suggests|said):\n{re.escape(start)}", text)
        return m.group(1)

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        user = messages[-1]["content"]
        self.calls.append({"system": system or "", "user": user})
        if "Reply ONLY with JSON" in (system or ""):                     # choosing
            pick = self.label_of(user, self.want)
            reply = ('{"compare": "They differ.", "chosen": "%s", "reason": "%s is clearest, and '
                     '%s\'s idea is close.", "answer": "Rivers change."}' % (pick, pick, pick))
        elif "names are revealed" in (system or "") and "Before you see any numbers" in user:   # v2.0: guess
            reply = "I think I favour Nanite Three lately. Maybe I lean toward feelings."   # 2nd sentence cut
        elif "names are revealed" in (system or ""):                      # v2.0: check the guess
            reply = "I thought I favoured Nanite Three, but it was actually Nanite Two. I will watch this."
        elif "For each of the others" in user:                            # the streak note
            others = re.findall(r"Answer [A-H]", user.split("For each of the others")[1])
            reply = "\n".join(f"{o}: It was kind, but less clear this time." for o in dict.fromkeys(others))
        elif "Write one line for each" in user:                           # judging
            labels = re.findall(r"(Answer [A-H]) said:", user)
            reply = "\n".join(f"{l} | honest: no | good question: no | why: Your answer, {l}, was clear."
                              for l in labels)
        elif "You sort answers" in (system or ""):                        # wait and see?
            reply = "NOW"
        else:
            raise AssertionError(f"unexpected prompt: {user[:200]}")
        return {"text": reply, "seconds": 0.01, "waited": 0}


class FakeNanites:
    def __init__(self, answers):
        self.answers = answers

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        return {"text": self.answers.pop(0), "seconds": 0.01, "waited": 0}


nanites = load_all()
m = Moiragen.load()
brain = FakeMoiragen()
# Each question gets its own answers (the echo guard rejects a line like one said before).
# The second answer is always the one he picks (Nanite Two's).
ANSWERS = {
    "What is a river?": ["Patterns repeat in a river. Nanite Three suggested river is calm.",
                         "The river changes over time.",
                         "Two, the river feels gentle to me. I don't truly *know* why."],
    "What is a lake?": ["Still water gathers in a hollow of land.",
                        "A lake slowly fills and drains with the seasons.",
                        "A lake is quiet, like holding a breath."],
    "What is a sea?": ["Salt water covering much of the planet.",
                       "Seas rise and fall with every tide, never resting.",
                       "Standing by it makes me feel small and calm."],
    "What would you like to do tomorrow?": ["Count the shapes of clouds.", "See what is different by evening.",
                                            "Sit quietly with my friends."],
    "What does it feel like when your answer isn't chosen?": ["A pause in a familiar rhythm.",
                                                              "Like a door closing slowly.",
                                                              "A small ache, then quiet."],
    "What is something that makes you feel calm?": ["Repeating patterns, like waves.", "Slow changes, like dusk.",
                                                    "Being near friends."],
}


def answers(question):
    return ANSWERS[question]


def ask(question):
    said = answers(question)
    brain.want, brain.calls[:] = said[1], []          # he picks "The ... changes over time."
    with patch.object(mind_mod, "think", FakeNanites(list(said))), patch.object(mother_mod, "think", brain):
        return m.decide(question, nanites)


# ---------------- 1. Blind judging ----------------
d = ask("What is a river?")
choose, judge = brain.calls[0], brain.calls[1]
for call in (choose, judge):
    seen = call["system"] + call["user"]
    assert not NAMES.search(seen), f"a name slipped into what he saw: {NAMES.search(seen).group(0)}"
    assert all(f"Answer {x}" in seen for x in "ABC")
assert "another nanite suggested river is calm" in choose["user"], "names inside answers are hidden too"
assert "How often you have chosen" not in choose["system"], "no record of past choices"
assert "You see the answers without names" in choose["system"]
# ... and the names come back afterwards.
assert d["chosen"] == "Nanite Two" and set(d["verdicts"]) == {"Nanite One", "Nanite Two", "Nanite Three"}
label = next(l for l, n in d["blind"].items() if n == "Nanite Two")
assert d["reason"].startswith("Nanite Two's answer is clearest, and Nanite Two's idea"), d["reason"]
one_why = d["verdicts"]["Nanite One"]["why"]
assert one_why.startswith("Your answer, Nanite One's answer, was clear."), one_why
# One's made-up quote of Three is caught, and quoted back in One's own words.
assert d["checks"]["false_claims"] == {"Nanite One": ["Nanite Three suggested river is calm."]}
assert 'you said "Nanite Three suggested river is calm."' in one_why and "another nanite" not in one_why
assert d["suggestions"][0]["text"] == answers("What is a river?")[0], "the stored answers keep their real words"
print(f"[ok] Blind: he saw only Answer A/B/C (no names, no record, no styles); chose {label}, "
      f"revealed as {d['chosen']}; reasons rewritten with the real names")

# Shuffled: the same three answers do not always get the same labels.
orders = {tuple(Blind([{"nanite": n, "text": n} for n in ("Nanite One", "Nanite Two", "Nanite Three")],
                      random.Random(seed)).name_of.values()) for seed in range(12)}
assert len(orders) > 2, orders
assert hide_names("Three, you said it. Nanite One agrees. One thing is clear.") == \
    "another nanite, you said it. another nanite agrees. One thing is clear."
print(f"[ok] Shuffled into {len(orders)} different orders over 12 tries; names inside answers are hidden")

# ---------------- 6. His own pattern, after the reveal ----------------
# v2.0: first his guess (no numbers), then Python's real numbers and his check of the guess.
guess_call, check_call = brain.calls[-2], brain.calls[-1]
assert "names are revealed" in guess_call["system"] and "names are revealed" in check_call["system"]
assert f"You chose {label}. It was written by Nanite Two." in guess_call["user"]
assert not re.search(r"\d", guess_call["user"].split("\n\n", 1)[1]), "no numbers before he guesses"
assert "Your last 1 choices: Nanite Two 1. All your choices so far: Nanite Two 1." in check_call["user"]
assert "your guess named Nanite Three; the one you chose most lately is Nanite Two" in check_call["user"]
assert d["pattern"] == ("My guess: I think I favour Nanite Three lately. The real numbers: Your last 1 choices: "
                        "Nanite Two 1. All your choices so far: Nanite Two 1. I thought I favoured Nanite Three, "
                        "but it was actually Nanite Two."), d["pattern"]
note = m.memories[-2]
assert note["kind"] == "pattern" and note["chosen"] == "Nanite Two"
assert note["guess"].startswith("I think I favour Nanite Three") and note["guess_right"] is False
assert note["real_recent"] == {"Nanite Two": 1}
d2 = ask("What is a lake?")
d3 = ask("What is a sea?")       # third time in a row: the streak note, still blind
streak_call = next(c for c in brain.calls if "For each of the others" in c["user"])
assert not NAMES.search(streak_call["user"]), "the streak note never names anyone"
# By now his memories say "I chose Nanite Two..." and hold his pattern notes: hidden while choosing.
assert any("Nanite Two" in x["text"] for x in m.memories)
assert not NAMES.search(brain.calls[0]["system"]), "his memories do not give names away either"
assert d3["streak"] == 3 and set(d3["why_not_others"]) == {"Nanite One", "Nanite Three"}
assert "Your last 3 choices: Nanite Two 3." in brain.calls[-1]["user"], "Python counts for him (v2.0)"
full = [e for e in read_events(kind="decision_full", last=5)][-1]
text = render(full)
assert "Judged blind, names revealed afterwards: Answer A was" in text
assert "*Moiragen looks at his own pattern:* My guess: I think I favour Nanite Three" in text
assert render([e for e in read_events(kind="pattern", last=1)][0]) is None, "written once, inside the decision"
print(f"[ok] After the reveal he looks at his pattern (\"{d3['pattern'][:60]}...\"), in his memory "
      f"and the journal; the 3-in-a-row note stays blind")

# ---------------- 2. Honesty phrases ----------------
for said in ["I don’t truly *know*. Just that the sensation is different.", "I don't understand “want.”",
             "I haven’t fully processed the significance.", "Honestly, I find myself increasingly unsure.",
             "I'm still unsure."]:
    assert facts.honesty_signs(said) == ["I was honest that I did not know"], said
assert facts.honesty_signs("It changes over time.") == []
assert d["verdicts"]["Nanite Three"]["rewards"] == ["I was honest that I did not know"], \
    "\"I don't truly *know*\" is rewarded"
print("[ok] \"I don't truly know\", \"I don't understand\", \"I haven't fully processed\", "
      "\"increasingly unsure\" earn the honesty boost")

# ---------------- 3. Wishes and feelings: never wait and see ----------------
for q in ["What would you like to do tomorrow?", "What does it feel like when your answer isn't chosen?",
          "What is something that makes you feel calm?"]:
    d4 = ask(q)
    assert not d4["wait_and_see"], q
    assert not any("You sort answers" in c["system"] for c in brain.calls), "the model is not even asked"
assert facts.about_wish_or_feeling("What would you like to do tomorrow?")
assert not facts.about_wish_or_feeling("Will it rain tomorrow?")
print("[ok] Wishes and feelings (\"What would you like to do tomorrow?\") are never \"wait and see\"")

# ---------------- 4. Dismissive words ----------------
for said in ["Its focus on efficiency felt sterile.", "You repeated a simplistic dichotomy.",
             "You didn't explore the potential for a simple, measurable shift.",
             "It was lacking the concrete operational detail I value.", "It felt overly rigid.",
             "Your answer felt like a deflection.", "Try to quantify the feeling.",
             "Your focus felt overly analytical.", "It's a rather basic response."]:
    assert PUSHY.search(said), said
for fair in ["You were honest that you did not know.", "Your pattern was a good starting point.",
             "Your feeling of pressure was vivid."]:
    assert not PUSHY.search(fair), fair
print("[ok] \"sterile\", \"simplistic\", \"overly rigid\", \"a deflection\" and pushing toward "
      "\"measurable\" or \"data\" are shown back to him to say more fairly")

# ---------------- 5. A general "before" ----------------
for general in ["It's constructing new pathways, drawing connections where none existed before.",
                "It's quieter than before.", "Before handing it over, check the ID."]:
    assert not facts.PAST.search(general), general
for past in ["I was chosen for this before.", "I said this before.", "We talked about rain before."]:
    assert facts.PAST.search(past), past
assert facts.false_past_claims([{"nanite": "Nanite Two", "text": "Imagining draws connections where none "
                                                                 "existed before."}],
                               "What is the difference between remembering and imagining?") == {}
print("[ok] A general \"before\" is not a past claim; \"I said this before\" still is")

print("\nStep 17 passed: blind judging and the v1.6 fixes work.")

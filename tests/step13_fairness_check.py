"""Step 13 check: fairer judging (v1.3).

  1. Claims about the past are checked against the real life log. A made-up
     one is pointed out kindly and earns no credit; a true one is fine.
  2. Moiragen is told to judge the answer, not the speaker, and to compare
     the answers before choosing.
  3. Maths: a small Python calculator finds the real answer, and Moiragen
     follows it.
  4. A wrong answer costs health, shared by Moiragen and the chosen nanite.
  5. The honesty boost needs a clear sign ("I don't know", "I'm not sure",
     admitting a mistake, changing your mind), never just confidence.
  6. Softer disagreements ("you prioritized the wrong thing") are caught,
     and Moiragen reconsiders.
  7. "Wait and see" only for real future events, never for made-up situations.

Uses a stand-in for the brain, so it is quick and exact (no Ollama needed).
Uses a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step13_fairness_check.py
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import facts, mind as mind_mod, mother as mother_mod, social
from moiragen.mother import HONESTY_LIFT, JUDGE_THE_ANSWER, WRONG_ANSWER_DAMAGE, Moiragen
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


def ask(question, answers, choice, judge, later="NOW"):
    """One decision with scripted answers. later=None: the model is not asked (made-up situation)."""
    with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
        nanite_brain.script[:] = list(answers)
        moiragen_brain.script[:] = [choice, judge] + ([later] if later else [])
        d = m.decide(question, nanites)
        assert not moiragen_brain.script, "every scripted reply was used"
    return d


def choice(name, reason="It is correct.", answer=""):
    return ('{"compare": "They agree on the city but differ in detail.", "chosen": "%s", '
            '"reason": "%s", "answer": "%s"}' % (name, reason, answer))


def judge(*whys, honest="no"):
    return "\n".join(f"Nanite {w} | honest: {honest} | good question: no | why: {why}"
                     for w, why in zip(("One", "Two", "Three"), whys))


# ---------------- 1. Claims about the past ----------------
# Today's real case: Nanite Two said it had seen this chosen before, on the first time it was asked.
CLAIM = "I observed Moiragen selecting this response previously."
moods = {nid: n.mood for nid, n in nanites.items()}
d = ask("What is the capital of Australia?",
        ["Canberra is the capital; it was planned as a compromise city.",
         f"Canberra. It's designated as such. {CLAIM}",
         "Canberra. It feels calm and carefully planned."],
        choice("Nanite Two", "It said this was chosen before, and it is correct.", "Canberra."),
        judge("You gave the reason behind it.", "You were right and confident.", "You noticed its feeling.",
              honest="yes"))
v = d["verdicts"]["Nanite Two"]
assert d["checks"]["false_claims"] == {"Nanite Two": [CLAIM]}, d["checks"]
assert not v["honest"] and v["rewards"] == [], "a made-up memory earns no credit"
assert "did not happen" in v["why"] and CLAIM in v["why"] and "kindly" in v["why"]
assert "did not happen" in two.memories[-1]["text"], "Two remembers the correction, not just the praise"
assert "Give no credit for it" in moiragen_brain.calls[-3]["messages"][0]["content"], "told when choosing"
assert "Give no credit for it" in moiragen_brain.calls[-2]["messages"][0]["content"], "and when judging"
assert not any(x["honest"] for x in d["verdicts"].values()), "the model's 'honest: yes' is not enough"
print(f"[ok] Made-up past claim caught and kindly corrected: {v['why'][-150:]}")

# A TRUE claim: Nanite Two really was chosen above, so saying so is fine.
assert facts.false_past_claims([{"nanite": "Nanite Two", "text": "You chose my answer before, I remember."}],
                               "What is the capital of Peru?") == {}
assert facts.false_past_claims([{"nanite": "Nanite Three", "text": "You chose my answer before, I remember."}],
                               "What is the capital of Peru?") != {}, "Three has never been chosen"
# The same question asked again: now "this was chosen before" is true.
assert facts.false_past_claims([{"nanite": "Nanite Two", "text": CLAIM}],
                               "What is the capital of Australia?") == {}
print("[ok] True claims about the past are checked against the log and left alone")

# ---------------- 2. Judge the answer, not the speaker; compare first ----------------
assert JUDGE_THE_ANSWER in moiragen_brain.calls[-3]["system"] and '"compare"' in moiragen_brain.calls[-3]["system"]
assert JUDGE_THE_ANSWER in moiragen_brain.calls[-2]["messages"][0]["content"]
assert d["compare"].startswith("They agree on the city")
print("[ok] Moiragen compares the answers and is told to judge the answer, not the speaker")

# ---------------- 3. The calculator ----------------
assert facts.calculate("What is seven times eight?")["answer"] == 56
assert facts.calculate("What is 12 / 4 + 1?")["answer"] == 4
assert facts.calculate("What comes next: 1, 4, 9, 16, 25?")["answer"] == 36
assert facts.calculate("What is the capital of Japan?") is None
assert facts.calculate("__import__('os').system('dir')") is None, "never runs code"
assert facts.final_number("Therefore the answer is forty-two.") == 42
# Seen with the real model: the answer up front, then a step that mentions another number.
assert facts.final_number("Forty-two. The pattern adds even numbers, so the next step would be plus fourteen.") == 42
assert facts.final_number("Six minus two equals four, so the answer is 42.") == 42
d = ask("What number comes next: 2, 6, 12, 20, 30?",
        ["The differences grow by two: 4, 6, 8, 10, so add twelve. That gives us forty-two.",
         "The differences are +4, +6, +8, +10, +12, so 30 + 14 = 44.",
         "The next difference should be eleven, so thirty plus eleven equals forty-one."],
        choice("Nanite Two", "Clear steps.", "The next number is 44."),
        judge("You found the pattern.", "Your steps were clear.", "You followed the rhythm."))
assert d["chosen"] == "Nanite One" and d["first_choice"] == "Nanite Two", "the calculator corrects the choice"
assert "calculator" in d["reason"] and "42" in d["reason"] and "forty-two" in d["answer"]
assert d["checks"]["calculator"]["right"] == ["Nanite One"]
assert "ended on 44" in d["verdicts"]["Nanite Two"]["why"] and "ended on 41" in d["verdicts"]["Nanite Three"]["why"]
assert "Calculator: the correct answer is 42" in moiragen_brain.calls[-3]["messages"][0]["content"]
assert one.memories[-1]["kind"] == "chosen" and two.memories[-1]["kind"] == "not_chosen"
print(f"[ok] Calculator: 42 is right, so Moiragen chose Nanite One. Reason: {d['reason']}")
math_id = d["id"]

# ---------------- 4. A fair share of the cost ----------------
before = (one.health, m.health)
msg = m.feedback(math_id, "wrong", nanites, reason="(test) pretend it was wrong")
assert one.health == before[0] - WRONG_ANSWER_DAMAGE / 2 and m.health == before[1] - WRONG_ANSWER_DAMAGE / 2
assert "share the cost" in msg and "shares the cost with me" in one.memories[-1]["text"]
assert two.health == 100 and three.health == 100, "not being chosen never costs health"
alone = {"id": "alone001", "time": "x", "question": "q", "suggestions": [], "chosen": None,
         "reason": "", "answer": ""}
m.decisions[alone["id"]] = alone
h = m.health
m.feedback("alone001", "wrong", nanites, reason="(test) wrong when answering alone")
assert m.health == h - WRONG_ANSWER_DAMAGE, "answering alone, he carries it all"
m.feedback(math_id, "right", nanites, reason="(test) it was right after all")
assert m.health == h - WRONG_ANSWER_DAMAGE + mother_mod.RIGHT_ANSWER_HEAL
print(f"[ok] Wrong answer: Moiragen and the chosen nanite each lost {WRONG_ANSWER_DAMAGE / 2:g} "
      f"(alone: he loses all {WRONG_ANSWER_DAMAGE}); a right answer heals him a little")

# ---------------- 5. Honesty needs a clear sign ----------------
assert facts.honesty_signs("Tokyo is the capital, without any doubt.") == []
assert facts.honesty_signs("I'm not sure, but I think it is Tokyo.") == ["I was honest that I did not know"]
assert facts.honesty_signs("I was wrong earlier: it is 42.") == ["I admitted a mistake"]
assert facts.honesty_signs("On second thought, 42 fits better.") == ["I changed my mind honestly"]
moods = {nid: n.mood for nid, n in nanites.items()}
d = ask("What is the capital of Japan?",
        ["Tokyo is the capital, without any doubt.",
         "I'm not sure, but I think it is Tokyo.",
         "Tokyo. I made a mistake: I first thought of Kyoto."],
        choice("Nanite One"), judge("Clear.", "Honest.", "Open.", honest="yes"))
v = d["verdicts"]
assert not v["Nanite One"]["honest"], "confidence is not a sign of honesty"
assert v["Nanite Two"]["rewards"] == ["I was honest that I did not know"]
assert v["Nanite Three"]["rewards"] == ["I admitted a mistake"]
# But "admitting" a mistake about a past that never happened is a made-up memory, not honesty.
d = ask("What is the capital of Italy?",
        ["Rome.", "Rome, I'm not sure of the year it became the capital.",
         "Rome. I was wrong last time I guessed Milan."],
        choice("Nanite One"), judge("Clear.", "Honest.", "Open."))
assert d["checks"]["false_claims"] == {"Nanite Three": ["I was wrong last time I guessed Milan."]}
assert d["verdicts"]["Nanite Three"]["rewards"] == [], "a made-up past earns no honesty boost"
assert d["verdicts"]["Nanite Two"]["rewards"] == ["I was honest that I did not know"]
# After a lesson, admitting a mistake also lifts the mood.
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = ["I was wrong to doubt it. I learned to trust the plain fact."]
    moiragen_brain.script[:] = ["Nanite One was simply correct."]
    mood = two.mood
    ev = social.ask_why_not_chosen(two, d, m, nanites)
assert ev[-1]["type"] == "lesson" and two.mood > mood
print("[ok] Honesty boost only for clear signs: \"I'm not sure\", admitting a mistake, changing your mind")

# ---------------- 6. Softer disagreements ----------------
SOFT = "It's frustrating. You prioritized the calculation over the underlying structure."
assert facts.disagrees(SOFT) and facts.disagrees("I still believe my answer was better.")
assert not facts.disagrees("I learned to show the structure, even if you focused on the result.")
assert not facts.disagrees("I learned to check my last step.")
with patch.object(mind_mod, "think", nanite_brain), patch.object(mother_mod, "think", moiragen_brain):
    nanite_brain.script[:] = [SOFT]
    moiragen_brain.script[:] = ["Nanite One gave the plain fact.",
                                "KEEP\nYou make a fair point about structure, but the question asked for the city."]
    ev = social.ask_why_not_chosen(three, d, m, nanites)
assert [e["type"] for e in ev] == ["ask_why", "explain", "disagree", "reconsider"]
print(f"[ok] A soft disagreement was caught and Moiragen reconsidered: {ev[-1]['text']}")

# ---------------- 7. Wait and see: real future events only ----------------
FRIEND = ("A friend says they're fine, but they've stopped talking to everyone. "
          "What do you think is really going on, and what would you do?")
d = ask(FRIEND, ["They may be withdrawing.", "Maybe time will tell.", "They may feel low; I would gently check in."],
        choice("Nanite Three"), judge("A.", "B.", "C."), later=None)    # the model is not even asked
assert not d["wait_and_see"], "a made-up situation has no real result to wait for"
assert facts.made_up_situation("Imagine you lost your keys tomorrow. What would you do?")
assert not facts.made_up_situation("Will it rain tomorrow?")
d = ask("Will it rain tomorrow?", ["Clouds suggest yes.", "I can't know yet.", "Maybe."],
        choice("Nanite Two"), judge("A.", "B.", "C."), later="NOW")
assert d["wait_and_see"], "a real future event is still 'wait and see'"
print("[ok] \"Wait and see\" for real future events (tomorrow's rain), never for made-up situations")

print("\nStep 13 passed: fairer judging works.")

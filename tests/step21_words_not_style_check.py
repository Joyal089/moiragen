"""Step 21 check (v2.0): judge by words, not style; guess, then check.

  1. Moiragen judges each answer by what it actually says, not by the nanite's usual
     style. Style talk aimed at a nanite ("you tend to get so wonderfully lost in...",
     "detached, almost clinical", "your usual...") is shown back to him with its own
     note and rewritten; his explanations get no style notes at all; and every prompt
     that reminds him to value all ways of seeing now says "judge by what it says".
  2. His pattern: he first GUESSES in his own words (no numbers), then Python shows
     him the real numbers (last 10 choices and all of them), and he says briefly
     whether his guess was right ("I thought I favoured Three, but it was actually Two.").

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step21_words_not_style_check.py
"""

import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import mind as mind_mod, mother as mother_mod, social
from moiragen.journal import render
from moiragen.memory_log import read_events
from moiragen.mother import PUSHY, STYLE_NOTE, VALUE_ALL_WAYS, Moiragen
from moiragen.nanite import load_all

mother_mod.ASK_WHY_CHANCE = 0
mother_mod.LEARNING = False

# ---------------- 1a. The rule, on the session's real lines ----------------
for style in ["However, you tend to get so wonderfully lost in considering the flow of events.",
              "In this particular instance, your measured approach felt... detached, almost clinical.",
              "Your usual focus on patterns showed again.", "As usual, you looked at feelings.",
              "You always bring the numbers."]:
    assert PUSHY.search(style), style
for fine in ["I tend to lean toward feelings myself.", "You thought about how your friend would feel.",
             "You noticed the clouds gather before rain."]:
    assert PUSHY.search(fine) is None, fine
assert "Judge each answer only by what it actually says, never by a nanite's usual style" in VALUE_ALL_WAYS
print("[ok] \"you tend to...\", \"detached\", \"clinical\", \"your usual...\" are caught; "
      "his own \"I tend to\" and fair words about the answer are not")


class Brain:
    def __init__(self):
        self.calls, self.want, self.guess, self.check, self.explain = [], "", "", "", ""

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        user, system = messages[-1]["content"], system or ""
        self.calls.append({"system": system, "user": user})
        if "Reply ONLY with JSON" in system:
            pick = re.search(rf"(Answer [A-H]) suggests:\n{re.escape(self.want)}", user).group(1)
            reply = '{"compare": "c", "chosen": "%s", "reason": "It is clear.", "answer": "a"}' % pick
        elif "Before you see any numbers" in user:
            reply = self.guess
        elif "was your guess right" in user:
            reply = self.check
        elif "Write one line for each" in user:
            labels = re.findall(r"(Answer [A-H]) said:", user)
            reply = "\n".join(f"{l} | honest: no | good question: no | why: Your answer was clear." for l in labels)
        elif "You sort answers" in system:
            reply = "NOW"
        elif "asks: why did you choose" in user:
            reply = self.explain
        elif "Rewrite it once" in user:
            reply = "Your answer described the flow of events, and this time the other one was more direct."
        else:
            raise AssertionError(f"unexpected prompt: {user[:200]}")
        return {"text": reply, "seconds": 0.01, "waited": 0}


class Says:
    def __init__(self, lines):
        self.lines = list(lines)

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        return {"text": self.lines.pop(0), "seconds": 0.01, "waited": 0}


nanites = load_all()
by_name = {n.name: n for n in nanites.values()}
m = Moiragen.load()
brain = Brain()


def ask(question, said, want, guess, check):
    brain.want, brain.guess, brain.check, brain.calls[:] = want, guess, check, []
    with patch.object(mind_mod, "think", Says(said)), patch.object(mother_mod, "think", brain):
        return m.decide(question, nanites)


# ---------------- 2. Guess, then check ----------------
WRONG = ("I think I favour Nanite Three lately, because I lean toward feelings.",
         "I thought I favoured Nanite Three, but it was actually Nanite Two.")
d1 = ask("What is a river?", ["Water that flows downhill.", "A river changes its course over years.",
                              "A river sounds calm to me."], "A river changes", *WRONG)
guess_call = next(c for c in brain.calls if "Before you see any numbers" in c["user"])
check_call = next(c for c in brain.calls if "was your guess right" in c["user"])
assert not re.search(r"\d", guess_call["user"].split("\n\n", 1)[1]), "no numbers before he guesses"
assert "counted by Python (these are exact)" in check_call["user"]
assert "your guess named Nanite Three; the one you chose most lately is Nanite Two" in check_call["user"]
assert d1["pattern"].startswith("My guess: I think I favour Nanite Three lately")
assert "The real numbers: Your last 1 choices: Nanite Two 1." in d1["pattern"]
assert d1["pattern"].endswith("I thought I favoured Nanite Three, but it was actually Nanite Two.")
note = next(x for x in reversed(m.memories) if x["kind"] == "pattern")
assert note["guess_right"] is False and note["real_recent"] == {"Nanite Two": 1}
assert "*Moiragen looks at his own pattern:* My guess:" in render(list(read_events(kind="decision_full", last=1))[0])
print(f"[ok] Wrong guess: \"{d1['pattern'][-66:]}\"")

RIGHT = ("I think I have been choosing Nanite Two most.", "I was right: it was Nanite Two most often lately.")
d2 = ask("What is a lake?", ["Still water in a hollow.", "A lake fills and drains with seasons.",
                             "A lake feels like a held breath."], "A lake fills", *RIGHT)
note = next(x for x in reversed(m.memories) if x["kind"] == "pattern")
assert note["guess_right"] is True and note["real_recent"] == {"Nanite Two": 2}
assert "Your last 2 choices: Nanite Two 2." in d2["pattern"]
print("[ok] Right guess: Python agrees, and the real numbers (last 10, and all) are shown to him")

# ---------------- 1b. Explaining a choice: by the words, never by style ----------------
loser = next(s for s in d2["suggestions"] if s["nanite"] != d2["chosen"])
brain.explain = ("You tend to get so wonderfully lost in considering the flow of events. "
                 "The chosen answer named the seasons directly.")
brain.calls[:] = []
with patch.object(mind_mod, "think", Says(["I see. Thank you for explaining."])), \
        patch.object(mother_mod, "think", brain):
    social.ask_why_not_chosen(by_name[loser["nanite"]], d2, m, nanites)
explain_call = next(c for c in brain.calls if "asks: why did you choose" in c["user"])
assert "tends to see things in its own way" not in explain_call["system"], "no style notes in his explanation"
assert "never by a nanite's usual style" in explain_call["system"]
rewrite_call = next(c for c in brain.calls if "Rewrite it once" in c["user"])
assert STYLE_NOTE in rewrite_call["user"] and "\"you tend to\"" in rewrite_call["user"].lower()
said = next(x for x in reversed(m.memories) if x["kind"] == "explained")["text"]
assert "tend to" not in said and "described the flow of events" in said, said
fair = list(read_events(kind="fairer_words", last=1))[0]
assert fair["to"] == loser["nanite"] and fair["phrase"].lower() == "you tend to"
print("[ok] Explaining a choice: no style notes, and \"You tend to get so wonderfully lost...\" is shown back "
      "with its own note and rewritten about the answer's words")

print("\nStep 21 passed: he judges by words, not style, and checks his own pattern against the real numbers.")

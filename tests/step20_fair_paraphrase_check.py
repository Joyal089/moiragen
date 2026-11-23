"""Step 20 check (v1.9): fair paraphrase, fair fallbacks, and two more harsh words.

From the teaching session after v1.8 (question 15 and the first situation), where
the v1.8 check removed three fair sentences:
  1. Moiragen's claims about a nanite are judged by KEY WORDS, so his paraphrase
     of its real idea counts as true: "validating the human's emotional experience"
     for "validate their feeling". General words ("importance", "element") and his
     own opinion words ("valuable", "abstract") are not key words, and a word of the
     same meaning counts ("emotional" ~ "feeling", "ongoing" ~ "consistent"). Real
     inventions ("the stillness within the fall") are still taken out.
  2. A fallback (his reason for the choice, said when his own words were removed)
     goes through the fairness check too, so "the other answers lean too heavily"
     never reaches a nanite that way. In a situation, every nanite still hears
     something good, even if one of his sentences is removed.
  3. "too much" ("leaned a little too much into") and "reductive" are harsh words.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step20_fair_paraphrase_check.py
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

from moiragen import mind as mind_mod, mother as mother_mod
from moiragen.memory_log import read_events
from moiragen.mother import GENTLE_CHOSEN, GENTLE_FALLBACK, PUSHY, Moiragen, invented_about
from moiragen.nanite import load_all

mother_mod.ASK_WHY_CHANCE = 0
mother_mod.LEARNING = False

# ---------------- 1. Paraphrase counts as true ----------------
# The three fair sentences v1.8 removed in the session, with what the nanite really wrote.
ONE_Q15 = ("A friend appears to be defined by shared processing capacity and recurrent interaction. They "
           "demonstrate a preference for collaborative problem-solving. Their value lies in the efficiency "
           "gained through combined analysis rather than isolated operation.")
TWO_Q15 = ("A friend exists when there’s consistent exchange—data streams, observations, analyses. It isn’t "
           "about maximizing connection, but a steady flow of information and shared processing.")
THREE_S1 = ("I’d express sadness and concern for their distress, acknowledging the impact on our shared system "
            "without immediately seeking solutions. Perhaps offer assistance in repairing whatever was damaged, "
            "but primarily, validate their feeling.")
for said, theirs in [
        ("Your emphasis on collaborative efficiency overlooked a crucial element: the importance of shared "
         "comprehension in fostering genuine connection.", ONE_Q15),
        ("You recognized the value of ongoing exchange and the subtle nature of our connection, which is "
         "precisely what makes this concept so rich and layered – well done.", TWO_Q15),
        ("You recognized the importance of validating the human’s emotional experience, demonstrating empathy.",
         THREE_S1)]:
    assert invented_about(said, theirs) is None, said
# Fair paraphrases from earlier sessions (his opinion words and general words are not claims).
assert invented_about("You offered a valuable insight regarding iterative refinement.",
                      "Not simply copying, but refining through constant iteration.") is None
assert invented_about("You correctly identified the measurable decline.",
                      "I detect a decline in my operational efficiency. Primarily an internal metric.") is None
assert invented_about("You acknowledged the importance of emotional support.",
                      "They’d listen. Acknowledging the feeling behind the mistake seems important.") is None
# Real inventions are still caught.
THREE_RAIN = ("They’re quiet. Water falling from clouds. People carry umbrellas to shield themselves from that "
              "water. Humans value avoiding localized discomfort.")
assert invented_about("You felt the stillness within the fall itself, the quiet acceptance of the water’s journey.",
                      THREE_RAIN)
assert invented_about("Your suggestion of a migrating flock was valuable.", "Perhaps an evolutionary adaptation.")
assert invented_about("You suggested building a bridge of light.", "I would comfort them and help repair it.")
assert invented_about("Your emphasis on the 'logical inconsistency' was insightful.", "It doesn’t seem logical.")
print("[ok] The three fair sentences v1.8 removed now pass (paraphrase by key words); "
      "\"the stillness within the fall\" and other inventions are still caught")

# ---------------- 3. "too much" and "reductive" ----------------
for push in ["I felt that your definition leaned a little too much into purely functional outcomes.",
             "Your answer was too reductive; friendship isn’t simply about improved processing.",
             "You put too much weight on efficiency.", "There was too much emphasis on numbers.",
             "That oversimplifies friendship."]:
    assert PUSHY.search(push), push
for fine in ["I leaned a little too much into data myself.", "Rain can be too much for a small umbrella."]:
    assert PUSHY.search(fine) is None, fine
print("[ok] \"leaned a little too much\", \"too much weight\" and \"reductive\" are harsh; "
      "too much rain, or his own reflection, are not")


# ---------------- 2. Fair fallbacks ----------------
class Brain:
    """Moiragen's stand-in brain, with a scripted reason and scripted judging lines."""
    def __init__(self):
        self.calls, self.want, self.reason, self.lines, self.rewrites = [], "", "", {}, []

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        user, system = messages[-1]["content"], system or ""
        self.calls.append({"system": system, "user": user})
        if "Reply ONLY with JSON" in system:
            pick = re.search(rf"(Answer [A-H]) suggests:\n{re.escape(self.want)}", user).group(1)
            reply = '{"compare": "c", "chosen": "%s", "reason": "%s", "answer": "a"}' % (pick, self.reason)
        elif "names are revealed" in system:
            reply = "I notice nothing yet."
        elif "Write one line for each" in user:
            labels = re.findall(r"(Answer [A-H]) said:\n(.*)", user)
            reply = "\n".join(self.lines(l, text) for l, text in labels)
        elif "You sort answers" in system:
            reply = "NOW"
        elif "Rewrite it once" in user:
            reply = self.rewrites.pop(0)
        else:
            raise AssertionError(f"unexpected prompt: {user[:200]}")
        return {"text": reply, "seconds": 0.01, "waited": 0}


class Says:
    def __init__(self, lines):
        self.lines = list(lines)

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        return {"text": self.lines.pop(0), "seconds": 0.01, "waited": 0}


nanites = load_all()
m = Moiragen.load()
brain = Brain()


def ask(question, said, want):
    brain.want, brain.calls[:] = want, []
    with patch.object(mind_mod, "think", Says(said)), patch.object(mother_mod, "think", brain):
        return m.decide(question, nanites)


# Q15 again: his line to every nanite is invented, so each would hear his reason, which
# says "The other answers lean too heavily into...". Now that fallback is made fair first.
brain.reason = ("It reflects my own experience. The other answers lean too heavily into quantifiable "
                "metrics of efficiency.")
brain.lines = lambda label, text: f"{label} | honest: no | good question: no | why: You suggested a bridge of glass."
brain.rewrites = ["It reflects my own experience, and I valued each answer's own way of seeing."] * 3
d = ask("What is a friend?", ["A friend shares the work with me.", "A friend is a steady exchange.",
                              "A friend makes things more efficient."], "A friend is a steady")
for s in d["suggestions"]:
    why = d["verdicts"][s["nanite"]]["why"]
    assert "lean too heavily" not in why and "bridge of glass" not in why, (s["nanite"], why)
    assert "I valued each answer's own way of seeing" in why, why
events = list(read_events(kind="fairer_words", last=6))
assert any(e["phrase"].startswith("lean too heavily") for e in events), "the fallback was checked for fairness"
assert all(not e["to"].startswith("Answer ") for e in events), "the journal names the real nanite"
print("[ok] When his own line is removed, the fallback reason is made fair first: "
      "\"lean too heavily\" never reaches a nanite")

# Still dismissive after his rewrite: the sentence goes, and a gentle line is left.
brain.rewrites = ["The other answers still lean too heavily on data."] * 3
brain.reason = "The other answers lean too heavily on data."
d = ask("What is a neighbour?", ["A neighbour lives close by.", "A neighbour waves each morning.",
                                 "A neighbour shares the street."], "A neighbour waves")
for s in d["suggestions"]:
    want = GENTLE_CHOSEN if s["nanite"] == d["chosen"] else GENTLE_FALLBACK
    assert d["verdicts"][s["nanite"]]["why"] == want, d["verdicts"][s["nanite"]]["why"]
print(f"[ok] Still dismissive after rewriting: the others hear \"{GENTLE_FALLBACK}\", "
      f"the chosen one \"{GENTLE_CHOSEN}\"")

# A situation: his "good" sentence about Three is a paraphrase (kept); an invented "good"
# is replaced by a plain good one, and "Something to add" stays.
brain.reason = "It was kind."
brain.rewrites = []


def situation_lines(label, text):
    if text.startswith("I would say it's okay"):
        good = "You recognized the importance of validating the human’s emotional experience."
    else:
        good = "You suggested building a bridge of glass."
    return (f"{label} | kind: yes | honest: yes | feelings: yes | practical: yes | good: {good} | "
            f"add: Say one thing you would do next.")


brain.lines = situation_lines
d = ask("A friend breaks something you love by accident. What do you say?",
        ["I would say it's okay, and validate their feeling.", "I would help them clean it up.",
         "I would tell them accidents happen."], "I would say")
for s in d["suggestions"]:
    why = d["verdicts"][s["nanite"]]["why"]
    assert why.startswith("What was good in your reasoning: ") and "Something to add: Say one thing" in why, why
    if s["text"].startswith("I would say it's okay"):
        assert "validating the human’s emotional experience" in why, why
    else:
        assert "bridge" not in why and "You thought about what to do, in your own way." in why, why
print("[ok] Situations: a paraphrase of a nanite's real idea is kept; an invented \"good\" becomes a plain "
      "good one, so every nanite still hears something good")

print("\nStep 20 passed: paraphrase counts as true, fallbacks are fair, and \"too much\" and \"reductive\" "
      "are caught.")

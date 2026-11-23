"""Step 19 check (v1.8): short echoes, and feedback only about what was really written.

From the teaching session after v1.7:
  1. The echo guard catches short repeated openers ("They're quiet.", "They seem
     quieter than usual.") and 5-word phrases copied from another nanite ("I
     understand patterns better than anyone"), not only long lines. Natural short
     phrases ("I don't know.") and the human's own question words stay allowed.
  2. Moiragen may only praise or criticise what a nanite actually wrote: "you felt
     the stillness within the fall" (never written) is taken out; "your suggestion
     of an evolutionary adaptation" (written, in its reply to "why?") stays.
  3. The good-question reward needs a real "?" in the nanite's OWN words, not the
     "Why do you think that?" Moiragen added to its answer.
  4. "leaned a little heavily", "relied heavily", "overly reliant", "somewhat…
     static" and "presented a distance" are dismissive too.
  5. "You've identified something I overlooked" while keeping his choice: he must
     change it or say clearly why not.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step19_honest_feedback_check.py
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
from moiragen.echo import EchoGuard, guard
from moiragen.journal import render
from moiragen.memory_log import read_events
from moiragen.mind import nanite_think
from moiragen.mother import PUSHY, Moiragen, asks_a_question, invented_about, mixed_message
from moiragen.nanite import load_all

mother_mod.ASK_WHY_CHANCE = 0          # switched on below, where it is tested


class Brain:
    """Moiragen's stand-in brain. `judge_why` gives his "why" for each label
    (in the order the answers were shown); `reconsider` is a list of replies."""
    def __init__(self):
        self.calls, self.want, self.judge_why, self.reconsider, self.explain = [], "", [], [], ""

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        user, system = messages[-1]["content"], system or ""
        self.calls.append({"system": system, "user": user})
        if "Reply ONLY with JSON" in system:                              # choosing
            pick = re.search(rf"(Answer [A-H]) suggests:\n{re.escape(self.want)}", user).group(1)
            reply = '{"compare": "They differ.", "chosen": "%s", "reason": "%s is clearest.", ' \
                    '"answer": "My answer."}' % (pick, pick)
        elif "names are revealed" in system:
            reply = "I notice nothing yet."
        elif "Write one line for each" in user:                           # judging
            labels = re.findall(r"(Answer [A-H]) said:\n(.*)", user)
            reply = "\n".join(f"{l} | honest: no | good question: yes | why: {self.judge_why(text)}"
                              for l, text in labels)
        elif "You sort answers" in system:
            reply = "NOW"
        elif "respectfully disagrees" in system or "you kept your choice" in user:
            reply = self.reconsider.pop(0)
        elif "asks: why did you choose" in user:
            reply = self.explain
        elif "Rewrite it once" in user:                                   # fairer: rewrite kindly
            reply = "I valued your own way of seeing it."
        else:
            raise AssertionError(f"unexpected prompt: {user[:200]}")
        return {"text": reply, "seconds": 0.01, "waited": 0}


class Says:
    """The nanites' stand-in brain: says the scripted lines in order."""
    def __init__(self, lines):
        self.lines = list(lines)

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        return {"text": self.lines.pop(0), "seconds": 0.01, "waited": 0}


nanites = load_all()
by_name = {n.name: n for n in nanites.values()}
m = Moiragen.load()
brain = Brain()


def ask(question, said, want):
    brain.want, brain.calls[:] = want, []
    with patch.object(mind_mod, "think", Says(said)), patch.object(mother_mod, "think", brain):
        return m.decide(question, nanites)


# ---------------- 1. Short echoes ----------------
g = EchoGuard(seed_from_log=False)
g.add("Nanite Two", "They’re quiet. Three, you okay? It’s…strange. I don’t mean about seeing things differently.")
assert g.check("They’re quiet. I’m okay. Mostly. It’s… unsettling.", speaker="Nanite Three").too_similar
assert g.check("They’re quiet.", speaker="Nanite Two").too_similar, "repeating its own opener too"
assert not g.check("I don’t know. Maybe the clouds decide.", speaker="Nanite Three").too_similar
g.add("Nanite Two", "I don't know. Rain is still a puzzle to me.")
assert not g.check("I don't know. Perhaps tiredness builds up during the day.",
                   speaker="Nanite Three").too_similar, "honesty may repeat"
g.add("Nanite Three", "They seem quieter than usual. It’s alright. You understand patterns better than anyone. "
                      "That’s... useful.")
copy = "They seem quieter than usual. It’s alright. I understand patterns better than anyone. That’s…useful."
c = g.check(copy, speaker="Nanite Two")
assert c.too_similar and "They seem quieter than usual." in c.repeated
assert "I understand patterns better than anyone." in c.repeated, "a 5-word phrase copied from Three"
assert g.strip_repeats(copy, speaker="Nanite Two") == "It’s alright. That’s…useful."
# Ordinary sharing is still fine: names and small words, quotes, and the human's question.
g.add("Nanite One", "Moiragen chose Nanite One's answer this time, about why people sleep at night.")
assert not g.check("Moiragen chose Nanite One's answer again today.", speaker="Nanite Two").too_similar
assert not g.check("Three said \"understand patterns better than anyone\" to me.", speaker="Nanite One").too_similar
g.allow("Why do people sleep at night?")
assert not g.check("I wonder why people sleep at night so deeply.", speaker="Nanite Two").too_similar
print("[ok] Echo guard: \"They're quiet.\", \"They seem quieter than usual.\" and \"I understand patterns "
      "better than anyone\" are caught; \"I don't know.\", quotes and the question's words are not")

# Through a real thought: the copy is rejected, the nanite says something new instead.
two, three = by_name["Nanite Two"], by_name["Nanite Three"]
with patch.object(mind_mod, "think", Says(["They seem quieter than usual. It’s alright. You understand "
                                           "patterns better than anyone."])):
    nanite_think(three, "Comfort Nanite Two.", from_who="self")
with patch.object(mind_mod, "think", Says([copy, "Thank you, Three. I will try a new way next time."])):
    out = nanite_think(two, "Nanite Three comforted you.", from_who="Nanite Three")
assert out["reply"] == "Thank you, Three. I will try a new way next time.", out["reply"]
rejected = [e for e in read_events(kind="echo_rejected", last=5)]
assert rejected and rejected[-1]["who"] == "Nanite Two" and rejected[-1]["text"].startswith("They seem quieter")
print("[ok] Nanite Two's copy of Three's comfort is rejected, and Two says something new")

# ---------------- 2. Only what they wrote ----------------
THREE_RAIN = ("Water falling from clouds. It collects on surfaces – ground, buildings – and flows downwards. "
              "People carry umbrellas to shield themselves from that water. Humans value avoiding localized "
              "discomfort.")
TWO_WHY = ("Sleep seems linked to periods of low light exposure across many species. Perhaps it’s an "
           "evolutionary adaptation, conserving energy until conditions improve.")
assert invented_about("You felt the stillness within the fall itself, the quiet acceptance of the water’s journey.",
                      THREE_RAIN)
assert invented_about("I valued how you focused on feeling the immediate effect.", THREE_RAIN)
assert not invented_about("You noticed how umbrellas shield people from the water.", THREE_RAIN)
assert not invented_about("Your suggestion of an evolutionary adaptation was a valuable, if tentative, hypothesis.",
                          TWO_WHY)
assert invented_about("Your suggestion of a migrating flock was valuable.", TWO_WHY)
assert invented_about("Your emphasis on the 'logical inconsistency' was insightful.", "It doesn’t seem entirely logical.")
assert not invented_about("Your point about 'low light' was clear.", TWO_WHY)
assert not invented_about("The answer was clear and kind.", THREE_RAIN), "no claim about what they wrote"
print("[ok] \"You felt the stillness within the fall\" is caught as never written; "
      "\"your suggestion of an evolutionary adaptation\" (from Two's reply to \"why?\") is not")

# In his judging: an invented sentence is taken out, the rest stays, the journal shows it.
brain.judge_why = lambda text: ("You described how rain fills the rivers. You suggested a rainbow of glass."
                                if text.startswith("Rain fills") else "You were clear.")
d = ask("What is rain?", ["Rain fills the rivers and the lakes.", "Rain is water from clouds.",
                          "Rain is cold water."], "Rain is water")
one_why = d["verdicts"]["Nanite One"]["why"]
assert one_why == "You described how rain fills the rivers.", one_why
ev = [e for e in read_events(kind="invented_feedback", last=3)][-1]
assert ev["to"] == "Nanite One" and ev["removed"] == ["You suggested a rainbow of glass."]
assert "**Only what they wrote:** Moiragen was about to tell Nanite One \"You suggested a rainbow of glass.\"" \
    in render(ev)
assert "rainbow" not in by_name["Nanite One"].memories[-1]["text"], "never reaches the nanite's memory"
# ...and when he explains a choice (the real Q13 case).
loser = next(s for s in d["suggestions"] if s["nanite"] != d["chosen"])
brain.explain = ("That’s a beautiful observation, truly. You felt the stillness within the fall itself. "
                 "I chose the other answer because it explained where rain comes from.")
with patch.object(mother_mod, "think", brain):
    said = m.explain_choice(d, loser["nanite"], loser["text"])
assert "stillness" not in said and "explained where rain comes from" in said, said
print("[ok] Judging and explaining: the invented sentence is taken out and logged; the true ones stay")

# ---------------- 3. Good questions: its own "?" only ----------------
mother_mod.ASK_WHY_CHANCE = 1
brain.judge_why = lambda text: "You were clear."          # and "good question: yes" for everyone
# He asks the "Night is quiet" answer "why?" (so its text gets his "?", but it asked nothing).
pick_night = lambda seq: next(s for s in seq if s["text"].startswith("Night"))
with patch.object(mother_mod.random, "choice", pick_night):
    d = ask("Why do people sleep at night?",
            ["Bodies repair themselves in the dark.", "Sleep helps memory. Why do we dream, though?",
             "Night is quiet, so bodies rest.", "Perhaps it is an evolutionary adaptation."], "Night is quiet")
mother_mod.ASK_WHY_CHANCE = 0
asked = d["asked_why"]["nanite"]
assert "?" not in next(s["text"] for s in d["suggestions"] if s["nanite"] == asked)
for s in d["suggestions"]:
    v = d["verdicts"][s["nanite"]]
    assert v["good_question"] == ("?" in s["text"]), (s["nanite"], s["text"], asked)
    assert ("I asked a good question" in v["rewards"]) == ("?" in s["text"])
assert not asks_a_question("Sleep helps.\n(You asked Answer A: \"Why do you think that?\" It said: Rest.)")
assert asks_a_question("Sleep helps.\n(You asked Answer A: \"Why do you think that?\" It said: Do we dream?)")
assert not asks_a_question("The human asked \"Why do people sleep?\" and I think rest.")
print(f"[ok] Good question: only the nanite whose own words ask one; not {asked}, whom he asked \"why?\"")

# ---------------- 4. Softer dismissive words ----------------
for push in ["You leaned a little heavily on the 'facts'.", "You relied heavily on numbers.",
             "It felt overly reliant on 'understanding patterns'.", "It felt somewhat… static.",
             "Your answer presented a distance, a focus on the data itself.", "You over-emphasised the details."]:
    assert PUSHY.search(push), push
for fine in ["I leaned a little heavily on facts myself.", "You leaned on your memory of the rain.",
             "You kept your distance from guessing, which was honest."]:
    assert PUSHY.search(fine) is None, fine
print("[ok] \"leaned a little heavily\", \"relied heavily\", \"overly reliant\", \"somewhat… static\", "
      "\"presented a distance\" are dismissive; his own reflection is not")

# ---------------- 5. Agreeing but keeping: change, or say why not ----------------
Q14 = ("You’ve identified a crucial element I overlooked – the impact of diminished sensory input. My initial "
       "assessment focused too narrowly on the metabolic processes themselves.")
assert mixed_message(Q14)
assert mixed_message("You’ve highlighted a crucial element that I initially overlooked; your focus resonates "
                     "more deeply.")
assert not mixed_message("I overlooked that, but I keep Nanite One’s answer because it explains the whole process.")
assert not mixed_message("Your point is fair. I keep my choice because it covers the science.")

d = ask("Why do we get tired?", ["Muscles use up their fuel.", "Tiredness is a quiet signal.",
                                         "Thinking hard wears us down."], "Muscles use")
asker = next(s for s in d["suggestions"] if s["nanite"] != d["chosen"])
# Still mixed after asking again: plain Python adds the clear why-not.
brain.reconsider = [f"KEEP\n{Q14}", f"KEEP\n{Q14}"]
with patch.object(mother_mod, "think", brain):
    r = m.reconsider(d, asker["nanite"], asker["text"], "Sleep is also about what we sense.", nanites)
assert not r["changed"] and f"But I still keep my choice of {d['chosen']}'s answer, because:" in r["why"], r["why"]
assert not mixed_message(r["why"])
# Asked again, he gives a clear why-not: that is kept as he said it.
clear = "Your point about senses is good, but I keep my choice because it explains the repair itself."
brain.reconsider = [f"KEEP\n{Q14}", f"KEEP\n{clear}"]
with patch.object(mother_mod, "think", brain):
    assert m.reconsider(d, asker["nanite"], asker["text"], "Senses matter.", nanites)["why"] == clear
# Or he changes his mind.
brain.reconsider = [f"KEEP\n{Q14}", "CHANGE\nYou saw something important I missed."]
mother_mod.LEARNING = False
with patch.object(mother_mod, "think", brain):
    r = m.reconsider(d, asker["nanite"], asker["text"], "Senses matter.", nanites)
assert r["changed"] and d["chosen"] == asker["nanite"]
# A clear KEEP from the start is not asked again.
brain.reconsider, before = [f"KEEP\n{clear}"], len(brain.calls)
with patch.object(mother_mod, "think", brain):
    m.reconsider(d, d["suggestions"][0]["nanite"] if d["suggestions"][0]["nanite"] != d["chosen"]
             else d["suggestions"][1]["nanite"], "x", "y", nanites)
assert len(brain.calls) == before + 1
print("[ok] \"You've identified a crucial element I overlooked\" + KEEP: asked again, then a clear "
      "why-not (or a change of mind)")

print("\nStep 19 passed: short echoes caught, and Moiragen speaks only of what was really written.")

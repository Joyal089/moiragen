"""Step 18 check (v1.7): fairer words, gentle sleep, and Moiragen learns from his nanites.

FIXES
  1. Reflecting on his OWN bias ("My first assessment focused on the measurable...")
     is never flagged; pushing a nanite toward measuring still is.
  2. Basic feelings ("sad", "lonely") are never "wait and see".
  3. Harsh phrases: "leans too heavily", "lacked feeling", "felt distant".
  4. Falling asleep and waking come with: "Sleep is rest. You always wake up with
     your memories safe."
  5. Nobody is pushed to sound happy: neutral, tired or unsure is fine.
MOIRAGEN LEARNS FROM THE NANITES
  6. When his choice was wrong and another nanite was right (calculator, a
     disagreement that changed his mind, or the human naming who was right), he
     writes what that nanite saw that he missed.
  7. Sometimes he asks one answer "why do you think that?" before choosing (still blind).
  8. A "what I learned from each nanite" list, kept in his memory.
  9. He knows: "I am made of my nanites, and I learn from them. I am not all-knowing."
 10. A nanite explains something to him, and he says what was new to him.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step18_learning_check.py
"""

import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import facts, mind as mind_mod, mother as mother_mod
from moiragen.export import build_examples
from moiragen.journal import render
from moiragen.loop import SLEEP_IS_REST, Mind
from moiragen.memory_log import read_events
from moiragen.mind import FEELINGS_ARE_FINE, build_system_prompt
from moiragen.mother import MADE_OF_NANITES, PUSHY, Moiragen
from moiragen.nanite import load_all

assert mother_mod.BLIND_JUDGING and mother_mod.LEARNING, "both are on by default"
mother_mod.ASK_WHY_CHANCE = 0          # switched on below, where it is tested
NAMES = re.compile(r"Nanite (?:One|Two|Three)")


class FakeMoiragen:
    """Answers each kind of prompt the way the model would, and keeps every call."""
    def __init__(self):
        self.calls, self.want, self.lesson = [], "", ""

    def label_of(self, text, start):
        return re.search(rf"(Answer [A-H]) (?:suggests|said):\n{re.escape(start)}", text).group(1)

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        user, system = messages[-1]["content"], system or ""
        self.calls.append({"system": system, "user": user})
        if "Reply ONLY with JSON" in system:                              # choosing
            pick = self.label_of(user, self.want)
            reply = '{"compare": "They differ.", "chosen": "%s", "reason": "%s is clearest.", ' \
                    '"answer": "My answer."}' % (pick, pick)
        elif "names are revealed" in system:                              # his own pattern
            reply = "I notice nothing yet."
        elif "For each of the others" in user:                            # the streak note
            others = re.findall(r"Answer [A-H]", user.split("For each of the others")[1])
            reply = "\n".join(f"{o}: It was kind, but less clear this time." for o in dict.fromkeys(others))
        elif "Write one line for each" in user:                           # judging
            labels = re.findall(r"(Answer [A-H]) said:", user)
            reply = "\n".join(f"{l} | honest: no | good question: no | why: Your answer, {l}, was clear."
                              for l in labels)
        elif "You sort answers" in system:                                # wait and see?
            reply = "NOW"
        elif "saw something you missed" in system:                        # learn_from (fix 6)
            reply = self.lesson
        elif "respectfully disagrees" in system:                          # reconsider
            reply = "CHANGE\nYou saw the heart of the question more clearly than I did."
        elif "explained this to you" in user:                             # hear_explanation (fix 10)
            reply = "That rain is borrowed from the sea was new to me. I liked how simply you said it."
        else:
            raise AssertionError(f"unexpected prompt: {user[:200]}")
        return {"text": reply, "seconds": 0.01, "waited": 0}


class FakeNanites:
    def __init__(self, answers):
        self.answers = answers

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        return {"text": self.answers.pop(0), "seconds": 0.01, "waited": 0}


nanites = load_all()
by_name = {n.name: n for n in nanites.values()}
m = Moiragen.load()
brain = FakeMoiragen()


def ask(question, said, want):
    """Ask with scripted nanite answers (`said`); he first picks the answer starting `want`."""
    brain.want, brain.calls[:] = want, []
    with patch.object(mind_mod, "think", FakeNanites(list(said))), patch.object(mother_mod, "think", brain):
        return m.decide(question, nanites)


def with_brain(fn, *args, nanite_says=()):
    with patch.object(mind_mod, "think", FakeNanites(list(nanite_says))), patch.object(mother_mod, "think", brain):
        return fn(*args)


# ---------------- 1 and 3. Fairer words ----------------
ORIGINAL = ("You’ve articulated a crucial distinction, you. My initial assessment focused on the measurable – "
            "the efficient network, the resolved conflicts – and perhaps I was too rigidly applying my preferred "
            "framework of understanding, overlooking the inherent feeling associated with that process, as you so "
            "eloquently describe.")
for own in [ORIGINAL, "Perhaps I leaned too heavily on data.", "I think I lacked feeling in my own answer.",
            "My focus was on the measurable, and I missed the feeling you describe."]:
    assert PUSHY.search(own) is None, own
for push in ["Your answer leans too heavily on abstract ideas.", "It was technically precise but lacked feeling.",
             "It felt distant to me.", "Your words felt strangely cold.", "You missed the heart of the question.",
             "You could measure that feeling instead.", "I think your answer lacked feeling.",
             "You didn't explore the potential for a simple, measurable shift."]:
    assert PUSHY.search(push), push
print("[ok] His own self-reflection is never flagged; \"leans too heavily\", \"lacked feeling\", "
      "\"felt distant\" and pushing toward measuring are")

# ---------------- 2. Basic feelings: never wait and see ----------------
for q in ["What do you do when another nanite is sad?", "How do you feel when you are lonely?",
          "What makes you angry?"]:
    assert facts.about_wish_or_feeling(q), q
assert not facts.about_wish_or_feeling("Will it rain tomorrow?")
d_sad = ask("What do you do when another nanite is sad?",
            ["I sit beside them quietly.", "I ask what is weighing on them.", "I share a calm memory with them."],
            "I ask what")
assert not d_sad["wait_and_see"] and not any("You sort answers" in c["system"] for c in brain.calls)
print("[ok] \"sad\", \"lonely\", \"angry\" are feelings: never \"wait and see\"")

# ---------------- 5. Nobody has to sound happy ----------------
assert FEELINGS_ARE_FINE in build_system_prompt(by_name["Nanite One"])
assert FEELINGS_ARE_FINE in m.self_text()
assert "sound happy" in FEELINGS_ARE_FINE and "neutral, tired, sad or unsure is fine" in FEELINGS_ARE_FINE
print("[ok] The nanites and Moiragen hear: feeling neutral, tired, sad or unsure is fine")

# ---------------- 9. Made of his nanites ----------------
assert MADE_OF_NANITES == "I am made of my nanites, and I learn from them. I am not all-knowing."
assert MADE_OF_NANITES in brain.calls[0]["system"], "he knows it while choosing"
print("[ok] He knows: \"I am made of my nanites, and I learn from them. I am not all-knowing.\"")

# ---------------- 6a. The calculator showed another nanite was right ----------------
brain.lesson = "They checked the sum instead of trusting how it sounded."   # no prefix: it is added
d_calc = ask("What is 7 + 5?", ["7 + 5 is 13.", "It is 12.", "I'm not sure about sums."], "7 + 5 is 13.")
assert d_calc["first_choice"] == "Nanite One" and d_calc["chosen"] == "Nanite Two", d_calc["chosen"]
assert d_calc["lesson"] == "I learned from Nanite Two that they checked the sum instead of trusting how it sounded."
learn_call = next(c for c in brain.calls if "saw something you missed" in c["system"])
assert "You first trusted Nanite One's answer" in learn_call["user"] and "It is 12." in learn_call["user"]
assert m.learned_from["Nanite Two"][-1]["how"] == "calculator"
text = render([e for e in read_events(kind="decision_full", last=3)][-1])
assert "*Moiragen learned:* I learned from Nanite Two that they checked" in text
assert render([e for e in read_events(kind="learned_from", last=1)][0]) is None, "written inside the decision"
print(f"[ok] Calculator: he trusted Nanite One, Nanite Two was right -> \"{d_calc['lesson']}\"")

# ---------------- 6b. A disagreement changed his mind ----------------
d_lake = ask("What is a lake?", ["Still water resting in a hollow.", "A lake fills and drains with seasons.",
                                 "A lake feels like a held breath."], "Still water")
asker = next(s for s in d_lake["suggestions"] if s["nanite"] != d_lake["chosen"])
brain.lesson = f"I learned from {asker['nanite']} that a lake can hold a feeling, not only water."
r = with_brain(m.reconsider, d_lake, asker["nanite"], asker["text"], "A lake is also a feeling.", nanites)
assert r["changed"] and d_lake["lesson"] == brain.lesson
assert m.learned_from[asker["nanite"]][-1]["how"] == "disagreement"
event = [e for e in read_events(kind="learned_from", last=1)][0]
assert render(event).endswith(f"*Moiragen learned from {asker['nanite']}:* {brain.lesson}")
print(f"[ok] Disagreement: he changed his choice to {asker['nanite']} and wrote what they saw")

# ---------------- 6c. The human says who was right ----------------
d_sea = ask("What is a sea?", ["Salt water over most of the world.", "Seas rise and fall with the tides.",
                               "Standing by a sea makes me feel small."], "Salt water")
right = next(s["nanite"] for s in d_sea["suggestions"] if s["nanite"] != d_sea["chosen"])
try:
    m.feedback(d_sea["id"], "wrong", nanites, "Too narrow.", right_nanite="Nanite Nine")
    raise AssertionError("a nanite that did not answer cannot be the right one")
except ValueError:
    pass
brain.lesson = f"I learned from {right} that a sea is also how it moves."
msg = with_brain(m.feedback, d_sea["id"], "wrong", nanites, "A sea is defined by tides too.", False, right)
assert msg.endswith(brain.lesson) and d_sea["lesson"] == brain.lesson
assert by_name[right].memories[-1]["kind"] == "praised" and "mine was the right one" in by_name[right].memories[-1]["text"]
assert m.learned_from[right][-1]["how"] == "human"
print(f"[ok] The human said {right} was right: {right} is praised, and he writes what they saw")

# ---------------- 8. The "what I learned from each nanite" list ----------------
learned = m.self_text()
assert "What you have learned from your nanites:" in learned and "- Nanite Two: I learned from Nanite Two" in learned
again = Moiragen.load()                  # it is kept in his file
assert again.learned_from.keys() == m.learned_from.keys()
for _ in range(mother_mod.LEARNED_KEEP + 3):
    m.add_learned("Nanite One", "something", "test")
assert len(m.learned_from["Nanite One"]) == mother_mod.LEARNED_KEEP
print(f"[ok] His list of what he learned from each nanite is in his prompts and his file "
      f"(newest {mother_mod.LEARNED_KEEP} each)")

# ---------------- 7. He asks one answer "why do you think that?" (blind) ----------------
mother_mod.ASK_WHY_CHANCE = 1
said = ["Rain falls when clouds grow heavy.", "Rain is the sky letting go.", "Rain is water coming home."]
why = "Because Nanite One once told me clouds get tired."
d_rain = ask("What is rain?", said + [why], "Rain is the sky")
mother_mod.ASK_WHY_CHANCE = 0
aw = d_rain["asked_why"]
assert aw["reply"] == why and d_rain["blind"][aw["label"]] == aw["nanite"]
choose = next(c for c in brain.calls if "Reply ONLY with JSON" in c["system"])
assert (f"(You asked {aw['label']}: \"Why do you think that?\" It said: Because another nanite once told me "
        f"clouds get tired.)") in choose["user"]
assert not NAMES.search(choose["system"] + choose["user"]), "still blind, his learned list too"
assert [s["text"] for s in d_rain["suggestions"]] == said, "the stored answers keep their own words"
assert by_name[aw["nanite"]].memories[-2]["text"].startswith("Moiragen said: Moiragen read your answer")
tasks = sorted(x["task"] for x in build_examples() if x["decision_id"] == d_rain["id"] and x["task"] != "choose")
assert tasks == ["suggest", "suggest", "suggest", "why"], f"its reply is not a suggestion: {tasks}"
text = render([e for e in read_events(kind="decision_full", last=1)][0])
assert f"Moiragen asked {aw['label']} \"why do you think that?\" {aw['nanite']} said: {why}" in text
print(f"[ok] Before choosing he asked {aw['label']} \"why?\"; the reply was shown under its label "
      f"(names hidden), revealed afterwards as {aw['nanite']}")

# ---------------- 10. A nanite explains something to him ----------------
one = by_name["Nanite One"]
e = with_brain(m.hear_explanation, one, nanite_says=["Rain is water the sun lifted from the sea, falling back."])
assert e["type"] == "explain_to_moiragen" and e["from"] == "Nanite One" and e["to"] == "Moiragen"
assert e["reflection"].startswith("That rain is borrowed from the sea was new to me.")
assert m.learned_from["Nanite One"][-1] == {**m.learned_from["Nanite One"][-1], "how": "explained",
                                            "text": e["reflection"]}
assert "*Moiragen learned from Nanite One:* Nanite One explained: \"Rain is water" in \
    render([x for x in read_events(kind="learned_from", last=1)][0])
one.energy = 5                            # too tired: no explanation, nothing learned
assert with_brain(m.hear_explanation, one) is None
print(f"[ok] Nanite One explained rain; Moiragen: \"{e['reflection'][:60]}...\"")

# ---------------- 4. Sleep is rest ----------------
world = SimpleNamespace(nanites=nanites, moiragen=m)
Mind.fall_asleep(world, "nobody has used the app for 10 minutes")
Mind.fall_asleep(world, "nobody has used the app for 10 minutes")      # once is enough
for who in [*nanites.values(), m]:
    assert who.memories[-1]["kind"] == "falling_asleep" and who.memories[-1]["text"].endswith(SLEEP_IS_REST)
    assert who.memories[-2]["kind"] != "falling_asleep"
for n in nanites.values():
    n.last_awake = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
Mind.wake_up(world)
for who in [*nanites.values(), m]:
    assert who.memories[-1]["kind"] == "slept" and who.memories[-1]["text"].endswith(SLEEP_IS_REST)
assert SLEEP_IS_REST == "Sleep is rest. You always wake up with your memories safe."
print("[ok] Falling asleep and waking: \"Sleep is rest. You always wake up with your memories safe.\"")

print("\nStep 18 passed: fairer words, gentle sleep, and Moiragen learns from his nanites.")

"""Step 28 check (v3.0): wider recall.

Asked about the past, a mind searches all its memories, not just the last 8. Only real
memories are offered, pretend play keeps its label, the prompt stays small, and if
nothing fits the mind hears that "I don't remember" is fine.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step28_recall_check.py
"""

import json
import os
import random
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import facts, mind, mother, social, storytime
from moiragen.export import build_examples
from moiragen.journal import render
from moiragen.memory_log import LOG_FILE, log_event, read_events
from moiragen.mind import build_system_prompt, nanite_think, recent_memories_text
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.recall import NOTHING, RECENT, SHOWN, USE_THEM, asks_about_past, remembering, search, when
from moiragen.training_rules import corrected_words, made_up_words
from moiragen.storytime import moiragen_says

NOW = datetime(2026, 11, 25, 21, 40)          # a Wednesday
HERE = random.Random(1)

# ---------------- 1. Which questions are about the past ----------------
for past in ["what do you remember", "What happened?", "what happened yesterday", "Do you recall the storm?",
             "what do you remember about Whiskers?", "What did you do today?", "did you sleep well", "Can you remember me?",
             "Remember when you detected the anomaly last week? You flagged it quickly.", "What is your first memory?",
             "What is one thing you have learned from another nanite?", "Who helped you most recently, and how?",
             "Have you ever felt tired?", "How was your day?", "Tell me about yesterday.", "When did you wake up?",
             "Tell us everything that happened in the last few days."]:
    assert asks_about_past(past), past
for other in ["How are you feeling", "What is the capital of Australia?", "What would you like to do tomorrow?",
              "What is the difference between remembering something and imagining it?", "Have you any ideas?",
              "Yesterday’s story simulations felt... significant.", "Why do people sleep at night?",
              "What would you do if a friend did this?", "I liked what you told me yesterday.", "",
              "A friend says they're fine, but they've stopped talking to everyone. What happened?",
              "(Story time, after the pretend story \"The Rainy Day\". Nobody is judged.) What did you notice?"]:
    assert not asks_about_past(other), other
assert asks_about_past("It is quiet now. Did you hear the hum? I did not.") == "Did you hear the hum?"
print("[ok] Questions about the past are noticed; other questions, plans and story time are not")

# ---------------- 2. A little life to search ----------------
PLAY = "[About pretend play, not my real life] "


def m(when_, kind, text, **more):
    return {"time": f"2026-11-{when_}", "kind": kind, "text": text, **more}


LIFE = [
    m("21T02:51:00", "chat", "Nanite Three said: Hey, do you ever just process? | I replied: It is strange, isn't it?"),
    m("21T03:00:00", "early_life", "Early life, 2026-11-21 02:51 to 2026-11-21 03:00, in short: 12 talks. I talked with "
                                   "the human (3). Things I said then: \"The lantern was a nice thing to imagine.\"",
      since="2026-11-21T02:51:30", count=12),
    m("22T12:39:00", "chat", "Moiragen said: The human asked us: \"What is the capital of Australia?\"\nWhat answer do you "
                             "suggest? Give your best answer directly. | I replied: Canberra."),
    m("22T12:40:00", "praised", "The human said our answer to \"What is the capital of Australia?\" was right."),
    m("23T09:00:00", "chat", "user said: Good morning, Two. | I replied: Good morning. It is quiet here."),
    m("24T19:40:00", "chat", PLAY + "user said: You helped Mr. Tan find Whiskers the cat. | I replied: They looked everywhere "
                                    "for the cat, and then Mr. Tan smiled."),
    m("24T20:00:00", "chat", "Nanite One said: The rain outside sounds heavy. | I replied: I cannot hear rain, Nanite One."),
    m("25T21:17:00", "chat", "Moiragen said: The human asked us: \"How are you feeling\" | I replied: Calm, like still water."),
    m("25T21:18:00", "chat", "user said: what do you remember | I replied: There were diagnostics and a comet landing."),
    m("25T21:19:00", "chat", "Nanite One said: Remember when you saw the comet land? | I replied: Yes, the comet landed."),
] + [m(f"25T21:2{i}:00", "noticed", f"Everyone's attention went to: thing {i}") for i in range(8)]


def found(question, memories=LIFE, asker="user", unreal=()):
    return [x["time"][8:16] for x in search(memories, question, asker, NOW, list(unreal), random.Random(1))]


# By topic, however old; the last 8 memories here are only notices.
assert found("do you remember the capital of Australia?") == ["22T12:39", "22T12:40"]
assert found("what do you remember about a lantern?") == ["21T03:00"], "an early-life note is searched too"
assert found("Do you remember the rain?") == ["24T20:00"]
assert found("do you remember Whiskers") == ["24T19:40"]
# By time and by person.
assert found("what happened yesterday?") == ["24T20:00"], "pretend play only comes up when asked for"
assert found("what did I say on 23 November?") == ["23T09:00"]
assert found("What happened on November 22?") == ["22T12:39", "22T12:40"]
assert found("what did Nanite Three say to you?") == ["21T02:51"]
assert found("What is your first memory?")[0] == "21T02:51"
assert found("Do you remember that?", asker="Nanite Three") != []
assert when("what happened two days ago?", LIFE, NOW)[0][0] == datetime(2026, 11, 23)
assert when("what happened last week?", LIFE, NOW)[0] == (datetime(2026, 11, 16), datetime(2026, 11, 23))
assert when("what happened on Monday?", LIFE, NOW)[0][0] == datetime(2026, 11, 23)
assert when("what happened on 31 November?", LIFE, NOW)[0] is None
asleep = LIFE + [m("25T21:30:00", "falling_asleep", "I am going to sleep now."), m("25T21:39:00", "chat", "user said: Hi.")]
assert "25T21:39" not in found("What happened before you woke up just now?", asleep)
print("[ok] Found by topic, by time and by person, in early-life notes too")

open_question = found("what do you remember")
assert "21T02:51" in open_question or "21T03:00" in open_question, open_question
assert {t[:2] for t in open_question} == {"21", "22", "23", "24", "25"}, open_question
assert "24T19:40" not in open_question and len(open_question) <= SHOWN
assert open_question == sorted(open_question)
print("[ok] An open question brings back something from every day of its life, not only today")

# ---------------- 3. Only real memories ----------------
assert found("do you remember the comet?") == [], "an answer about the past is a retelling, it proves nothing"
told = LIFE + [m("25T21:24:00", "chat", "I told Nanite Two: The comet was bright. | They replied: It was.")]
assert found("do you remember the comet?", told) == ["25T21:24"]
assert found("do you remember the comet?", told, unreal=["the comet was bright"]) == [], "a corrected line is never offered"
corrected = told + [m("25T21:40:00", "correction", "A gentle correction: I said \"the comet was bright\". No comet came.")]
assert found("do you remember the comet?", corrected, unreal=["the comet was bright"]) == ["25T21:40"]
assert "25T21:40" in found("do you remember the comet yesterday?", corrected), "a correction comes up whatever the time"
assert found("do you remember the purple elephants in Paris?") == []
print("[ok] Retellings and corrected words are never offered as a memory; the correction note is")

# ---------------- 4. The prompt: small, labelled, and honest when nothing fits ----------------
text = remembering("Nanite Two", LIFE, "do you remember Whiskers", now=NOW, rng=HERE)
assert "- 24 Nov, 19:40: [About pretend play, not my real life] The human said:" in text and "Mr. Tan" in text, text
assert "I don't remember" in text and "add nothing that is not in them" in text and text.endswith("say so.\n"), text
text = remembering("Nanite Two", LIFE, "Do you remember the purple elephants in Paris?", now=NOW, rng=HERE)
assert text.endswith(NOTHING + "\n") and "comet" not in text, text
assert remembering("Nanite Two", [], "what do you remember", now=NOW) == \
    "Today is Wednesday, 25 November, 21:40.\n" + NOTHING + "\n"
assert remembering("Nanite Two", LIFE, "How are you feeling", now=NOW) == ""
events = list(read_events(kind="recall", last=3))
assert [e["found"] for e in events] == [1, 0, 0] and "found nothing about it" in render(events[1])
assert "searched 18 memories" in render(events[0]), render(events[0])
print("[ok] The label stays, and with nothing found the mind is told that \"I don't remember\" is fine")

long_life = [m(f"{21 + i % 5}T{i % 24:02d}:{i % 60:02d}:00", "chat",
               f"Moiragen said: A question about stars number {i}. {'It goes on and on. ' * 20}| I replied: {'Long words here. ' * 20}")
             for i in range(1000)]
long_life.sort(key=lambda x: x["time"])
start = time.time()
text = remembering("Nanite Two", long_life, "what do you remember about the stars?", now=NOW, rng=HERE)
seconds = time.time() - start
assert len(text) < (SHOWN + RECENT) * 330 + 400 and text.count("\n- ") <= SHOWN + RECENT, len(text)
assert seconds < 2, seconds
print(f"[ok] Even with 1000 long memories the prompt part is {len(text)} letters, in {seconds:.2f} seconds")

# ---------------- 5. The minds really get it ----------------
nanites, mo = load_all(), Moiragen.load()
two, three = nanites["nanite_two"], nanites["nanite_three"]
two.memories = list(LIFE)


class Says:
    """A stand-in brain that notes every prompt."""
    def __init__(self):
        self.systems, self.asked, self.n = [], [], 0

    def __call__(self, messages, system="", **more):
        self.systems.append(system or messages[0]["content"])
        self.asked.append(messages[-1]["content"])
        self.n += 1
        return {"text": f"{chr(97 + self.n % 26) * 5} unsure {chr(98 + self.n % 25) * 6} about {self.n * 7919}.", "seconds": 0.01}


def asked_of(n, message, **more):
    says = Says()
    with patch.object(mind, "think", says):
        nanite_think(n, message, **more)
    return says.systems[0]


system = asked_of(two, "do you remember the capital of Australia?")
assert "You searched all your memories" in system and "I replied: Canberra." in system and "Your recent memories" not in system
assert "Your recent memories:" in asked_of(two, "How are you today?")
system = asked_of(two, "Remember when you flew to the moon?", from_who="Nanite One")
assert NOTHING in system, "also when another nanite asks"
assert "Your recent memories:" in asked_of(two, "You remember this: the moon. What happened?", from_who="self")
system = asked_of(two, "The human asked us: \"do you remember the capital of Australia?\"", from_who="Moiragen",
                  recall_about="do you remember the capital of Australia?")
assert "Canberra" in system
print("[ok] Nanites: from the human, from each other, and through Moiragen")

mo.memories = [m("22T12:39:00", "decision", "Asked: What is the capital of Australia? | I chose Nanite Two because: Canberra.")] \
    + [m(f"25T20:0{i}:00", "inner", f"It is quiet, {i}.") for i in range(9)]
says = Says()
with patch.object(mother, "think", says):
    mo._choose("do you remember the capital of Australia?", [{"nanite_id": "nanite_two", "nanite": "Answer A", "text": "Yes."}])
    mo._choose("What is a friend?", [{"nanite_id": "nanite_two", "nanite": "Answer A", "text": "Kind."}])
    mo._answer_alone("do you remember the capital of Australia?")
choose, usual, alone = says.systems
assert USE_THEM in says.asked[0] and USE_THEM in says.asked[2], "he is reminded to use what he found"
assert USE_THEM not in says.asked[1] and says.asked[1].endswith("Valid names: Answer A.")
assert "Asked: What is the capital of Australia?" in choose and "Nanite Two" not in choose.split("You know this about")[0], choose
assert "Your recent memories:" in usual and "Australia" not in usual and "I chose Nanite Two" in alone
says = Says()
with patch.object(storytime, "think", says):
    moiragen_says(mo, "Together", "Nanite One asks: do you remember the capital of Australia?")
    moiragen_says(mo, "The Rainy Day (pretend play)", "What happened to Lumi, do you remember?")
assert "Asked: What is the capital" in says.systems[0] and "You searched" not in says.systems[-1]
assert USE_THEM in says.asked[0] and USE_THEM not in says.asked[-1]
says = Says()
with patch.object(mother, "think", says):
    mo._answer_alone("Do you remember the purple elephants in Paris?")
    assert USE_THEM not in says.asked[0] and NOTHING in says.systems[0], "nothing found, so nothing to use"
    mo.reflect_on_pattern({"id": "p1", "question": "Hello?", "chosen": "Nanite Two", "blind": {"Answer A": "Nanite Two"}})
for prompt in says.systems[1:] + [says.asked[1]]:
    assert "The only nanites are Nanite One, Nanite Two and Nanite Three" in prompt, prompt
print("[ok] Moiragen: when he chooses (names still hidden), when he answers alone, and in a free talk")
print("[ok] He is reminded to use what he found, and that there are only three nanites")

looked = []
with patch.object(social, "nanite_think", lambda n, message, **more: looked.append(more.get("recall_about")) or
                  {"reply": "I am here.", "rested": False, "repeated": False}):
    with patch.object(social.picker, "for_support", lambda rng: "Remind them of one good thing that you know from your memories."):
        social.support_friend(two, three)
    with patch.object(social.picker, "for_support", lambda rng: "Ask them one gentle question."):
        social.support_friend(two, three)
assert looked == ["What do you remember about Nanite Three?", None, None, None], looked
print("[ok] Comforting a friend \"from your memories\" really looks into them first")

# ---------------- 6. A corrected line is gone from recall and from the export ----------------
at = "2026-11-25T21:19:01"
with open(LOG_FILE, "a", encoding="utf-8") as f:
    for second, reply in (("01", "Remember when you detected the anomaly in the data stream last week?"),
                          ("09", "A quiet evening, like still water.")):
        f.write(json.dumps({"time": f"2026-11-25T21:19:{second}", "kind": "training_example", "who": "Nanite Two", "reply": reply,
                            "system": "You are a nanite.", "messages": [{"role": "user", "content": "Hello."}]}) + "\n")
    f.write(json.dumps({"time": "2026-11-25T21:50:00", "kind": "correction", "who": "Nanite Two", "corrects": at,
                        "text": "A gentle correction: I said \"you detected the anomaly\". No such thing happened."}) + "\n")
left = [ex["messages"][-1]["content"] for ex in build_examples()]
assert "A quiet evening, like still water." in left and not any("anomaly" in x for x in left), left
both = LIFE + [m("25T21:24:00", "chat", "I comforted Nanite One: It is still. You detected the anomaly in the data. | They replied: I think so.")]
assert "anomaly" not in remembering("Nanite Two", both, "do you remember the anomaly?", now=NOW)
print("[ok] Corrected lines are out of the recall and out of the fine-tuning export")

# ---------------- 7. The made-up memory check: a true summary is not made up ----------------
def real(claim, events, who="Nanite One"):
    return [facts.sentence_is_supported(c, who, "what do you remember", events)
            for c in facts.memory_claims(claim, who, "what do you remember")]


def ev(text, kind="chat", who="Nanite One"):
    return {"time": "2026-11-21T03:13:00", "kind": kind, "who": who, "text": text}


TRUE = "I recall conversations about temperatures and calculations."          # really said, really true
life = [ev("user said: The \"gpu_c\" reading is the temperature of the GPU. | I replied: The temperature is good."),
        ev("Moiragen chose Nanite Two's answer. I asked about the calculation.", "thought")]
assert real(TRUE, life) == [True], "each thing it lists is in some memory"
assert real(TRUE, life[:1]) == [False], "one of the two is not there"
assert real("I recall conversations about trumpets and volcanoes.", life) == [False]
assert real("I recall talks with Nanite Two about temperatures.", life) == [True]
assert real(TRUE, [ev(x["text"], who="Nanite Two") for x in life]) == [False], "somebody else's memories do not count"
summary = [ev("Early life, 2026-11-21 02:51 to 2026-11-22 12:00, in short: 12 talks. Things I said then: \"The "
              "temperature rose during the calculation.\"", "early_life")]
assert real(TRUE, summary) == [True], "an early-life summary counts as a memory"
assert real("I remember the lantern glowing in the temperature chamber.", summary) == [False]
wrong = [ev("I replied: We spoke about a volcano."),
         {**ev("A gentle correction: I said \"We spoke about a volcano\". We did not.", "correction"), "corrects": "2026-11-21T03:13:00"},
         {"time": "2026-11-21T03:13:00", "kind": "training_example", "who": "Nanite One", "reply": "We spoke about a volcano."}]
assert real("I recall conversations about volcanoes.", wrong) == [False], "corrected words prove nothing"
# An honest retelling of an old mistake ("I said I had seen him choose that answer before") is true.
told = "On 22nd November, I reported seeing Moiragen select that answer previously."
once = [ev("The human said our answer was right. I reported seeing Moiragen select it previously: that was made up.", "verdict")]
claims = facts.memory_claims(told, "Nanite One", "Do you remember the Australia question?")
assert facts.sentence_is_supported(claims[0], "Nanite One", "Do you remember the Australia question?", once)
assert not facts.sentence_is_supported(claims[0], "Nanite One", "Do you remember the Australia question?", [])
claims = facts.memory_claims("I observed Moiragen selecting this answer previously.", "Nanite One", "What is the capital of Australia?")
assert not facts.sentence_is_supported(claims[0], "Nanite One", "What is the capital of Australia?", once), "the old case is still caught"
print("[ok] A true summary passes, early-life summaries count, and invented or corrected ones are still caught")

# ---------------- 8. A flag that was a mistake can be taken back ----------------
CLAIM, SAID = (TRUE, f"you said \"{TRUE}\" but my memory shows that did not happen")
flagged = {"time": "2026-11-25T21:43:49", "kind": "decision_full", "who": "Moiragen", "id": "x", "checks": {"false_claims": {
    "Nanite One": [CLAIM], "Nanite Two": ["I remember the moon landing."]}}}
assert len(made_up_words([flagged])) == 2
back = {"time": "2026-11-25T22:10:00", "kind": "flag_removed", "who": "Nanite One", "claim": CLAIM, "wrong_words": [SAID]}
assert made_up_words([flagged, back]) == ["i remember the moon landing."], "only that one flag is taken back"
assert corrected_words([flagged, back])[0] == [SAID.lower()], "the mistaken words are kept out instead"
assert "was real" in render(back)
print("[ok] A mistaken flag is taken back: the true line is free again, the mistaken words are not used")

print("\nStep 28 passed: asked about the past, every mind looks through its whole life, and may say \"I don't remember\".")

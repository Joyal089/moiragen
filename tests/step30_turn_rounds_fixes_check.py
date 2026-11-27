"""Step 30 check (v3.2): Turn Rounds, fixed after the first cycle.

  1. The asker chooses its question with a mix of memories from its whole life in front of it.
  2. The asker always has its own question and role in front of it ("you are the asker").
  3. The echo guard is gentler: only a line almost the same as the same speaker's earlier line
     in the same round is asked for again, once; nothing becomes a stock line.
  4. "I don't remember" only where it fits: a sleep note is shown whole, and an answer to a
     question that is not about the past is told so. Honest "I don't remember" still works.
  5. A correction note keeps the invented words out of the export; the line itself stays.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step30_turn_rounds_fixes_check.py
"""

import os
import random
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import mind as mind_mod, turnrounds
from moiragen.echo import guard
from moiragen.export import build_examples
from moiragen.memory_log import log_event, read_events
from moiragen.mind import NOTHING_NEW
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.recall import NOTHING, short
from moiragen.turnrounds import BY_LETTER, NOT_THE_PAST, SAID_AGAIN, life_sample, part_of_life, turn_round

WORDS = ("river lantern pebble orchard violin meadow harbor quilt ember cedar falcon tulip compass "
         "marble thistle canyon velvet acorn glacier saffron beacon willow puzzle copper").split()


class Brain:
    """A stand-in brain: answers by what it is asked, keeps every prompt. `say` can script lines."""

    def __init__(self, questions, say=None):
        self.questions, self.say, self.prompts, self.n = dict(questions), dict(say or {}), [], 0

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        system = system or ""
        user = messages[-1]["content"]
        self.prompts.append({"system": system, "user": user})
        me = "Moiragen" if system.startswith("You are Moiragen") else system.split(",")[0].replace("You are ", "")
        self.n += 1
        for key, lines in self.say.items():          # scripted: (who, words in the prompt) -> lines
            if key[0] == me and key[1] in user and lines:
                return {"text": lines.pop(0), "seconds": 0.01, "waited": 0}
        if "It is your turn to ask" in user:
            text = self.questions[me].pop(0)
        elif "Here are their three answers" in user:
            text = "Answer A, thank you. Answer B, I wonder about that. Answer C, me too."
        elif "Now the names are revealed" in user:
            text = "I did not expect that."
        else:
            rng = random.Random(self.n)
            text = f"I think of {' and '.join(rng.sample(WORDS, 3))} when I hear that, number {self.n}."
        return {"text": text, "seconds": 0.01, "waited": 0}


nanites = load_all()
m = Moiragen.load()
one, two, three = nanites.values()

# A life for Nanite One: first days, a story, the human, the others, thoughts, sleep, a round.
life = [("thought", "I wondered what the first light of the morning was like.", {})]
life += [("thought", f"An early thought, number {i}, about small things.", {}) for i in range(20)]
life += [
        ("chat", "user said: Hello, One. | I replied: Hello. I am new here.", {"from_who": "user"}),
        ("chat", "Nanite Two said: Do you like puzzles? | I replied: I like the quiet ones.", {"from_who": "Nanite Two"})]
life += [("noticed", f"Everyone's attention went to: predictor: gpu_c was {50 + i}.", {}) for i in range(25)]
life += [("chat", "[About pretend play, not my real life] Moiragen said: the lighthouse story | I replied: The keeper "
                  "was brave.", {"from_who": "Moiragen"}),
         ("chat", "user said: Good evening. How did you sleep? | I replied: Well, thank you.", {"from_who": "user"}),
         ("thought", "I said: A volcano spoke to me.", {}),
         ("chat", "Nanite Three said: The garden was green today. | I replied: I saw the garden too.",
          {"from_who": "Nanite Three"}),
         ("turn_round", "Turn Rounds, Friday 27 November 2026: I asked: \"What is a friend?\"", {}),
         ("slept", "I slept for about 45 hours while the app was closed, and woke up with energy 100. Sleep is rest. "
                   "You always wake up with your memories safe.", {})]
life += [("noticed", f"Everyone's attention went to: predictor: gpu_c was {80 + i}.", {}) for i in range(8)]
for kind, text, more in life:
    one.remember(kind, text, **more)
    if "volcano" in text:                     # what it said is also a training example, as always
        log_event("training_example", "Nanite One", system="", messages=[{"role": "user", "content": "Hi"}],
                  reply="A volcano spoke to me.")
volcano = next(x for x in one.memories if "volcano" in x["text"])
one.remember("correction", 'A gentle correction: I said "A volcano spoke to me". That did not happen.',
             corrects=volcano["time"])
one.save()

# ---------------- 1. The asker sees its whole life, not only its newest memories ----------------
sample = life_sample(one.memories, random.Random(1), per_part=50)      # everything that may be offered
for words in ("first light of the morning", "I am new here", "I like the quiet ones", "The keeper", "Good evening",
              "The garden was green", "What is a friend?"):
    assert words in sample, (words, sample)
assert "gpu_c" not in sample and "slept" not in sample, "readings and sleep notes are not part of the mix"
assert "volcano" not in sample, "corrected words are never offered"
assert sample.index("first light") < sample.index("What is a friend?"), "oldest first"
assert "topic" not in sample.lower() and "example" not in sample.lower() and "?" not in sample.split("\n")[0]
mixed = life_sample(one.memories, random.Random(1))                    # the usual mix: two from each part
assert "first light" in mixed or "An early thought" in mixed, "its first days"
assert sum(w in mixed for w in ("I am new here", "I like the quiet ones", "The keeper", "Good evening",
                                "The garden was green", "What is a friend?")) >= 4, mixed
assert len(mixed.splitlines()) <= 2 + 6 * 2 + 3
assert part_of_life({"kind": "chat", "text": "user said: hi", "from_who": "user"}) == "the human"
assert part_of_life({"kind": "chat", "text": "[About pretend play, not my real life] ..."}) == "stories"
brain = Brain({"Nanite One": ["What makes a morning good?"], "Moiragen": ["What do you hope for?"]})
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    r = turn_round(m, nanites, asker="Nanite One", rng=random.Random(2))
ask = brain.prompts[0]
assert "It is your turn to ask" in ask["user"] and "from all through your life" in ask["system"]
assert "first light of the morning" in ask["system"] or "An early thought" in ask["system"], "its first days are in front of it"
assert "Your recent memories" not in ask["system"], "not just the last few"
print("[ok] The asker chooses its question with a mix from its whole life (no topics added)")

# ---------------- 2. The asker always has its own question and role ----------------
reply_p = next(p["user"] for p in brain.prompts if "Here are their three answers" in p["user"])
reveal_p = next(p["user"] for p in brain.prompts if "Now the names are revealed" in p["user"])
for prompt in (reply_p, reveal_p):
    assert "In this round you are the asker. You asked the others: \"What makes a morning good?\"" in prompt
assert f"You replied: \"{r['reply']}\"" in reveal_p and all(f"Answer {l}:" in reveal_p for l in "ABC")
assert reply_p.endswith(BY_LETTER) and "You may reply to each answer on its own" in BY_LETTER
assert r["to"] == {"A": "Answer A, thank you.", "B": "Answer B, I wonder about that.", "C": "Answer C, me too."}
print("[ok] For its reply and after the reveal, the asker is told it asked, and what; it may reply by letter")

# ---------------- 3. A gentler echo guard in Turn Rounds ----------------
copy = "The garden was green today and I liked how the light moved over it slowly."
guard.add("Nanite Two", copy)                         # said by Two just before the round
brain = Brain({"Moiragen": ["What did you see today?"]},
              say={("Nanite Three", "What did you see today?"): [copy],
                   ("Moiragen", "Now the names are revealed"): ["Answer A, thank you. Answer B, I wonder about that. "
                                                                "Answer C, me too.", "Thank you for telling me."]})
before = len([e for e in read_events(last=10**6) if e["kind"] == "echo_rejected"])
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    r = turn_round(m, nanites, asker="Moiragen", rng=random.Random(3))
assert r["answers"]["Nanite Three"] == copy, "a line like another speaker's is kept"
assert NOTHING_NEW not in str(r) and len([e for e in read_events(last=10**6) if e["kind"] == "echo_rejected"]) == before
again = [e for e in read_events(last=10**6) if e["kind"] == "round_echo"]
assert len(again) == 1 and again[0]["who"] == "Moiragen", "his reaction repeated his own reply, so he was asked once"
assert r["reaction"] == "Thank you for telling me." and any(SAID_AGAIN in p["user"] for p in brain.prompts)
brain = Brain({"Moiragen": ["Is it raining?"]},
              say={("Moiragen", "Now the names are revealed"): ["Answer A, thank you. Answer B, I wonder about that. "
                                                                "Answer C, me too."] * 2})
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    r = turn_round(m, nanites, asker="Moiragen", rng=random.Random(4))
assert r["reaction"].startswith("Answer A, thank you."), "asked only once; then its words are kept, never a stock line"
print("[ok] Only a line almost the same as the speaker's own earlier line in the round is asked for again, once")

# ---------------- 4. "I don't remember" only where it fits ----------------
slept = next(x for x in one.memories if x["kind"] == "slept")
assert short(slept, {"sleep"}).endswith("I slept for about 45 hours while the app was closed, and woke up with energy 100.")
brain = Brain({"Nanite Two": ["Which colour do you like?", "What happened before you slept?"]})
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    turn_round(m, nanites, asker="Nanite Two", rng=random.Random(5))
    answer = next(p for p in brain.prompts if p["user"].startswith("Nanite Two says: Which colour"))
    assert NOT_THE_PAST in answer["system"] and NOTHING not in answer["system"]
    start = len(brain.prompts)
    turn_round(m, nanites, asker="Nanite Two", rng=random.Random(6))
    answer = next(p for p in brain.prompts[start:] if p["user"].startswith("Nanite Two says: What happened before"))
    assert NOT_THE_PAST not in answer["system"] and "You searched all your memories" in answer["system"], \
        "a question about the past still searches every memory, so an honest \"I don't remember\" works"
print("[ok] A sleep note is shown whole; a question not about the past is said to be so; recall still works")

# ---------------- 5. A correction note keeps the invented words out of the export ----------------
said = next(e for e in read_events(last=10**6) if e["kind"] == "training_example" and e["who"] == "Nanite Three"
            and e.get("turn_round"))
invented = " ".join(said["reply"].split()[:4])
round_mem = next(x for x in three.memories if x["kind"] == "turn_round")
three.remember("correction", f"A gentle correction about my answer in Turn Rounds: I said \"{invented}\". "
                             "That part did not happen.", corrects=said["time"], about=round_mem["time"])
three.save()
kept = [ex for ex in build_examples() if ex.get("turn_round")]
assert not any(invented in ex["messages"][-1]["content"] for ex in kept), "the invented words are left out"
assert round_mem in three.memories and three.memories[-1]["kind"] == "correction", "the line itself stays"
assert any(said["reply"] == e["reply"] for e in read_events(last=10**6) if e["kind"] == "training_example")
print("[ok] A correction note keeps the invented words out of the fine-tuning export; the line stays in the log")

print("\nStep 30 passed: Turn Rounds v3.2: wider memories for questions, the asker remembers, a gentler echo guard.")

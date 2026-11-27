"""Step 29 check (v3.1): Turn Rounds.

Everyone takes turns asking (One, Two, Three, Moiragen, then One again); the other three
answer; the asker sees the answers as A, B and C, shuffled and without names, replies in
its own words, then hears who wrote what. Only a repeated question gets a soft nudge.
Everyone remembers the round with the date. No judging: no health or mood changes.

Uses a stand-in for the brain (no Ollama needed) and a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step29_turn_rounds_check.py
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
from moiragen.export import build_examples
from moiragen.journal import render
from moiragen.memory_log import log_event, read_events
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.turnrounds import (ABOUT, NUDGE, ORDER, STOP_BELOW, answerers, asked_before, blind,
                                 blind_text, next_asker, reveal_text, split_reply, turn_round, turn_rounds)

# Words to build answers that never sound alike, so the echo guard stays quiet.
WORDS = ("river lantern pebble orchard violin meadow harbor quilt ember cedar falcon tulip compass "
         "marble thistle canyon velvet acorn glacier saffron beacon willow puzzle copper").split()


class Brain:
    """A stand-in brain. It answers by what it is asked, and keeps every prompt it saw."""

    def __init__(self, questions):
        self.questions = dict(questions)        # asker -> the questions it will ask, in order
        self.prompts, self.n = [], 0

    def __call__(self, messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
        system = system or (messages[0]["content"] if messages[0]["role"] == "system" else "")
        user = messages[-1]["content"]
        self.prompts.append({"system": system, "user": user})
        me = "Moiragen" if system.startswith("You are Moiragen") else system.split(",")[0].replace("You are ", "")
        self.n += 1
        if "It is your turn to ask" in user:
            assert self.questions.get(me), (me, user[-200:])
            text = self.questions[me].pop(0)
        elif "Here are their three answers" in user:
            text = "Answer A, that made me think of rain. B: I am not sure I agree. Something else came to mind too."
        elif "Now the names are revealed" in user:
            text = "Oh, that is a surprise to me."
        else:
            rng = random.Random(self.n)
            text = f"I think of {' and '.join(rng.sample(WORDS, 3))} when I hear that, number {self.n}."
        return {"text": text, "seconds": 0.01, "waited": 0}


nanites = load_all()
m = Moiragen.load()
one, two, three = nanites.values()

# ---------------- 1. Whose turn: One, Two, Three, Moiragen, then One again ----------------
assert next_asker([]) == "Nanite One"
for asker, after in zip(ORDER, ORDER[1:] + ORDER[:1]):
    assert next_asker([{"kind": "turn_round_full", "asker": asker}]) == after
assert answerers("Nanite Two") == ["Nanite Three", "Moiragen", "Nanite One"]
assert answerers("Moiragen") == ["Nanite One", "Nanite Two", "Nanite Three"]
print("[ok] The order is One, Two, Three, Moiragen, then back to One; the other three answer")

# ---------------- 2. Blind answers: shuffled, labelled A, B, C, names hidden ----------------
answers = {"Nanite Two": "Nanite Three said it first, but I feel it too.", "Nanite Three": "Calm.",
           "Moiragen": "I wonder."}
orders = set()
for seed in range(12):
    shown, names = blind(answers, random.Random(seed))
    assert list(shown) == ["A", "B", "C"] and sorted(names.values()) == sorted(answers)
    assert all(shown[l] == answers[n].replace("Nanite Three", "another nanite") for l, n in names.items())
    orders.add(tuple(names.values()))
    seen = blind_text("What do you hear?", shown)
    assert not any(name in seen for name in answers), "no names in what the asker sees"
assert len(orders) > 2, "the order really is shuffled"
assert reveal_text({"A": "Nanite Two", "B": "Moiragen", "C": "Nanite Three"}) == \
    "Answer A was Nanite Two, Answer B was Moiragen and Answer C was Nanite Three."
print("[ok] The asker sees A, B and C in a shuffled order, with names hidden in the words too")

# What the asker said to each answer (it may also say things to nobody in particular).
parts = split_reply("Hello all. Answer A, that made me think. It was lovely. B: I am not sure. "
                    "Answer A and Answer B are close, I think. Answer C was different.")
assert parts == {"A": "Answer A, that made me think. It was lovely.", "B": "B: I am not sure.",
                 "C": "Answer C was different.", "all": "Hello all. Answer A and Answer B are close, I think."}, parts
assert split_reply("A lovely thought. A good day.") == {"all": "A lovely thought. A good day."}
print("[ok] Its reply is split by the answer it talks to; the rest is for everyone")

# ---------------- 3. One round, start to end ----------------
before = {n.name: (n.health, n.mood) for n in nanites.values()}
m_health = m.health
brain = Brain({"Nanite One": ["What does quiet feel like to you?", "What does quiet feel like to you?",
                              "Do you ever wonder where the rain goes?", "How do you know you are awake?"],
               "Nanite Two": ["Which sound do you like best?"], "Nanite Three": ["What is a friend?"],
               "Moiragen": ["What would you like to learn next?"]})
events = []
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    r = turn_round(m, nanites, rng=random.Random(3), notify=lambda t, **d: events.append((t, d)))

assert r["asker"] == "Nanite One" and r["question"] == "What does quiet feel like to you?" and not r["nudged"]
ask = brain.prompts[0]["user"]
assert ask == f"Your creator (the human) says: {ABOUT}\nIt is your turn to ask. Nanite Two, Nanite Three and " \
              "Moiragen will answer. Write only your question.", ask
assert sorted(r["answers"]) == ["Moiragen", "Nanite Three", "Nanite Two"]
assert all(p["user"].startswith("Nanite One says: What does quiet") for p in brain.prompts[1:4]
           if not p["system"].startswith("You are Moiragen")), "the answerers hear the asker"
assert "Nanite One says: What does quiet feel like to you?" in [p["user"] for p in brain.prompts[1:4]]
reply_prompt = brain.prompts[4]["user"]
assert "Here are their three answers" in reply_prompt and not any(n in reply_prompt for n in r["answers"])
assert reply_prompt.endswith(turnrounds.BY_LETTER) and "In this round you are the asker. You asked the others: \"What does quiet" in reply_prompt
assert "Now the names are revealed: " + r["reveal"] in brain.prompts[5]["user"]
assert "You do not have to." in brain.prompts[5]["user"]
kinds = [t for t, _ in events if t != "thinking"]
assert kinds == ["turn_round_start", "turn_question", "turn_answer", "turn_answer", "turn_answer",
                 "turn_reply", "turn_reveal", "turn_reaction", "turn_round_end"], kinds
live = [d for t, d in events if t == "turn_answer"]
assert sorted(d["label"] for d in live) == ["A", "B", "C"] and all("who" not in d for d in live), \
    "while they answer, the viewer only shows the letters"
assert r["to"]["A"].startswith("Answer A") and r["to"]["B"].startswith("B:")
print("[ok] One round: its own question, three answers, a blind reply in its own words, then the reveal")

# ---------------- 4. Memory, with the date, for everyone ----------------
for mind in [*nanites.values(), m]:
    mem = mind.memories[-1]
    assert mem["kind"] == "turn_round" and mem["turn_round"] == r["id"] and mem["time"][:10] == r["time"][:10]
    day = mem["time"][:10]
    assert "Turn Rounds, " in mem["text"] and str(int(day[8:])) in mem["text"] and day[:4] in mem["text"]
    assert "What does quiet feel like to you?" in mem["text"] and "Then the names were revealed." in mem["text"]
    assert all(f"Answer {l} (" in mem["text"] for l in "ABC")
mine = two.memories[-1]
assert mine["my_answer"] == r["answers"]["Nanite Two"] and "Answer Nanite" not in mine["text"]
assert mine["said_to_me"] == " ".join(x for x in (r["to"].get(mine["label"], ""), r["to"].get("all", "")) if x)
assert f"Answer {mine['label']} (I)" in mine["text"], "it knows which answer was its own"
assert one.memories[-1]["text"].startswith("Turn Rounds, ") and ": I asked:" in one.memories[-1]["text"]
full = [e for e in read_events(last=10**6) if e["kind"] == "turn_round_full"]
assert len(full) == 1 and full[0]["answers"] == r["answers"] and full[0]["names"] == r["names"]
assert "Turn Rounds: Nanite One asks" in render(full[0]) and "**Revealed:**" in render(full[0])
print("[ok] Everyone remembers the round with its date; the answerers know what the asker said to them")

# ---------------- 5. No judging; energy is spent as usual; labelled for the export ----------------
assert {n.name: (n.health, n.mood) for n in nanites.values()} == before and m.health == m_health
assert one.energy < 100 and two.energy < 100, "thinking still costs energy"
examples = build_examples()
labelled = [ex for ex in examples if ex.get("turn_round") == r["id"]]
assert len(labelled) == 6, len(labelled)              # question, 3 answers, reply, reaction
assert {ex["task"] for ex in labelled} == {"round_question", "round_answer", "round_response", "round_reaction"}
assert not [ex for ex in build_examples(skip_rounds=True) if ex.get("turn_round")]
assert not any(e["kind"] in ("decision_full", "verdict", "lesson") for e in read_events(last=10**6))
print("[ok] No scores, health or mood changes; energy is spent; every line is labelled for the export")

# ---------------- 6. The soft nudge, only for a question asked before ----------------
log_event("turn_round_full", "mind", id="old", asker="Moiragen", question="Shall we sing?")   # Nanite One asks next
assert asked_before("Nanite One", "what does QUIET feel like to you") == "What does quiet feel like to you?"
assert asked_before("Nanite One", "What is a song?") is None
assert asked_before("Nanite Two", "What does quiet feel like to you?") is None, "only its own questions count"
start = len(brain.prompts)
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    r2 = turn_round(m, nanites, rng=random.Random(4))
assert r2["asker"] == "Nanite One" and r2["nudged"] and r2["question"] == "Do you ever wonder where the rain goes?"
nudge = brain.prompts[start + 1]["user"]
assert nudge.endswith(f"You wrote: \"What does quiet feel like to you?\"\n{NUDGE}"), nudge
assert NUDGE == "You've asked that before. You can ask something new if you like."
assert [e for e in read_events(last=10**6) if e["kind"] == "round_nudge"]
assert all(NUDGE not in p["user"] for p in brain.prompts[:start]), "no nudge for a new question"
print("[ok] A question asked before gets the soft nudge, once; a new one gets nothing")

# ---------------- 7. A whole cycle: everyone asks once, Moiragen too ----------------
for n in nanites.values():
    n.energy = 100
log_event("turn_round_full", "mind", id="old2", asker="Moiragen", question="Shall we dance?")
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    out = turn_rounds(m, nanites, 4, rng=random.Random(5))
assert [x["asker"] for x in out["rounds"]] == ORDER and out["stopped"] is None
mo = out["rounds"][3]
assert mo["question"] == "What would you like to learn next?" and sorted(mo["answers"]) == ["Nanite One", "Nanite Three", "Nanite Two"]
assert any(p["user"] == "Moiragen says: What would you like to learn next?" for p in brain.prompts), \
    "the nanites hear Moiragen ask"
assert any(p["user"] == "Nanite Two says: Which sound do you like best?" and p["system"].startswith("You are Moiragen")
           for p in brain.prompts), "Moiragen answers like everyone else"
print("[ok] Four rounds: each one asks once, Moiragen as a normal member")

# ---------------- 8. Too tired: they sleep first, and the order carries on later ----------------
three.energy = STOP_BELOW - 1
asks_next = next_asker()
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain):
    out = turn_rounds(m, nanites, 4)
assert out["rounds"] == [] and out["stopped"] == ["Nanite Three"] and next_asker() == asks_next == "Nanite One"
paused = [e for e in read_events(last=10**6) if e["kind"] == "turn_rounds_paused"][-1]
assert "Nanite Three needs to sleep first" in paused["text"] and render(paused)
print("[ok] Below 30 energy the rounds pause; the next asker carries on later")

# ---------------- 9. The viewer's API ----------------
from fastapi.testclient import TestClient
from moiragen.loop import Mind
from server import create_app

for n in nanites.values():
    n.save()
mind = Mind(tick_seconds=3600)
for n in mind.nanites.values():
    n.energy = 100
brain.questions["Nanite One"] = ["Where do thoughts go at night?"]
with patch.object(mind_mod, "think", brain), patch.object(turnrounds, "think", brain), \
        TestClient(create_app(mind=mind)) as client:
    sent = []
    mind.subscribe(lambda e: sent.append(e["type"]))
    assert client.post("/api/turnrounds", json={"rounds": 0}).status_code == 400
    got = client.post("/api/turnrounds", json={"rounds": 1})
    assert got.status_code == 200, got.text
    assert got.json()["rounds"][0]["asker"] == "Nanite One" and "turn_reveal" in sent and "vitals" in sent
    said = client.post("/api/moiragen", json={"text": "How did you sleep?"})
    assert said.status_code == 200 and said.json()["reply"]
    assert mind.moiragen.memories[-1]["text"].startswith("The human said: How did you sleep? | I replied: ")
viewer = (Path(__file__).resolve().parent.parent / "viewer")
assert 'id="rounds"' in (viewer / "index.html").read_text(encoding="utf-8")
assert all(f'case "{t}"' in (viewer / "app.js").read_text(encoding="utf-8")
           for t in ("turn_round_start", "turn_question", "turn_answer", "turn_reply", "turn_reveal", "turn_reaction"))
print("[ok] The server runs Turn Rounds (/api/turnrounds), you can talk to Moiragen himself (/api/moiragen), "
      "and the viewer has a Turn Rounds panel")

print("\nStep 29 passed: Turn Rounds work: free questions, blind answers, a reveal, and no judging.")

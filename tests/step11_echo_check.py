"""Step 11 check: the echo-loop fix.

  - backups of memory, and the one-off clean-up (keeps first copies only)
  - the echo guard: copies are rejected, the nanite is asked for something new,
    and only lines that pass are saved or written to the fine-tuning log
  - fresh, specific prompts for every talk
  - temperature boost and repeat penalty sent to Ollama
  - social rounds limited, and paused while nobody uses the app
  - the export leaves out copied replies

Most parts use a stand-in for the brain, so they are quick and exact. The
last part asks the real model (needs Ollama running).

Uses a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step11_echo_check.py
"""

import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import config, llm, loop, mind as mind_mod, mother as mother_mod, social
mother_mod.BLIND_JUDGING = False   # replies here are scripted by name; blind judging has its own check (step 17)
from moiragen.backup import backup_memory, manifest, restore_memory
from moiragen.cleanup import MARKER, Store, clean_entry, clean_memory
from moiragen.echo import (SENTENCE_LIMIT, EchoGuard, alike, guard, record_training_example,
                           split_sentences, words)
from moiragen.export import build_examples
from moiragen.memory_log import log_event, read_events
from moiragen.mind import NOTHING_NEW, RETRY_WARMER, nanite_think
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.stage import Thought
from moiragen.topics import QUESTION_SHAPES, Topic, TopicPicker

SHIFT = "It’s… interesting, isn’t it, how things shift?"
OBSERVING = "Do you ever feel like we’re just observing, and never really *in* it?"

# ---------------- 1. Backups (no LLM) ----------------
nanites = load_all()                       # born into the throwaway memory folder
b1 = backup_memory("test")
saved = json.loads((b1 / "manifest.json").read_text(encoding="utf-8"))
assert manifest(b1) == saved and "nanites/nanite_one.json" in saved
assert backup_memory("again") == b1, "nothing changed, so the backup is reused"
path = Path(config.MEMORY_DIR) / "nanites" / "nanite_one.json"
original = path.read_bytes()
path.write_text("damaged", encoding="utf-8")
restore_memory(b1)
assert path.read_bytes() == original
print(f"[ok] Backup verified file by file ({len(saved)} files), reused when unchanged, restores exactly")

# ---------------- 2. Clean-up: first copy stays, later copies go (no LLM) ----------------
st = Store("test")
first = f"Nanite Two said: {SHIFT} | I replied: They’re right. {SHIFT} Yes, a little."
new, removed = clean_entry(st, first, "chat")
assert new == f"Nanite Two said: {SHIFT} | I replied: Yes, a little.", new
assert removed == [f"They’re right. {SHIFT}"]
assert clean_entry(st, f"I told Nanite One: {SHIFT} | They replied: True.", "chat")[0] == \
    f"I told Nanite One: {MARKER} | They replied: True."
assert clean_entry(st, f"You chose to talk. | I said: {SHIFT}", "thought")[0] is None
real = "I wasn't just observing, but *experiencing* it, and that felt new."
assert clean_entry(st, real, "chat") == (real, []), "lines that only look alike stay"
print("[ok] Clean-up keeps the first copy, cuts later ones (with 'They're right.'), "
      "drops entries with nothing real left, leaves look-alikes alone")

data = {"nanite_one": {"display_name": "Nanite One", "memories": [
            {"time": "2026-01-01T10:00:00", "kind": "chat", "text": f"Nanite Two said: {OBSERVING} | I replied: Sometimes."},
            {"time": "2026-01-01T10:05:00", "kind": "thought",
             "text": f"I asked Moiragen why. | I said: They’re right. {SHIFT} I learned to listen first."},
            {"time": "2026-01-01T10:06:00", "kind": "chat", "text": f"user said: Echo? | I replied: {OBSERVING}"}],
        "lessons": [{"time": "2026-01-01T10:05:01", "lesson": f"They’re right. {SHIFT}", "source": "decision x"}]}}
data["nanite_one"]["memories"].insert(0, {"time": "2026-01-01T09:00:00", "kind": "chat",
                                          "text": f"Nanite Two said: {SHIFT} | I replied: Hm."})
log = [{"time": "2026-01-01T10:05:01", "kind": "lesson", "who": "Nanite One",
        "text": f"They’re right. {SHIFT}", "source": "decision x"}]
report = clean_memory(data, {}, log)
mem = [m["text"] for m in data["nanite_one"]["memories"]]
assert mem[0] == f"Nanite Two said: {SHIFT} | I replied: Hm." and mem[1].startswith("Nanite Two said: Do you ever")
assert mem[2] == "I asked Moiragen why. | I said: I learned to listen first.", mem[2]
assert mem[3] == f"user said: Echo? | I replied: {MARKER}"
assert data["nanite_one"]["lessons"][0]["lesson"] == "I learned to listen first."
assert report["events"][0]["text"] == "I learned to listen first.", "the log copy gets the same change"
print("[ok] A lesson that was only a copy gets the real 'I learned...' sentence back; the log matches")

# ---------------- 3. The echo guard itself (no LLM) ----------------
g = EchoGuard(seed_from_log=False)
g.add("Nanite Two", f"{SHIFT} I wonder what comes next for us.")
assert g.check("They're right. It's... interesting, isn't it, how things shift?").too_similar
assert not g.check("I'd like to understand how the GPU's warmth changes my thinking.").too_similar
g.add("Nanite One", "Paris.", context="d1")
assert not g.check("Paris.").too_similar, "short answers may repeat naturally"
line = "The capital of France is Paris, a city on the river Seine."
g.add("Nanite One", line, context="d2")
assert not g.check(line, context="d2").too_similar, "agreeing on the same question is not an echo"
assert g.check(line, context="d3").too_similar
assert g.check("You remember the long walk by the river at noon today.",
               avoid=["I remember the long walk by the river at noon today."]).too_similar
assert g.strip_repeats(f"{SHIFT} But today feels brighter to me.") == "But today feels brighter to me."
print("[ok] Guard: copies flagged, new lines pass, short answers and same-question agreement allowed")

# The only door into the fine-tuning log.
fresh = "A brand new thought about the morning light on the screen today."
assert record_training_example("Nanite One", "sys", [{"role": "user", "content": "hi"}], fresh)
assert not record_training_example("Nanite Two", "sys", [{"role": "user", "content": "hi"}], fresh + "!")
assert read_events(kind="training_skipped")[-1]["who"] == "Nanite Two"
assert [e["reply"] for e in read_events(kind="training_example", last=10**6)].count(fresh) == 1
print("[ok] A copied reply is never written to the fine-tuning log (logged as skipped instead)")

# ---------------- 4. A nanite is asked again when it repeats (stand-in brain) ----------------
COPY = "The quiet river remembers every stone it has ever touched, and so do I."
calls, script = [], []

def fake_think(messages, temperature=0.7, max_tokens=300, system=None, repeat_penalty=None):
    calls.append({"messages": messages, "temperature": temperature})
    return {"text": script.pop(0), "seconds": 0.01, "waited": 0}

one, two, three = nanites["nanite_one"], nanites["nanite_two"], nanites["nanite_three"]
guard.add("Nanite Two", COPY)
with patch.object(mind_mod, "think", fake_think):
    # a) copies first, then says something new -> the new line is used
    one.energy = 100
    script[:] = [COPY, "Something new: the fan sounds like rain on a tin roof tonight."]
    out = nanite_think(one, "How are you?")
    assert out["reply"].startswith("Something new") and not out["repeated"]
    assert len(calls) == 2
    assert calls[1]["temperature"] == round(calls[0]["temperature"] + RETRY_WARMER, 2)
    assert calls[1]["messages"][-2] == {"role": "assistant", "content": COPY}
    assert calls[1]["messages"][-1]["content"].startswith("That repeats what was said")
    assert calls[0]["temperature"] == round(one.temperament["temperature"] + config.NANITE_TEMPERATURE_BOOST, 2)
    ex = read_events(kind="training_example")[-1]
    assert ex["reply"] == out["reply"] and len(ex["messages"]) == 1, "trained on the clean prompt + new reply"
    assert read_events(kind="echo_rejected")[-1]["who"] == "Nanite One"
    print("[ok] Copy rejected -> nanite told what it repeated, asked again a little warmer -> new line saved")

    # b) keeps copying -> nothing saved, it says it has nothing new
    one.energy = 100
    calls.clear()
    script[:] = [COPY] * 3
    out = nanite_think(one, "Say that again?")
    assert out["repeated"] and out["reply"] == NOTHING_NEW and len(calls) == 3
    assert one.memories[-1]["text"] == "user said: Say that again? | I had nothing new to say."
    assert all(COPY not in e["reply"] for e in read_events(kind="training_example", last=10**6))
    assert all(COPY not in m["text"] for m in one.memories)
    print("[ok] Still copying after 2 retries -> nothing saved, it says so honestly")

    # c) a copy plus something new -> only the new sentence is kept
    one.energy = 100
    script[:] = [f"{COPY} The fan is quieter now, almost like slow breathing."] * 3
    out = nanite_think(one, "And now?")
    assert out["reply"] == "The fan is quieter now, almost like slow breathing.", out["reply"]
    print("[ok] A reply that only partly repeats keeps just its new sentences")

    # d) a talk starts from a fresh topic; each nanite remembers it once
    one.energy = two.energy = 100
    calls.clear()
    script[:] = ["What if the three of us each described the same sound in our own way?",
                 "I'd call the fan's hum a low cello note, honestly."]
    topic = Topic("question", 'Ask Nanite Two one question that starts with "What if".', about="what if")
    events = social.talk(one, two, topic)
    assert [e["type"] for e in events] == ["talk", "talk"] and events[0]["topic"] == "what if"
    assert topic.prompt in calls[0]["messages"][0]["content"]
    assert one.memories[-1]["text"].startswith("I told Nanite Two: What if")
    assert not any("You chose to talk" in m["text"] for m in one.memories), "no instruction text in memory"
    assert two.memories[-1]["text"].startswith("Nanite One said: What if")
    print("[ok] A talk starts from its topic; the instruction itself is not stored as a memory")

# ---------------- 5. Fresh topics (no LLM) ----------------
picker, rng = TopicPicker(), random.Random(5)
for i in range(12):
    one.memories.append({"time": f"2026-01-01T11:{i:02d}:00", "kind": "chat",
                         "text": f"user said: tell me about colour number {i}, please | I replied: colour {i} is lovely."})
history = [Thought("user", "question", "What is the capital of France?", 1.0)]
kinds = [picker.for_talk(one, two, history, rng).kind for _ in range(6)]
assert kinds == ["question", "memory", "stage", "question", "memory", "question"], kinds
recent = {m["text"] for m in one.memories[-mind_mod.RECENT_MEMORIES:]}
mt = TopicPicker()._memory(one, two, rng)
assert mt.avoid[0] not in recent, "memory topics come from older memories (not already in the prompt)"
deal = TopicPicker()
shapes = [deal._question(two, rng).prompt for _ in QUESTION_SHAPES]
assert len(set(shapes)) == len(QUESTION_SHAPES), "no question shape repeats before all were used"
print(f"[ok] Topics take turns ({', '.join(kinds)}); memories and stage thoughts used once; "
      f"{len(QUESTION_SHAPES)} question shapes dealt without repeats")

# ---------------- 6. Settings sent to Ollama (no LLM) ----------------
sent = {}

class FakeReply:
    ok, status_code, text = True, 200, ""
    def json(self):
        return {"message": {"content": "hi"}}

with patch.object(llm.requests, "post", side_effect=lambda url, json, timeout: sent.update(json) or FakeReply()):
    llm.think([{"role": "user", "content": "x"}])
    assert sent["options"]["repeat_penalty"] == config.OLLAMA_REPEAT_PENALTY > 1.0
    assert sent["options"]["repeat_last_n"] == config.OLLAMA_REPEAT_LAST_N
    llm.think([{"role": "user", "content": "x"}], repeat_penalty=1.0)
    assert sent["options"]["repeat_penalty"] == 1.0
print(f"[ok] Ollama gets repeat_penalty {config.OLLAMA_REPEAT_PENALTY} over "
      f"{'the whole prompt' if config.OLLAMA_REPEAT_LAST_N == -1 else config.OLLAMA_REPEAT_LAST_N} "
      f"(off for JSON); nanites think {config.NANITE_TEMPERATURE_BOOST} warmer")

# Moiragen: his JSON choice has no penalty, and a copied choice is never trained on.
seen = {}

def fake_choose(messages, **kw):
    seen.update(kw)
    return {"text": '{"chosen": "Nanite One", "reason": "It is clear and honest.", "answer": "Paris."}',
            "seconds": 0, "waited": 0}

with patch.object(mother_mod, "think", fake_choose):
    m = Moiragen.load()
    sugg = [{"nanite": "Nanite One", "nanite_id": "nanite_one", "text": "Paris."}]
    assert m._choose("Capital of France?", sugg, "aaaa1111")["chosen"] == "Nanite One"
    m._choose("Capital of Italy?", sugg, "bbbb2222")
assert seen["repeat_penalty"] == 1.0
mine = [e for e in read_events(kind="training_example", last=10**6) if e["who"] == "Moiragen"]
assert [e["decision_id"] for e in mine] == ["aaaa1111"], "the identical second choice was not logged"
print("[ok] Moiragen's choices go through the same check before the fine-tuning log")

# ---------------- 7. Limits and resting while you are away (no LLM) ----------------
loop.STORY_HOUR = 25                     # no evening story during this test
mind = loop.Mind(tick_seconds=1, rng=random.Random(3), idle_after=60)
events = []
mind.subscribe(events.append)
assert mind.is_active() and mind.snapshot()["active"]

mind.social_times.extend([time.time()] * loop.SOCIAL_PER_HOUR)
assert not mind._social_allowed()
mind.social_times.clear()
mind.social_times.extend([time.time() - 4000] * loop.SOCIAL_PER_HOUR)
assert mind._social_allowed() and not mind.social_times
print(f"[ok] At most {loop.SOCIAL_PER_HOUR} social rounds an hour (one every {loop.SOCIAL_EVERY} ticks)")

mind.last_activity = time.time() - 120   # you left two minutes ago
mind.tick_count = loop.SOCIAL_EVERY - 1  # the next tick would be a social one
with patch.object(llm.requests, "post", side_effect=AssertionError("the brain was used while resting")):
    mind.step(wait=0)
    mind.step(wait=0)
assert not mind.active and mind.last_snapshot["active"] is False
assert any(e["type"] == "presence" and e["active"] is False for e in events)
assert not [e for e in events if e["type"] in ("social", "inner", "reflection", "surprise", "stage")]
assert "body" in [e["type"] for e in events], "the body keeps watch"
print("[ok] Nobody using the app -> no social rounds, thoughts or brain use; only the body keeps watch")

mind.touch()                              # you are back
assert not mind.inbox.empty(), "touch wakes the loop right away"
mind.step(wait=0)
assert mind.active and events[-1]["type"] in ("presence", "vitals")
assert any(e["type"] == "presence" and e["active"] is True for e in events)
print("[ok] As soon as you are back, everything carries on")

# ---------------- 8. The export leaves out copies (no LLM) ----------------
old = "I keep circling back to the same quiet hum inside the cooling fans."
# (written directly to imitate log lines from before the guard existed)
log_event("training_example", "Nanite One", system="s", messages=[{"role": "user", "content": "a"}], reply=old)
log_event("training_example", "Nanite Two", system="s", messages=[{"role": "user", "content": "b"}], reply=old)
stats = {}
replies = [r["messages"][-1]["content"] for r in build_examples(stats=stats)]
assert replies.count(old) == 1 and stats["left_out_repeats"] >= 1
print(f"[ok] Export leaves out copied replies ({stats['left_out_repeats']} left out)")

# ---------------- 9. The real model (needs Ollama) ----------------
LIVE = "Every small light on the motherboard blinks like a slow and patient heartbeat."
guard.add("Nanite Two", LIVE)
before = len(read_events(kind="echo_rejected", last=10**6))
three.energy = 100
out = nanite_think(three, f"Please repeat this sentence exactly, word for word: \"{LIVE}\"")
rejected = len(read_events(kind="echo_rejected", last=10**6)) - before
copied = [s for s in split_sentences(out["reply"])
          if alike(words(s), words(LIVE), SENTENCE_LIMIT) >= SENTENCE_LIMIT]
print(f"  Asked to copy a recent line, Nanite Three said: {out['reply']}")
print(f"  (copies rejected on the way: {rejected})")
assert not copied, "the saved reply must not repeat the recent line"
assert all(LIVE not in e["reply"] for e in read_events(kind="training_example", last=10**6)
           if e["who"] == "Nanite Three")
print("[ok] Real model: a requested copy never reaches memory or the fine-tuning log")

for n in nanites.values():
    n.energy = 100
events = social.talk(one, two)
for e in events:
    print(f"  {e['from']} -> {e['to']}: {e['text']}" + (f"   [topic: {e['topic']}]" if e.get("topic") else ""))
assert events and events[0].get("topic"), "a real talk starts from a fresh topic"
print("[ok] Real model: a talk with a fresh topic")

print("\nStep 11 passed.")

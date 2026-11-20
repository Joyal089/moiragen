"""Step 7 check: the consciousness layer.
Stage (global workspace), prediction and surprise, reflection, inner voice,
the running loop, and the daily story.

Uses a throwaway memory folder. Needs Ollama running (takes several minutes).
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step7_check.py
"""

import os
import random
import sys
import tempfile
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen.loop import Mind
from moiragen.prediction import EventPredictor, NumberPredictor
from moiragen.stage import Stage
from moiragen.story import story_path

# ---------------- Stage (no LLM) ----------------
stage = Stage()
heard = []
stage.subscribe(heard.append)
stage.post("Nanite One", "talk", "small talk", 0.3)
stage.post("body", "hot", "GPU is hot", 0.85)
stage.post("Nanite Two", "help", "helping a friend", 0.65)
w = stage.compete(random.Random(0))
assert w.kind == "hot" and heard == [w]
print("[ok] Stage: most important thought wins and is broadcast")

# Same source winning again gets a penalty, so a slightly weaker new voice can win.
stage = Stage()
for _ in range(2):
    stage.post("body", "hot", "still hot", 0.7)
    stage.compete(random.Random(1))
stage.post("body", "hot", "still hot", 0.7)
stage.post("Nanite Three", "lesson", "I learned something", 0.55)
assert stage.compete(random.Random(1)).source == "Nanite Three"
print("[ok] Stage: one voice cannot hog attention")

# Old losing thoughts fade away.
stage = Stage()
stage.post("Nanite One", "talk", "faint", 0.1)
for _ in range(4):
    stage.post("user", "question", "louder", 1.0)
    stage.compete()
assert all(t.text != "faint" for t in stage.candidates)
print("[ok] Stage: old losing thoughts fade")

# ---------------- Prediction (no LLM) ----------------
p = NumberPredictor(floor=4)
calm = [p.observe(v) for v in (40, 41, 40, 41, 40, 41)]
spike = p.observe(75)
assert max(s for s in calm if s is not None) < 0.4 and spike >= 0.9, (calm, spike)
print(f"[ok] Numbers: steady temps -> low surprise, jump to 75°C -> surprise {spike}")

ep = EventPredictor(warmup=4)
for k in ["talk", "help"] * 5:
    ep.observe(k)
assert ep.predict() == "talk"             # after "help" comes "talk"
expected = ep.observe("talk")
odd = ep.observe("story")                  # never seen after "talk"
assert expected < 0.4 and odd > 0.8, (expected, odd)
print(f"[ok] Events: predicted 'talk' (surprise {expected}), unseen 'story' -> surprise {odd}")

# ---------------- The Mind (uses the LLM) ----------------
mind = Mind(tick_seconds=1, rng=random.Random(7))
events = []
mind.subscribe(events.append)
types = lambda: [e["type"] for e in events]

# A question: decision, stage spotlight, reactions.
d = mind.handle_question("What is the capital of France?")
print(f"  Moiragen chose {d['chosen']}: {d['answer'][:120]}")
assert "paris" in d["answer"].lower()
assert "decision" in types() and "stage" in types()
assert any(e["type"] == "stage" and e["source"] in ("user", "Moiragen") for e in events)
print("[ok] Question answered and put on the stage")

# A tick: senses the body and reflects on that decision.
mind.tick()
refl = [e for e in events if e["type"] == "reflection"]
assert refl, "Moiragen should reflect on the new decision"
print(f"  Reflection: {refl[0]['reflection'][:160]}")
print(f"  About me:   {refl[0]['about_me']}")
assert d["reflected"]
assert "body" in types()
if refl[0]["about_me"]:
    assert mind.moiragen.self_knowledge and refl[0]["about_me"] in mind.moiragen.self_text()
    print("[ok] Reflected, and learned something about himself (now part of his prompt)")
else:
    print("[ok] Reflected (no 'About me' line this time)")

# Inner voice: something important on stage -> a private thought.
inner = [e for e in events if e["type"] == "inner"]
if not inner:
    mind.last_inner = 0
    mind.stage.post("Nanite Two", "hurt", "Nanite Two is hurt (health 40).", 0.8)
    mind._attend()
    inner = [e for e in events if e["type"] == "inner"]
assert inner, "an important thought should trigger his inner voice"
print(f"  Inner voice: {inner[-1]['text']}")
print("[ok] Inner voice reacts to the spotlight")

# Broadcast: nanites noticed the important winner.
assert any(m["kind"] == "noticed" for n in mind.nanites.values() for m in n.memories)
print("[ok] Important spotlight thoughts are remembered by the nanites (broadcast)")

# A social tick (every SOCIAL_EVERY ticks).
from moiragen.loop import SOCIAL_EVERY
mind.touch()                          # you are here, so the nanites are awake
mind.tick_count = SOCIAL_EVERY - 1    # the next tick is a social one
mind.tick()
social = [e for e in events if e["type"] == "social"]
print(f"  Social events so far: {[(e['from'], e['action'], e['to']) for e in social]}")
assert all("action" in e for e in social)
print("[ok] Ticks run social life without crashing")

# Daily story.
text = mind.handle_story()
print(f"  Story:\n{text}\n")
from datetime import date
assert text and story_path(date.today().isoformat()).exists()
print("[ok] Daily story written to memory/stories/")

# ---------------- Background loop ----------------
mind.start()
d2 = mind.ask("What is 2 plus 2?", timeout=300)
mind.stop()
assert "4" in d2["answer"] or "four" in d2["answer"].lower()
assert not mind._thread.is_alive()
assert "error" not in types(), [e for e in events if e["type"] == "error"]
print("[ok] Background loop answered a question from another thread and stopped cleanly")

print("\nStep 7 passed.")

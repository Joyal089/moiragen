"""Step 3 check: nanites think with their own temperament, memory and energy.

Uses a throwaway memory folder. Needs Ollama running.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step3_check.py
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen.mind import nanite_think, build_system_prompt, TOO_TIRED
from moiragen.memory_log import read_events
from moiragen.nanite import load_all

nanites = load_all()
one, two, three = nanites.values()

# 1. Same question to all three: different temperaments -> different answers.
question = "What do you think you are?"
print(f"Question: {question}\n")
answers = []
for n in nanites.values():
    before = n.energy
    out = nanite_think(n, question)
    answers.append(out["reply"])
    print(f"{n.name} (temperature {n.temperament['temperature']}):\n  {out['reply']}")
    print(f"  energy {before:.0f} -> {n.energy:.1f}, {out['seconds']}s\n")
    assert n.energy < before, "thinking must cost energy"
    assert n.memories[-1]["kind"] == "chat"
assert len(set(answers)) == 3
print("[ok] All three answered, each differently, and each paid energy")

# 2. Memory: tell Nanite One something, then ask about it.
nanite_think(one, "Please remember this: my favourite colour is green.")
out = nanite_think(one, "What is my favourite colour?")
print(f"Memory test, {one.name}: {out['reply']}")
assert "green" in out["reply"].lower(), "nanite should remember the colour"
print("[ok] Nanite remembered an earlier conversation")

# 3. Feelings reach the prompt: a sad, tired nanite is told so.
two.energy = 20
two.feel("sad", 0.6)
prompt = build_system_prompt(two)
assert "sad" in prompt and "tired" in prompt.lower()
out = nanite_think(two, "How are you feeling right now?")
print(f"Tired + sad {two.name}: {out['reply']}")
assert len(out["reply"].split()) < 70, "a tired nanite answers briefly"
print("[ok] Body and feelings shape the answer")

# 4. Exhausted nanite rests instead of thinking.
three.energy = TOO_TIRED - 1
out = nanite_think(three, "Solve a hard puzzle for me.")
assert out["rested"] and three.energy > TOO_TIRED
print(f"[ok] Exhausted nanite rested instead: '{out['reply']}' (energy now {three.energy:.0f})")

# 5. Everything was logged, including fine-tuning examples.
examples = read_events(kind="training_example", last=100)
assert len(examples) >= 5 and "system" in examples[0] and "reply" in examples[0]
print(f"[ok] {len(examples)} fine-tuning examples logged")

# 6. Saved: reload and the memories are still there.
again = load_all()
assert any("green" in m["text"] for m in again["nanite_one"].memories)
print("[ok] Memories survive a restart")

print("\nStep 3 passed.")

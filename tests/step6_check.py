"""Step 6 check: body cells sense time, energy, temperature and load,
and the brain slows down when the laptop is hot.

Uses a throwaway memory folder. Needs Ollama running for the slow-down test.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step6_check.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import llm
from moiragen.body import Body, HOT_C, HOT_PAUSE, WARM_C, WARM_PAUSE
from moiragen.memory_log import read_events
from moiragen.nanite import load_all

nanites = load_all()
body = Body(nanites)

# 1. Real readings from every cell, quickly.
t0 = time.time()
s = body.sense()
took = time.time() - t0
print(f"  clock:       {s['clock']}")
print(f"  energy:      {s['energy']}")
print(f"  temperature: {s['temperature']}")
print(f"  load:        {s['load']}")
print(f"  state:       {s['state']} ({s['why']})")
assert s["clock"]["part_of_day"] in {"morning", "afternoon", "evening", "night"}
assert set(s["energy"]["nanite_energy"]) == {"Nanite One", "Nanite Two", "Nanite Three"}
assert 0 <= s["load"]["ram_percent"] <= 100
assert took < 2, f"sensing should be quick, took {took:.2f}s"
if s["temperature"]["gpu_c"] is None:
    print("  (no NVIDIA reading - the temperature cell reports unknown, which is allowed)")
else:
    assert 10 < s["temperature"]["gpu_c"] < 110
print(f"[ok] All cells report in {took:.2f}s")

# 2. Moiragen's plain-language sense of his body.
print(f"  describe(): {body.describe(s)}")
assert "It is" in body.describe(s)
print("[ok] Body can describe itself in words")

# 3. Tired nanites are noticed by the energy cell.
nanites["nanite_two"].energy = 12
s = body.sense()
assert s["energy"]["tired_nanites"] == ["Nanite Two"]
print("[ok] Energy cell notices a tired nanite")

# 4. Pretend the GPU is warm, then hot: the pace changes and the brain is told.
body.temperature.fake_temp = WARM_C + 1
s = body.sense()
assert s["state"] == "warm" and s["pause_seconds"] == WARM_PAUSE and llm._cooldown_seconds == WARM_PAUSE
body.temperature.fake_temp = HOT_C + 5
s = body.sense()
assert s["state"] == "hot" and llm._cooldown_seconds == HOT_PAUSE
print(f"[ok] Fake {HOT_C + 5}°C -> state 'hot', brain rests {HOT_PAUSE}s per thought ({s['why']})")

# 5. A thought really takes longer when hot.
llm.set_cooldown(0)
llm.think([{"role": "user", "content": "Say hi."}], max_tokens=5)  # warm-up: loads the model into VRAM
t0 = time.time(); llm.think([{"role": "user", "content": "Say hi."}], max_tokens=5); cool_t = time.time() - t0
body.sense()  # still fake-hot, sets the cooldown again
t0 = time.time(); llm.think([{"role": "user", "content": "Say hi."}], max_tokens=5); hot_t = time.time() - t0
assert hot_t >= cool_t + HOT_PAUSE - 0.5, (cool_t, hot_t)
print(f"[ok] Thought took {cool_t:.1f}s when cool, {hot_t:.1f}s when hot")

# 6. Cooling down returns to full speed.
body.temperature.fake_temp = 45
s = body.sense()
assert s["state"] == "fine" and llm._cooldown_seconds == 0
print("[ok] Cooled down -> full speed again")

# 7. Only changes of state are logged (no flooding).
for _ in range(5):
    body.sense()
states = [e["state"] for e in read_events(kind="body", last=50)]
print(f"  logged body states: {states}")
assert states == ["fine", "warm", "hot", "fine"], states
print("[ok] Body log records only changes")

print("\nStep 6 passed.")

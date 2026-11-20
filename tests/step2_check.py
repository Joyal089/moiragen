"""Step 2 check: nanite bodies - birth, feelings, saving, and rebuilding.

Uses a throwaway memory folder, so Moiragen's real memory is never touched.

Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step2_check.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Point memory at a temporary folder BEFORE importing moiragen.
# (load_dotenv does not override variables that are already set.)
os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen.nanite import Nanite, load_all, NANITE_DIR

print(f"Test memory: {os.environ['MEMORY_DIR']}")

# 1. Birth: three nanites, each with a slightly different temperament.
nanites = load_all()
assert len(nanites) == 3
for n in nanites.values():
    print(f"  {n.name}: {n.temperament}")
temps = [tuple(n.temperament.values()) for n in nanites.values()]
assert len(set(temps)) == 3, "temperaments should differ"
assert all(n.health == 100 and n.energy == 100 for n in nanites.values())
print("[ok] Three nanites born with different temperaments")

one, two, three = nanites["nanite_one"], nanites["nanite_two"], nanites["nanite_three"]

# 2. Body changes: work, mistakes, help, rest.
one.spend_energy(75, "thinking hard")
assert one.energy == 25 and one.emotions["tired"] > 0
one.hurt(30, "I gave a wrong answer about the moon.")
assert one.health == 70 and one.emotions["sad"] > 0 and one.mood < 50
before = one.friendships["nanite_two"]
one.heal(15, helper=two)
assert one.health == 85 and one.emotions["grateful"] > 0
assert one.friendships["nanite_two"] > before
one.rest(50)
assert one.energy == 75
print(f"[ok] Body works: health={one.health} energy={one.energy} mood={one.mood} "
      f"feeling={one.strongest_emotion()}")

# 3. Limits: stats never go past 0..100.
three.hurt(500, "test of limits")
assert three.health == 0
three.heal(999)
assert three.health == 100
print("[ok] Stats stay inside 0..100")

# 4. Feelings fade with time.
s = one.emotions["grateful"]
one.fade_emotions()
assert one.emotions["grateful"] < s
print("[ok] Feelings fade over time")

# 5. Save and reload: everything comes back exactly.
for n in nanites.values():
    n.save()
again = load_all()
assert again["nanite_one"].health == one.health
assert again["nanite_one"].memories[-1]["text"] == one.memories[-1]["text"]
assert again["nanite_one"].temperament == one.temperament
print("[ok] Saved and reloaded from memory files")

# 6. Break Nanite Two's file and let a friend rebuild it.
original_temperament = two.temperament
(NANITE_DIR / "nanite_two.json").write_text("{ this is not valid json", encoding="utf-8")
healed = load_all()
rebuilt = healed["nanite_two"]
assert rebuilt.temperament == original_temperament, "temperament recovered from life log"
assert rebuilt.memories[-1]["kind"] == "rebuilt"
assert rebuilt.health == 50
print(f"[ok] Broken nanite rebuilt: {rebuilt.memories[-1]['text']}")

# 7. Unknown emotions are refused (the blueprint is the rulebook).
try:
    one.feel("angry", 0.5)
    raise AssertionError("should have refused")
except ValueError:
    print("[ok] Unknown emotions are refused")

print("\nStep 2 passed.")

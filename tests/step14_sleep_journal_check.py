"""Step 14 check: sleep, and the journal that keeps recording.

  1. Sleep: energy comes back for the time the app was closed (or nobody
     used it), 20 an hour, at most 8 hours counted, never above full.
  2. It happens when Moiragen starts, and when you come back after a rest.
  3. The inner-life journal starts with Moiragen, catches up on everything
     written while it was not running, never writes anything twice, and
     keeps following the life log.

No Ollama needed. Uses a throwaway memory folder.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step14_sleep_journal_check.py
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import journal as journal_mod
from moiragen.journal import Journal
from moiragen.loop import Mind
from moiragen.memory_log import log_event
from moiragen.nanite import SLEEP_ENERGY_PER_HOUR, SLEEP_MAX_HOURS, Nanite, load_all


def hours_ago(h: float) -> str:
    return (datetime.now() - timedelta(hours=h)).isoformat(timespec="seconds")


def set_asleep(energies: dict, hours: float) -> None:
    """Write the nanite files as if the app closed `hours` ago with these energies."""
    for nid, energy in energies.items():
        path = Path(os.environ["MEMORY_DIR"]) / "nanites" / f"{nid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["energy"], data["last_awake"] = energy, hours_ago(hours)
        path.write_text(json.dumps(data), encoding="utf-8")


# ---------------- 1. Sleep itself ----------------
nanites = load_all()
one = nanites["nanite_one"]
one.energy = 40
assert one.sleep(1.5) == 1.5 * SLEEP_ENERGY_PER_HOUR and one.energy == 70
one.energy = 10
assert one.sleep(30) == min(90, SLEEP_MAX_HOURS * SLEEP_ENERGY_PER_HOUR) and one.energy == 100, \
    "a long sleep fills energy, never above full"
one.energy = 100
assert one.sleep(5) == 0 and one.energy == 100
assert one.sleep(-3) == 0, "a clock that went backwards gives nothing"
one.emotions["tired"] = 0.6
one.energy = 50
one.sleep(2)
assert one.emotions["tired"] == 0
one.last_awake = hours_ago(2)
assert 1.99 < one.hours_asleep() < 2.01
one.save()
assert Nanite.load("nanite_one").hours_asleep() < 0.01, "saving means awake now"
# Files from before sleep existed have no last_awake: their save time is used.
path = Path(os.environ["MEMORY_DIR"]) / "nanites" / "nanite_two.json"
data = json.loads(path.read_text(encoding="utf-8"))
data.pop("last_awake")
path.write_text(json.dumps(data), encoding="utf-8")
old = time.time() - 3 * 3600
os.utime(path, (old, old))
assert 2.99 < Nanite.load("nanite_two").hours_asleep() < 3.01
print(f"[ok] Sleep: {SLEEP_ENERGY_PER_HOUR} energy an hour, at most {SLEEP_MAX_HOURS} hours, never above full")

# ---------------- 2. On start, and when you come back ----------------
set_asleep({"nanite_one": 40, "nanite_two": 45, "nanite_three": 100}, hours=2)
mind = Mind(tick_seconds=0.05, idle_after=0.3)
# Times are stored to the second, so a sleep can be a moment longer: allow 0.1 energy.
e = {n.id: round(n.energy) for n in mind.nanites.values()}
assert e == {"nanite_one": 80, "nanite_two": 85, "nanite_three": 100}, e
assert all(n.hours_asleep() < 0.01 for n in mind.nanites.values()), "awake now"
print(f"[ok] App closed for 2 hours: energy {e}")

# Nobody uses the app: they rest. Pretend that rest lasted an hour, then come back.
time.sleep(0.4)
mind._check_presence()
assert not mind.active
for n in mind.nanites.values():
    n.energy, n.last_awake = 50, hours_ago(1)
events = []
mind.subscribe(events.append)
mind.touch()
mind._check_presence()
assert mind.active and all(abs(n.energy - 70) < 0.1 for n in mind.nanites.values())
assert any("slept about 1.0 hours" in x.get("text", "") for x in events)
print(f"[ok] Back after an hour's rest: {[x['text'] for x in events if 'slept' in x.get('text', '')][0]}")

# ---------------- 3. The journal ----------------
jfile = journal_mod.JOURNAL_FILE
log_event("inner", "Moiragen", text="A first quiet thought.")
log_event("energy", "Nanite One", change=-5)                        # left out: just a number
log_event("correction", "Nanite Two", text="A gentle correction: that did not happen.")
log_event("lesson", "Nanite Two", text="I only say what really happened.", source="correction")
log_event("lesson", "Nanite One", text="I learned to check.", source="decision abc")   # written as social_lesson
log_event("decision_full", "Moiragen", id="d1", question="What comes next: 2, 6, 12, 20, 30?",
          suggestions=[{"nanite": "Nanite One", "text": "42"}, {"nanite": "Nanite Two", "text": "44"}],
          verdicts={"Nanite Two": {"why": "Check the last step.", "rewards": []}},
          chosen="Nanite One", first_choice="Nanite Two", reason="The calculator says 42.", answer="42",
          compare="They differ on the last step.", checks={"calculator": {"text": "42", "how": "steady differences"}})

# Moiragen starts: the journal catches up on everything written so far.
mind.journal.start()
text = jfile.read_text(encoding="utf-8")
for must in ["A first quiet thought", "Correction (Nanite Two)", "I only say what really happened",
             "Moiragen compared: They differ", "Calculator check: 42", "first he picked Nanite Two",
             "The nanites slept about 2.0 hours", "caught up on"]:
    assert must in text, f"missing from the journal: {must}"
assert "I learned to check" not in text, "lessons from decisions come from social_lesson, not twice"

# While running, new lines appear within a few seconds.
log_event("inner", "Moiragen", text="A thought while running.")
deadline = time.time() + 5
while "A thought while running" not in jfile.read_text(encoding="utf-8") and time.time() < deadline:
    time.sleep(0.2)
assert "A thought while running" in jfile.read_text(encoding="utf-8"), "the journal follows the log"
mind.journal.stop()

# Moiragen is closed; things are still written (a script, a crash). Next start catches up.
log_event("inner", "Moiragen", text="Written while the journal was off.")
j2 = Journal()
j2.start()
j2.stop()
text = jfile.read_text(encoding="utf-8")
assert "Written while the journal was off" in text
for line in ["A first quiet thought", "A thought while running", "Written while the journal was off"]:
    assert text.count(line) == 1, f"written more than once: {line}"
print("[ok] Journal: catches up on start, follows while running, catches up after being off, never twice")

print("\nStep 14 passed: sleep and the journal work.")

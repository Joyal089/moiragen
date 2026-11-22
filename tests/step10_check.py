"""Step 10 check: training-data export, broken-memory recovery, and calm
behaviour when the brain (Ollama) is unreachable.

Uses a throwaway memory folder. Needs Ollama running.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step10_check.py
"""

import json
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
from moiragen.export import build_examples, export_training
from moiragen.loop import Mind
from moiragen.memory_log import log_event
from moiragen.mother import MOIRAGEN_FILE, Moiragen
from moiragen.nanite import load_all

# 1. A decision marked wrong, then export it as training data.
nanites = load_all()
m = Moiragen.load()
d = m.decide("Name one primary colour.", nanites)
m.feedback(d["id"], "wrong", nanites, reason="test")
path, summary = export_training()
print(f"  {json.dumps(summary)}")
rows = [json.loads(l) for l in open(path, encoding="utf-8")]
mine = [r for r in rows if r["decision_id"] == d["id"]]
assert len(mine) == 4, f"3 suggestions + 1 choice, got {len(mine)}"
assert all(r["messages"][0]["role"] == "system" and r["messages"][-1]["role"] == "assistant" for r in rows)
assert all(r["feedback"] == "wrong" for r in mine)
winners = [r["who"] for r in mine if r.get("chosen")]
assert winners == [d["chosen"]], winners
assert summary["life"]["decisions"] == 1 and summary["life"]["mistakes"] >= 1
print(f"[ok] Exported {summary['examples']} examples; the decision's 4 are labelled "
      f"'wrong' and only {d['chosen']}'s suggestion is marked chosen")
assert not any(r["decision_id"] == d["id"] for r in build_examples(skip_wrong=True))
print("[ok] --skip-wrong leaves out decisions marked wrong")

# 2. A damaged moiragen.json is kept and rebuilt from the life log.
log_event("reflection", "Moiragen", text="test reflection", about_me="I like clear answers.")
MOIRAGEN_FILE.write_text("{ broken", encoding="utf-8")
m2 = Moiragen.load()
assert "I like clear answers." in [k["text"] for k in m2.self_knowledge]
assert any(m["kind"] == "decision" for m in m2.memories)
assert list(MOIRAGEN_FILE.parent.glob("moiragen.broken-*.json")), "the broken file must be kept"
print("[ok] Damaged memory file kept aside; self-knowledge and memories rebuilt from the log")

# 3. The brain goes away: one calm error, he keeps running, then recovers.
mind = Mind(tick_seconds=0.1)
events = []
mind.subscribe(events.append)
real_host = llm.OLLAMA_HOST
llm.OLLAMA_HOST = "http://127.0.0.1:9"      # nothing listens there
mind.start()
deadline = time.time() + 30
while time.time() < deadline and not any(e["type"] == "error" for e in events):
    time.sleep(0.2)
errors = [e for e in events if e["type"] == "error"]
assert errors and "Ollama" in errors[0]["text"], errors
print(f"[ok] Brain unreachable -> calm message: \"{errors[0]['text']}\"")
time.sleep(3)
assert len([e for e in events if e["type"] == "error"]) == 1, "should not flood errors"
assert mind._thread.is_alive()
llm.OLLAMA_HOST = real_host                 # the brain comes back
deadline = time.time() + 120
while time.time() < deadline and not any("working again" in e.get("text", "") for e in events):
    time.sleep(0.5)
mind.stop()
assert any("working again" in e.get("text", "") for e in events)
print("[ok] No error flood, loop stayed alive, and recovered when the brain came back")

print("\nStep 10 passed.")

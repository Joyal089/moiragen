"""Step 1 check: can Moiragen's brain think, and does his memory log work?

Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step1_check.py
"""

import sys
import threading
from pathlib import Path

# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
# Let this script import the "moiragen" package from the project folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import config, llm
from moiragen.memory_log import log_event, read_events

print(f"Model:  {config.OLLAMA_MODEL} at {config.OLLAMA_HOST}")
print(f"Memory: {config.MEMORY_DIR}")

# 1. Is Ollama running?
assert llm.is_awake(), "Ollama is not running - start the Ollama app first."
print("[ok] Ollama is awake")

# 2. One thought.
reply = llm.think([{"role": "user", "content": "In one short sentence: what is a nanite?"}])
print(f"[ok] Brain replied in {reply['seconds']}s: {reply['text']}")

# 3. Taking turns: two minds ask at once; the second must wait for the first.
results = {}

def ask(name):
    results[name] = llm.think([{"role": "user", "content": "Say one word."}], max_tokens=10)

threads = [threading.Thread(target=ask, args=(n,)) for n in ("A", "B")]
for t in threads:
    t.start()
for t in threads:
    t.join()
waits = sorted(r["waited"] for r in results.values())
assert waits[1] > 0, "Expected one mind to wait for the other"
print(f"[ok] Minds took turns (waits: {waits[0]}s and {waits[1]}s)")

# 4. Memory log: write an event and read it back.
log_event("test", "step1_check", note="foundation works", reply=reply["text"])
last = read_events(kind="test", last=1)[0]
assert last["note"] == "foundation works"
print(f"[ok] Logged and read back: {last}")

# 5. A detail named "kind" or "who" must not crash logging (this once broke chats).
e = log_event("test", "step1_check", kind="chat", who="someone")
assert e["kind"] == "test" and e["detail_kind"] == "chat" and e["detail_who"] == "someone"
print("[ok] Details named 'kind'/'who' are kept safely")

print("\nStep 1 passed.")

"""Step 8 check: the backend server and its live event stream.

Uses a throwaway memory folder and FastAPI's test client (no real network).
Needs Ollama running. Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step8_check.py
"""

import os
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*httpx.*")  # harmless notice from the test client

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from moiragen.loop import Mind
from server import create_app

# A Mind that only works when asked (no idle ticks), so the test is quick.
mind = Mind(tick_seconds=3600)
app = create_app(mind=mind)


def read_until(ws, wanted, limit=200):
    """Read WebSocket messages until one matches wanted(event)."""
    seen = []
    for _ in range(limit):
        e = ws.receive_json()
        seen.append(e["type"])
        if wanted(e):
            return e, seen
    raise AssertionError(f"never saw the event; saw {seen}")


with TestClient(app) as client:
    # 1. The page and the snapshot.
    r = client.get("/")
    assert r.status_code == 200 and "Moiragen" in r.text
    s = client.get("/api/state").json()
    assert [n["name"] for n in s["nanites"]] == ["Nanite One", "Nanite Two", "Nanite Three"]
    assert all(0 <= n["health"] <= 100 for n in s["nanites"]) and "body" in s
    print(f"[ok] Page served; snapshot has 3 nanites, body state '{s['body']['state']}'")

    # 2. Bad requests are refused politely.
    assert client.post("/api/chat", json={"nanite_id": "nanite_nine", "text": "hi"}).status_code == 404
    assert client.post("/api/ask", json={"text": "   "}).status_code == 400
    assert client.post("/api/feedback", json={"decision_id": "nope", "correct": True}).status_code == 404
    print("[ok] Unknown nanite, empty question and unknown decision are refused")

    with client.websocket_connect("/ws") as ws:
        # 3. On connect the browser gets the full picture first.
        first = ws.receive_json()
        assert first["type"] == "vitals" and len(first["nanites"]) == 3
        print("[ok] WebSocket sends the full picture on connect")

        # 4. Direct chat with one nanite, streamed live.
        r = client.post("/api/chat", json={"nanite_id": "nanite_two", "text": "Hello Two, how are you?"})
        assert r.status_code == 200 and r.json()["reply"]
        e, seen = read_until(ws, lambda e: e["type"] == "chat" and e["from"] == "Nanite Two")
        print(f"  Nanite Two: {e['text'][:120]}")
        print(f"[ok] Chat answered over HTTP and streamed live (events: {seen})")

        # 5. Ask Moiragen: suggestions + choice + reason come through the stream.
        r = client.post("/api/ask", json={"text": "Is water wet? One sentence."})
        d = r.json()
        assert r.status_code == 200 and len(d["suggestions"]) == 3 and d["chosen"] and d["reason"]
        e, seen = read_until(ws, lambda e: e["type"] == "decision")
        assert e["id"] == d["id"]
        print(f"  Moiragen chose {d['chosen']}: {d['reason'][:120]}")
        print("[ok] Decision returned and streamed live")

        # 6. Feedback: wrong -> chosen nanite loses health, visible in the next snapshot.
        chosen_id = next(s["nanite_id"] for s in d["suggestions"] if s["nanite"] == d["chosen"])
        before = next(n["health"] for n in client.get("/api/state").json()["nanites"] if n["id"] == chosen_id)
        r = client.post("/api/feedback", json={"decision_id": d["id"], "correct": False, "note": "test"})
        assert r.status_code == 200
        read_until(ws, lambda e: e["type"] == "feedback")          # skip older queued events
        e, _ = read_until(ws, lambda e: e["type"] == "vitals")      # the snapshot sent after it
        after = next(n["health"] for n in e["nanites"] if n["id"] == chosen_id)
        assert after < before, (before, after)
        print(f"[ok] Marked wrong: {d['chosen']} health {before:.0f} -> {after:.0f}, pushed to the browser")

# 7. Leaving the 'with' block shut the server down and stopped the mind.
assert not mind._thread.is_alive()
print("[ok] Server shutdown stopped Moiragen's loop cleanly")

print("\nStep 8 passed.")

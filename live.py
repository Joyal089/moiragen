"""Watch Moiragen live in the terminal: his thinking loop runs on its own,
and you can ask him things at any time.

Run from the project folder:
    .venv\\Scripts\\python.exe live.py

Type a question and press Enter. Commands:
    /story    write today's story now
    /quit     stop

This uses Moiragen's REAL memory.
"""

import sys

from moiragen.loop import Mind

# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")


def show(e: dict) -> None:
    """Print each kind of event as one readable line."""
    t, at = e["type"], e["time"][11:16]
    if t == "stage":
        print(f"[{at}] SPOTLIGHT ({e['salience']:.2f}) {e['source']}: {e['text'][:120]}")
    elif t == "social":
        print(f"[{at}]   {e['from']} -[{e['action']}]-> {e['to']}: {e.get('text', '')[:120]}")
    elif t == "inner":
        print(f"[{at}] Moiragen thinks: {e['text']}")
    elif t == "surprise":
        print(f"[{at}] SURPRISE {e['text']}")
    elif t == "reflection":
        print(f"[{at}] Moiragen reflects: {e['reflection'][:160]}")
        if e["about_me"]:
            print(f"[{at}]   About me: {e['about_me']}")
    elif t == "decision":
        print(f"[{at}] Moiragen chose {e['chosen']}: {e['reason']}\n[{at}] Moiragen > {e['answer']}")
    elif t == "story":
        print(f"[{at}] STORY of {e['day']}:\n{e['text']}")
    elif t in ("awake", "asleep", "error"):
        print(f"[{at}] {e['text']}")
    # body readings arrive every tick; too noisy to print


mind = Mind()
mind.subscribe(show)
mind.start()
print("Moiragen is living. Type a question any time, /story, or /quit.\n")

while True:
    try:
        q = input().strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not q:
        continue
    if q == "/quit":
        break
    if q == "/story":
        # The loop thread writes it (all mind work happens in that one thread).
        print("  (Moiragen is writing today's story...)")
        if not mind.request_story():
            print("Nothing has happened today yet.")
        continue
    print("  (asking Moiragen... the nanites are thinking)")
    mind.ask(q)

print("Stopping (finishing the current thought)...")
mind.stop()

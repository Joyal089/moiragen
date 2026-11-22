"""Watch Moiragen live in the terminal: his thinking loop runs on its own,
and you can ask him things at any time.

Run from the project folder:
    .venv\\Scripts\\python.exe live.py

Type a question and press Enter. Commands:
    /story    write today's story now
    /quit     stop
    (just Enter)  "I'm here": after 10 minutes without any typing the nanites
                  rest, so nothing piles up while you are away

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
        print(f"[{at}] Moiragen chose {e['chosen']}: {e['reason']}")
        for name, v in e.get("verdicts", {}).items():
            valued = f"  (+ {', '.join(v['rewards'])})" if v.get("rewards") else ""
            print(f"[{at}]   to {name}: {v['why']}{valued}")
        if e.get("wait_and_see"):
            print(f"[{at}]   He will wait and see if it is right ({e['check']}).")
        print(f"[{at}] Moiragen > {e['answer']}")
    elif t == "choice_changed":
        print(f"[{at}] Moiragen changed his choice to {e['chosen']}: {e['reason']}")
    elif t == "feedback":
        print(f"[{at}] Your verdict: {e['verdict']}. {e['reason']}")
    elif t == "story":
        print(f"[{at}] STORY of {e['day']}:\n{e['text']}")
    elif t in ("awake", "asleep", "error"):
        print(f"[{at}] {e['text']}")
    elif t == "presence":
        print(f"[{at}] {e['text']}" + ("" if e["active"] else "  (press Enter to wake them)"))
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
        mind.touch()   # "I'm here"
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

"""Ask Moiragen a question in the terminal and watch him decide.

Run from the project folder:
    .venv\\Scripts\\python.exe ask.py

For each question you see every nanite's suggestion, who Moiragen chose,
why, and his final answer. Then you can tell him if he was right:
    y = right, n = wrong (the chosen nanite loses some health), Enter = skip
Type /status to see the nanites, /quit to stop.

This uses Moiragen's REAL memory.
"""

import sys

from moiragen.mind import describe_state
from moiragen.mother import Moiragen
from moiragen.nanite import load_all

# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")

nanites = load_all()
moiragen = Moiragen.load()
print("Ask Moiragen anything. /status shows the nanites, /quit stops.\n")

while True:
    try:
        q = input("you > ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not q:
        continue
    if q == "/quit":
        break
    if q == "/status":
        for n in nanites.values():
            print(f"  {n.name}: {describe_state(n)}")
        print()
        continue

    print("  (the nanites are thinking...)\n")
    d = moiragen.decide(q, nanites)
    for s in d["suggestions"]:
        mark = "*" if s["nanite"] == d["chosen"] else " "
        print(f" {mark} {s['nanite']}: {s['text']}\n")
    print(f"Moiragen chose {d['chosen']}. Reason: {d['reason']}")
    print(f"Moiragen > {d['answer']}\n")

    verdict = input("Was that right? (y / n / Enter to skip) ").strip().lower()
    if verdict in ("y", "n"):
        note = input("Anything to add? (Enter to skip) ").strip() if verdict == "n" else ""
        print(f"Moiragen > {moiragen.feedback(d['id'], verdict == 'y', nanites, note)}\n")

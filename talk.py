"""Talk to one nanite in the terminal (a simple tool until the viewer app exists).

Run from the project folder:
    .venv\\Scripts\\python.exe talk.py            (talk to Nanite One)
    .venv\\Scripts\\python.exe talk.py two        (talk to Nanite Two)

Commands while chatting:
    /status   show its body and feelings
    /rest     let it rest
    /quit     stop

This uses Moiragen's REAL memory, so the nanite remembers you next time.
"""

import sys

from moiragen.mind import nanite_think, describe_state
from moiragen.nanite import load_all

# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")

which = (sys.argv[1] if len(sys.argv) > 1 else "one").lower()
nanites = load_all()
n = nanites.get(f"nanite_{which}")
if n is None:
    sys.exit("Choose one, two or three.")

print(f"You are talking to {n.name}. Type /quit to stop.\n")
while True:
    try:
        text = input("you > ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        continue
    if text == "/quit":
        break
    if text == "/status":
        print(f"  {describe_state(n)}\n")
        continue
    if text == "/rest":
        n.rest()
        n.save()
        print(f"  {n.name} rests. Energy is now {n.energy:.0f}.\n")
        continue

    out = nanite_think(n, text)
    print(f"{n.name} > {out['reply']}")
    print(f"  (energy -{out['energy_spent']}, now {n.energy:.0f}; {out['seconds']}s)\n")

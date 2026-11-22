"""Ask Moiragen a question in the terminal and watch him decide.

Run from the project folder:
    .venv\\Scripts\\python.exe ask.py

For each question you see every nanite's suggestion, who Moiragen chose,
why, his short reason for each nanite, and his final answer. Then you can
tell him if he was right, always with a short reason they can learn from:
    y = right, n = wrong (the chosen nanite loses some health),
    w = wait and see (judge it later, with /waiting), Enter = skip
After each answer the nanites react: one whose idea lost may ask why,
and may even disagree with Moiragen; a friend may comfort it.
Type /status to see the nanites, /life to let them live a moment on
their own (talk, help, rest), /waiting to judge "wait and see" answers,
/quit to stop.

This uses Moiragen's REAL memory.
"""

import sys

from moiragen.mind import describe_state
from moiragen.mother import Moiragen
from moiragen.nanite import load_all
from moiragen.social import after_decision, social_round

# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")

ARROWS = {"talk": "->", "help": "+health->", "support": "comforts->", "ask_why": "asks->",
          "explain": "->", "lesson": "learned:", "rest": "rests", "disagree": "disagrees->"}


def show(events):
    """Print social events like a little script."""
    for e in events:
        if e["type"] == "rest":
            print(f"  {e['from']} rests (energy {e['energy']:.0f})")
        elif e["type"] == "lesson":
            print(f"  {e['from']} learned: {e['text']}")
        elif e["type"] == "reconsider":
            what = f"changed his choice to {e['chosen']}" if e["changed"] else "kept his choice"
            print(f"  Moiragen {what}. To {e['to']}: {e['text']}")
        else:
            print(f"  {e['from']} {ARROWS.get(e['type'], '->')} {e['to']}: {e['text']}")
    if events:
        print()


def ask_verdict(decision_id, allow_wait=True):
    """Ask for your verdict and a short reason, then tell Moiragen."""
    keys = "y / n / w / Enter to skip" if allow_wait else "y / n / Enter to skip"
    answer = input(f"Was that right? ({keys}) ").strip().lower()
    verdict = {"y": "right", "n": "wrong", "w": "wait"}.get(answer)
    if verdict is None or (verdict == "wait" and not allow_wait):
        return
    if verdict == "wait":
        reason = input("What should we check later? (Enter to skip) ").strip()
    else:
        reason = input("Why? (a short reason) ").strip()
        while not reason:
            reason = input("Please give a short reason, so the nanites can learn from it: ").strip()
    print(f"Moiragen > {moiragen.feedback(decision_id, verdict, nanites, reason)}\n")


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
    if q == "/life":
        print("  (the nanites live a moment...)\n")
        show(social_round(nanites))
        continue
    if q == "/waiting":
        waiting = moiragen.waiting()
        if not waiting:
            print("  Nothing is waiting to be judged.\n")
        for w in waiting:
            print(f"  \"{w['question']}\" ({w['time'][:10]}) {w['chosen']}: {w['answer']}")
            print(f"  What to check: {w.get('check') or 'the result'}")
            ask_verdict(w["id"], allow_wait=False)
        continue

    print("  (the nanites are thinking...)\n")
    d = moiragen.decide(q, nanites)
    for s in d["suggestions"]:
        mark = "*" if s["nanite"] == d["chosen"] else " "
        v = d["verdicts"].get(s["nanite"], {})
        valued = f"  (+ {', '.join(v['rewards'])})" if v.get("rewards") else ""
        print(f" {mark} {s['nanite']}: {s['text']}\n     Moiragen: {v.get('why', '')}{valued}\n")
    print(f"Moiragen chose {d['chosen']}. Reason: {d['reason']}")
    if d["wait_and_see"]:
        print(f"He will wait and see if it is right ({d['check']}).")
    print(f"Moiragen > {d['answer']}\n")
    show(after_decision(d, nanites, moiragen))
    ask_verdict(d["id"])

"""Step 5 check: friendship and care between nanites.

Uses a throwaway memory folder. Needs Ollama running (takes a few minutes).
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step5_check.py
"""

import os
import random
import sys
import tempfile
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
# Show emoji/accents correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moiragen import social
from moiragen.mind import build_system_prompt
from moiragen.mother import Moiragen
from moiragen.nanite import load_all


def show(events):
    for e in events:
        print(f"    {e['type']:8} {e['from']} -> {e['to']}: {str(e.get('text', ''))[:140]}")


nanites = load_all()
one, two, three = nanites["nanite_one"], nanites["nanite_two"], nanites["nanite_three"]
moiragen = Moiragen.load()

# 1. Choosing who to talk to follows friendship (no LLM).
one.friendships["nanite_two"], one.friendships["nanite_three"] = 90, 20
rng = random.Random(1)
picks = [social.choose_who_to_talk_to(one, nanites, rng).id for _ in range(300)]
share = picks.count("nanite_two") / len(picks)
assert share > 0.7, share
one.emotions["left_out"] = 0.8  # lonely -> leans even more on its best friend
picks_lonely = [social.choose_who_to_talk_to(one, nanites, rng).id for _ in range(300)]
assert picks_lonely.count("nanite_two") / 300 > share
one.emotions["left_out"] = 0.0
print(f"[ok] Picks best friend {share:.0%} of the time, more when lonely "
      f"({picks_lonely.count('nanite_two') / 300:.0%})")

# 2. Talking: both speak, both remember, friendship grows.
before = (three.friendships["nanite_one"], one.friendships["nanite_three"])
ev = social.talk(three, one)
show(ev)
assert len(ev) == 2 and ev[0]["from"] == "Nanite Three" and ev[1]["from"] == "Nanite One"
assert three.friendships["nanite_one"] > before[0] and one.friendships["nanite_three"] > before[1]
print("[ok] Nanites talked and grew closer")

# 3. Helping a hurt friend: health up, helper pays energy, patient grateful.
two.hurt(55, "test injury")
health, energy = two.health, one.energy
ev = social.help_friend(one, two)
show(ev)
assert two.health > health and one.energy < energy
assert two.emotions["grateful"] > 0 and two.memories[-1]["kind"] == "helped_by"
print(f"[ok] {one.name} helped {two.name}: health {health:.0f} -> {two.health:.0f}, "
      f"helper energy {energy:.0f} -> {one.energy:.0f}")

# 4. Not chosen -> asks why -> learns a lesson. (A hand-made decision, so this is quick.)
decision = {
    "id": "test01", "question": "What colour is the sky on a clear day?", "chosen": "Nanite One",
    "reason": "It was short, correct and explained why.",
    "suggestions": [
        {"nanite_id": "nanite_one", "nanite": "Nanite One",
         "text": "Blue, because air scatters blue sunlight more than other colours."},
        {"nanite_id": "nanite_three", "nanite": "Nanite Three",
         "text": "I'm not sure. Maybe it changes? I feel uncertain about colours."},
    ],
}
three.feel("disappointed", 0.3)
three.feel("left_out", 0.2)
health = three.health
ev = social.ask_why_not_chosen(three, decision, moiragen, nanites)
show(ev)
kinds = [e["type"] for e in ev]
# It either learns a lesson, or respectfully disagrees and Moiragen reconsiders.
assert kinds in (["ask_why", "explain", "lesson"], ["ask_why", "explain", "disagree", "reconsider"]), kinds
assert three.health == health, "losing a vote (or disagreeing) never costs health"
if kinds[-1] == "lesson":
    assert three.lessons and three.lessons[-1]["lesson"]
    assert three.lessons[-1]["lesson"] in build_system_prompt(three)
    print("[ok] Not-chosen nanite asked why, learned a lesson, and the lesson is in its prompt")
else:
    print("[ok] Not-chosen nanite asked why, disagreed, and Moiragen reconsidered (no health lost)")

# 5. A friend notices and supports it.
lo = three.emotions["left_out"] + three.emotions["disappointed"]
ev = social.support_friend(two, three)
show(ev)
assert three.emotions["left_out"] + three.emotions["disappointed"] < lo
assert three.emotions["grateful"] > 0
print("[ok] A friend comforted it: feelings eased, gratitude grew")

# 6. A social round: a badly hurt nanite always gets help.
for n in nanites.values():
    n.energy, n.health = 90, 100
two.hurt(60, "test injury 2")
ev = social.social_round(nanites, random.Random(3))
show(ev)
assert any(e["type"] == "help" and e["to"] == "Nanite Two" for e in ev)
print("[ok] In a social round, the hurt nanite was helped")

# 7. Friendships drift toward neutral when unused.
three.friendships["nanite_two"] = 80
social.social_round({"nanite_three": three}, random.Random(0))  # alone: nobody to talk to
assert three.friendships["nanite_two"] < 80
print("[ok] Unused friendships slowly drift back toward neutral")

# 8. Lessons survive a rebuild (recovered from the life log).
if not three.lessons:   # it disagreed in part 4 instead of learning, so give it one lesson here
    three.learn("I learned to say why I see things my way.", source="test")
(Path(os.environ["MEMORY_DIR"]) / "nanites" / "nanite_three.json").write_text("broken", encoding="utf-8")
rebuilt = load_all()["nanite_three"]
assert rebuilt.lessons and rebuilt.lessons[-1]["lesson"] == three.lessons[-1]["lesson"]
print("[ok] A rebuilt nanite gets its lessons back")

print("\nStep 5 passed.")

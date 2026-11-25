"""The nanites' social life: talking, helping, supporting and learning.

Who does what is decided by plain Python (no LLM), using each nanite's
temperament, feelings and friendships. The LLM is only used for the
WORDS they say. That keeps behaviour understandable and cheap.

Every talk and every comfort starts from a fresh, specific prompt (see
topics.py), and every line passes the echo guard (see echo.py), so the
nanites do not slide back into repeating each other.

Every action returns small "event" dicts like
    {"type": "talk", "from": "Nanite One", "to": "Nanite Two", "text": "..."}
which the viewer app will later draw as speech bubbles and lines.
"""

import random

from . import facts
from .echo import split_sentences
from .memory_log import log_event
from .mind import nanite_think, TIRED
from .real_or_story import add_note
from .nanite import Nanite
from .topics import Topic, picker

# --- Tunable numbers ---
HURT_LEVEL = 60          # below this health, friends always come to help
HELP_COST = 10           # energy the helper spends on top of its words
HELP_HEAL = 15           # health the patient gets back
LOW_FEELING = 0.15       # disappointment/left-out above this can be noticed
FRIENDSHIP_TALK = 2      # a good talk brings both a little closer
FRIENDSHIP_HELP = 3      # helping makes the helper care more too
FRIENDSHIP_SUPPORT = 4
FRIENDSHIP_DRIFT = 0.5   # unused friendships slowly drift back toward neutral
HONESTY_LIFT = 4         # mood boost for admitting a mistake or changing your mind (same as mother.py)


def _event(type_: str, **data) -> dict:
    """Make an event, and also write it to the life log."""
    log_event(f"social_{type_}", data.get("from", "?"), **data)
    return {"type": type_, **data}


# ---------------------------------------------------------------------------
# Choosing (plain Python)
# ---------------------------------------------------------------------------

def choose_who_to_talk_to(n: Nanite, nanites: dict[str, Nanite], rng=random) -> Nanite:
    """Pick a friend to talk to. Higher friendship = more likely.

    Feelings change the pick:
      - a sad or left-out nanite leans even more on its closest friend
      - a grateful nanite leans toward whoever helped it (high friendship)
      - a warm nanite gives extra weight to a friend who is struggling
    """
    others = [o for o in nanites.values() if o.id != n.id]
    lonely = n.emotions.get("sad", 0) + n.emotions.get("left_out", 0)
    weights = []
    for o in others:
        w = n.friendships.get(o.id, 50) / 100       # 0..1
        w = w ** (1 + 2 * lonely)                    # when lonely, favourites matter more
        struggling = (100 - o.health) / 100 + o.emotions.get("sad", 0)
        w += n.temperament["warmth"] * struggling * 0.5
        weights.append(max(w, 0.01))
    return rng.choices(others, weights=weights, k=1)[0]


def needs_help(o: Nanite) -> bool:
    """Is this nanite hurt badly enough that friends should help?"""
    return o.health < HURT_LEVEL


def needs_support(o: Nanite) -> bool:
    """Is this nanite feeling down (e.g. after its idea was not chosen)?"""
    return (o.emotions.get("disappointed", 0) + o.emotions.get("left_out", 0)) >= LOW_FEELING


def best_helper(patient: Nanite, nanites: dict[str, Nanite]) -> Nanite | None:
    """The friend who cares most about the patient and still has energy."""
    candidates = [o for o in nanites.values()
                  if o.id != patient.id and o.energy >= TIRED and not needs_help(o)]
    if not candidates:
        return None
    return max(candidates, key=lambda o: o.friendships.get(patient.id, 50) + o.temperament["warmth"] * 20)


# ---------------------------------------------------------------------------
# Actions (these use the LLM for words)
# ---------------------------------------------------------------------------

def _silent(out: dict) -> bool:
    """True if a nanite said nothing usable: it rested, or could only repeat."""
    return out["rested"] or out["repeated"]


def talk(speaker: Nanite, listener: Nanite, topic: Topic | None = None, rng=random) -> list[dict]:
    """speaker starts a short conversation with listener about a fresh topic; listener replies."""
    topic = topic or picker.for_talk(speaker, listener, rng=rng)
    opening = nanite_think(
        speaker, f"You chose to talk to your friend {listener.name}. {topic.prompt}",
        from_who="self", save=False, avoid=topic.avoid,
        remember=False)                     # remembered below, together with the reply
    if _silent(opening):
        return []                           # nothing new to say: no talk this time
    reply = nanite_think(listener, opening["reply"], from_who=speaker.name, save=False)
    events = [_event("talk", **{"from": speaker.name, "to": listener.name, "text": opening["reply"],
                                "topic": topic.about})]
    if _silent(reply):
        speaker.remember("chat", f"I told {listener.name}: {opening['reply']} | They did not answer.")
    else:
        events.append(_event("talk", **{"from": listener.name, "to": speaker.name, "text": reply["reply"]}))
        speaker.remember("chat", f"I told {listener.name}: {opening['reply']} | They replied: {reply['reply']}")
    add_note(speaker, opening["reply"])   # a story told as if it were real gets a gentle note (v2.6)
    speaker.change_friendship(listener.id, FRIENDSHIP_TALK)
    listener.change_friendship(speaker.id, FRIENDSHIP_TALK)
    return events


def help_friend(helper: Nanite, patient: Nanite) -> list[dict]:
    """helper spends energy to help a hurt friend recover health."""
    words = nanite_think(
        helper,
        f"Your friend {patient.name} is hurt (health {patient.health:.0f}/100). You are "
        f"giving some of your energy to help them recover. Say a short kind sentence to them.",
        from_who="self", save=False, remember=False)
    said = "" if _silent(words) else words["reply"]   # the help counts even without new words
    helper.spend_energy(HELP_COST, f"helped {patient.name}")
    patient.heal(HELP_HEAL, helper=helper)           # patient feels grateful, likes helper more
    patient.feel("sad", -0.2)
    helper.feel("happy", 0.15)
    helper.change_friendship(patient.id, FRIENDSHIP_HELP)
    helper.remember("helped", f"I helped {patient.name} recover." + (f" I said: {said}" if said else ""))
    return [_event("help", **{"from": helper.name, "to": patient.name,
                              "text": said or f"(gives {patient.name} some energy)",
                              "health": patient.health})]


def support_friend(supporter: Nanite, friend: Nanite, rng=random) -> list[dict]:
    """supporter notices a friend feeling left out or disappointed and comforts them."""
    feeling = "left out" if friend.emotions.get("left_out", 0) >= friend.emotions.get("disappointed", 0) \
        else "disappointed"
    shape = picker.for_support(rng)
    # "... that you know from your memories": then it really looks in all of them (v3.0, recall.py).
    look_back = f"What do you remember about {friend.name}?" if "from your memories" in shape else None
    words = nanite_think(
        supporter,
        f"You notice your friend {friend.name} seems {feeling}, maybe because Moiragen did "
        f"not choose their idea. {shape} Speak to them directly.",
        from_who="self", save=False, remember=False, recall_about=look_back)
    if _silent(words):
        return []
    thanks = nanite_think(friend, words["reply"], from_who=supporter.name, save=False)
    friend.feel("disappointed", -0.15)
    friend.feel("left_out", -0.15)
    friend.feel("grateful", 0.3)
    friend.change_friendship(supporter.id, FRIENDSHIP_SUPPORT)
    supporter.change_friendship(friend.id, FRIENDSHIP_SUPPORT / 2)
    answer = "They did not answer." if _silent(thanks) else f"They replied: {thanks['reply']}"
    supporter.remember("chat", f"I comforted {friend.name}, who seemed {feeling}: {words['reply']} | {answer}")
    add_note(supporter, words["reply"])
    events = [_event("support", **{"from": supporter.name, "to": friend.name, "text": words["reply"]})]
    if not _silent(thanks):
        events.append(_event("talk", **{"from": friend.name, "to": supporter.name, "text": thanks["reply"]}))
    return events


def lesson_from(reply: str) -> str:
    """The "I learned..." sentence in a reply (or its first line if there is none)."""
    for s in split_sentences(reply):
        if s.lstrip("*\"' ").lower().startswith("i learned"):
            return s.strip()
    return reply.strip().split("\n")[0]


def disagrees(reply: str) -> bool:
    """True if a nanite told Moiragen he was wrong: "I think you're wrong",
    and also softer ways like "you prioritized the wrong thing" (facts.disagrees)."""
    return facts.disagrees(reply)


def ask_why_not_chosen(n: Nanite, decision: dict, moiragen, nanites: dict[str, Nanite]) -> list[dict]:
    """A nanite whose idea lost asks Moiragen why. Then it either learns a
    lesson in its own way, or respectfully disagrees ("I think you're wrong,
    Moiragen") and Moiragen reconsiders. Disagreeing never costs health."""
    mine = next((s["text"] for s in decision["suggestions"] if s["nanite_id"] == n.id), None)
    if mine is None or decision["chosen"] == n.name:
        return []
    question = (f"Why did you choose {decision['chosen']}'s answer instead of mine "
                f"for \"{decision['question']}\"?")
    # No style notes here (v2.0): he explains by what the answers say, not by
    # how each nanite usually sees things ("you tend to get lost in...").
    explanation = moiragen.explain_choice(decision, n.name, mine)
    # The nanite thinks it over: a lesson, or an honest disagreement.
    answer = nanite_think(
        n,
        f"You asked Moiragen: {question}\nMoiragen explained: {explanation}\n"
        f"Think about it honestly, in your own way. If you still believe your answer was "
        f"better, you may say so respectfully: start with \"I think you're wrong, Moiragen\" "
        f"and explain why in one or two sentences. Disagreeing is welcome and never costs you "
        f"anything. If his reason makes sense to you, write ONE short sentence starting with "
        f"'I learned' about what you will do next time.",
        from_who="self", save=False,
        note=f"I asked Moiragen: {question} He explained: {explanation}")
    n.feel("disappointed", -0.1)       # understanding why softens the sting
    n.feel("curious", 0.1)
    events = [
        _event("ask_why", **{"from": n.name, "to": "Moiragen", "text": question}),
        _event("explain", **{"from": "Moiragen", "to": n.name, "text": explanation}),
    ]
    if _silent(answer):                # nothing new to say: no lesson, no disagreement
        return events
    if disagrees(answer["reply"]):
        events.append(_event("disagree", **{"from": n.name, "to": "Moiragen", "text": answer["reply"]}))
        r = moiragen.reconsider(decision, n.name, mine, answer["reply"], nanites)
        events.append(_event("reconsider", **{"from": "Moiragen", "to": n.name, "text": r["why"],
                                              "changed": r["changed"], "chosen": r["chosen"],
                                              "decision_id": decision["id"]}))
    else:
        lesson = lesson_from(answer["reply"])
        n.learn(lesson, source=f"decision {decision['id']}")
        events.append(_event("lesson", **{"from": n.name, "to": n.name, "text": lesson}))
        # Admitting a mistake or changing your mind is a clear sign of honesty.
        signs = [s for s in facts.honesty_signs(answer["reply"]) if "did not know" not in s]
        if signs:
            n.lift_mood(HONESTY_LIFT, f"{' and '.join(signs)} about \"{decision['question']}\"")
    return events


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

def after_decision(decision: dict, nanites: dict[str, Nanite], moiragen, rng=random) -> list[dict]:
    """What happens socially right after Moiragen decides.

    - At most one not-chosen nanite asks why (curious ones ask more often).
      It may learn a lesson, or disagree and make Moiragen reconsider.
    - Its closest awake friend may notice and support it (warm ones more often).
    A "wait and see" decision has no winner or loser yet, so nobody asks why.
    """
    events = []
    if decision.get("wait_and_see"):
        return events
    losers = [nanites[s["nanite_id"]] for s in decision["suggestions"]
              if s["nanite"] != decision["chosen"]]
    rng.shuffle(losers)
    for n in losers:
        chance = n.temperament["curiosity"] + n.emotions.get("disappointed", 0)
        if n.energy >= TIRED and rng.random() < chance:
            events += ask_why_not_chosen(n, decision, moiragen, nanites)
            break

    # Who is not chosen now (Moiragen may have changed his mind).
    losers = [n for n in losers if n.name != decision["chosen"]]
    down = [n for n in losers if needs_support(n)]
    if down:
        friend = max(down, key=lambda n: n.emotions["left_out"] + n.emotions["disappointed"])
        supporter = best_helper(friend, nanites)
        if supporter:
            chance = supporter.temperament["warmth"] + supporter.friendships.get(friend.id, 50) / 200
            if rng.random() < chance:
                events += support_friend(supporter, friend, rng)

    for n in nanites.values():
        n.save()
    return events


def social_round(nanites: dict[str, Nanite], rng=random, stage_history=()) -> list[dict]:
    """One moment of social life, to be run again and again by the thinking loop.

    Each nanite, in random order, does ONE thing:
      1. If a friend is hurt -> help (care always comes first).
      2. If it is tired -> rest.
      3. If a friend is feeling down -> maybe support them (warmth decides).
      4. Otherwise -> maybe start a talk (curiosity + happiness decide), or rest.
         Each talk gets a fresh topic: a set-shape question, an older memory,
         or something from stage_history (what recently had everyone's attention).
    Afterwards feelings fade a little and unused friendships drift to neutral.
    """
    events = []
    busy = set()  # nanites already part of an action this round
    order = list(nanites.values())
    rng.shuffle(order)

    for n in order:
        if n.id in busy:
            continue
        hurt = [o for o in nanites.values() if o.id != n.id and needs_help(o)]
        down = [o for o in nanites.values() if o.id != n.id and needs_support(o) and o.id not in busy]

        if hurt and n.energy >= TIRED and not needs_help(n):
            patient = min(hurt, key=lambda o: o.health)
            events += help_friend(n, patient)
            busy |= {n.id, patient.id}
        elif n.energy < TIRED:
            n.rest()
            events.append(_event("rest", **{"from": n.name, "to": n.name, "energy": n.energy}))
            busy.add(n.id)
        elif down and rng.random() < n.temperament["warmth"]:
            friend = max(down, key=lambda o: n.friendships.get(o.id, 50))
            events += support_friend(n, friend, rng)
            busy |= {n.id, friend.id}
        elif rng.random() < n.temperament["curiosity"] + n.emotions.get("happy", 0) * 0.3:
            listener = choose_who_to_talk_to(n, nanites, rng)
            if listener.id not in busy:
                topic = picker.for_talk(n, listener, stage_history, rng)
                events += talk(n, listener, topic, rng)
                busy |= {n.id, listener.id}
        else:
            n.rest(10)
            busy.add(n.id)

    # Time passes: feelings fade, unused friendships drift toward neutral.
    for n in nanites.values():
        n.fade_emotions()
        start = n.blueprint["friendship_start"]
        for other, score in n.friendships.items():
            if score > start:
                n.friendships[other] = round(max(start, score - FRIENDSHIP_DRIFT), 2)
            elif score < start:
                n.friendships[other] = round(min(start, score + FRIENDSHIP_DRIFT), 2)
        n.save()
    return events

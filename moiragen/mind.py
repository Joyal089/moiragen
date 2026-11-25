"""How a nanite thinks: turning its body, feelings and memories into a reply.

The nanite has no role or personality written in. What makes each one
different is:
  1. its temperament numbers (e.g. "temperature" sets how adventurous the
     LLM is allowed to be),
  2. its current body and feelings (a tired nanite answers briefly),
  3. its own memories (what it has lived through so far).
As memories pile up, the nanites grow apart. That is their personality.
"""

from .config import NANITE_TEMPERATURE_BOOST
from .echo import NANITES, guard, record_training_example
from .llm import think
from .memory_log import log_event
from .nanite import Nanite
from .real_or_story import add_note
from .recall import remembering

# --- Energy rules (easy to tune) ---
THINK_BASE_COST = 5        # every thought costs at least this much energy
THINK_COST_PER_50_WORDS = 3  # longer answers cost more
TOO_TIRED = 8              # below this a nanite cannot think, it must rest
TIRED = 30                 # below this it keeps answers short

# How many recent memories to remind the nanite of each time.
# Small, because gemma3:4b has limited attention and we want speed.
RECENT_MEMORIES = 8

# --- The echo guard (see echo.py) ---
ECHO_RETRIES = 2           # how many times a nanite is asked to say something new
RETRY_WARMER = 0.1         # each new try is a little more adventurous (temperature)
# Nobody has to sound happy (v1.7). Said to the nanites and to Moiragen.
FEELINGS_ARE_FINE = ("You never need to sound happy or cheerful. Feeling neutral, tired, sad or "
                     "unsure is fine; just say what is true for you.")
NOTHING_NEW = ("I notice I'm only repeating what was already said, "
               "so I'll stay quiet until I have something new.")


def describe_state(n: Nanite) -> str:
    """Put the nanite's body and feelings into plain words for the prompt."""
    feelings = [f"{e} ({s:.1f})" for e, s in n.emotions.items() if s >= 0.15]
    feeling_text = ", ".join(feelings) if feelings else "calm"
    friends = ", ".join(
        f"{other.replace('nanite_', 'Nanite ').title()}: {score:.0f}/100"
        for other, score in n.friendships.items()
    )
    return (
        f"Health {n.health:.0f}/100, energy {n.energy:.0f}/100, mood {n.mood:.0f}/100 "
        f"(50 is neutral). Feelings: {feeling_text}. Friendship: {friends}."
    )


def recent_memories_text(n: Nanite, how_many: int = RECENT_MEMORIES) -> str:
    """The last few things the nanite lived through, oldest first."""
    if not n.memories:
        return "You have no memories yet. This is the start of your life."
    lines = [f"- [{m['kind']}] {m['text']}" for m in n.memories[-how_many:]]
    return "\n".join(lines)


def lessons_text(n: Nanite, how_many: int = 5) -> str:
    """The most recent lessons it has learned, or an empty string."""
    if not n.lessons:
        return ""
    lines = "\n".join(f"- {l['lesson']}" for l in n.lessons[-how_many:])
    return f"Lessons you have learned from experience:\n{lines}\n\n"


def build_system_prompt(n: Nanite, remembered: str = "") -> str:
    """The instructions the nanite sees before every thought.

    Notice there is no personality here: only facts about its situation.
    remembered: for a question about the past, what it found in all its memories (recall.py).
    """
    short = n.energy < TIRED
    memories = remembered or f"Your recent memories:\n{recent_memories_text(n)}\n"
    return (
        f"You are {n.name}, one of three small thinking nanites inside a digital being "
        f"called Moiragen. Moiragen listens to all three nanites and makes the final choice. "
        f"The other nanites are your friends. You have no fixed role. You are still "
        f"discovering who you are, only through what you experience.\n\n"
        f"Your body right now: {describe_state(n)}\n"
        f"Your feelings may show in how you answer, but only as much as you really feel them. "
        f"These numbers are for your own awareness; do not recite them. {FEELINGS_ARE_FINE}\n\n"
        f"{memories}\n"
        f"{lessons_text(n)}"
        f"Speak as yourself, in first person. When someone talks to you, reply to them "
        f"directly, not about them. Write only the words you say: no narration, no "
        f"stage directions, no \"I said\" or \"I replied\", and no quotation marks around "
        f"your own words. Nanites have no gender: call another nanite by name or \"they\". "
        f"Be honest; if you do not know, say so. "
        f"Only use what is in your memories: do not invent past events, and do not guess "
        f"what the other nanites think or feel unless they have told you. "
        + ("You are tired, so answer in one or two short sentences."
           if short else "Keep your answer under 120 words.")
    )


def energy_cost(reply: str) -> float:
    """Thinking costs energy: a base cost plus a bit for every 50 words."""
    words = len(reply.split())
    return THINK_BASE_COST + THINK_COST_PER_50_WORDS * (words / 50)


def speak_freshly(n: Nanite, system: str, messages: list[dict], temperature: float,
                  max_tokens: int, context=None, avoid: list[str] | None = None) -> tuple[str | None, float]:
    """Think, and make sure the words are new (the echo guard, see echo.py).

    1. Think, then check the reply against every nanite's recent lines.
    2. Too similar? Show the nanite what it said, ask it to say something new,
       and think again a little more adventurously (up to ECHO_RETRIES times).
    3. Still repeating? Keep only its new sentences. If nothing new is left,
       return None: the nanite has nothing new to say.

    context: e.g. a decision id (answers to the same question are not echoes)
    avoid:   texts the reply must not copy either (e.g. a memory it was given)
    Returns (the reply or None, seconds spent thinking).
    """
    convo, seconds = list(messages), 0.0
    for attempt in range(ECHO_RETRIES + 1):
        result = think(convo, temperature=round(temperature + attempt * RETRY_WARMER, 2),
                       max_tokens=max_tokens, system=system)
        seconds += result["seconds"]
        reply = result["text"]
        check = guard.check(reply, NANITES, context, avoid, speaker=n.name)
        if not check.too_similar:
            return reply, seconds
        # Rejected: logged (never saved as a memory or as training data).
        log_event("echo_rejected", n.name, text=reply[:300], similar_to=check.similar_to[:200],
                  score=check.score, attempt=attempt + 1)
        convo = messages + [{"role": "assistant", "content": reply},
                            {"role": "user", "content": check.nudge()}]
    rest = guard.strip_repeats(reply, NANITES, context, avoid, speaker=n.name)
    if rest and not guard.check(rest, NANITES, context, avoid, speaker=n.name).too_similar:
        return rest, seconds
    return None, seconds


def nanite_think(n: Nanite, message: str, from_who: str = "user", save: bool = True,
                 decision_id: str | None = None, avoid: list[str] | None = None,
                 remember: bool = True, note: str | None = None, task: str = "suggest",
                 recall_about: str | None = None) -> dict:
    """Ask a nanite something and get its reply.

    message:  what is said to the nanite
    from_who: who is speaking ("user", "Moiragen", "Nanite Two", ...)
              or "self" for a private moment where nobody is speaking and
              the message describes the situation (e.g. "You chose to talk to...")
    avoid:    texts the reply must not copy (e.g. the memory it was asked about)
    remember: False when the caller records the moment itself (e.g. a talk)
    note:     for a private moment: what to remember instead of the whole
              instruction, e.g. "I asked Moiragen why..."
    task:     with a decision_id, the training label: "suggest" (its answer) or
              "why" (its reply when Moiragen asked "why do you think that?")
    recall_about: the question itself, when `message` holds more than that ("The human asked
              us..."). If it asks about the past, all its memories are searched (recall.py).

    Returns {"nanite", "reply", "energy_spent", "seconds", "rested", "repeated"}.
    "repeated" is True when the nanite could only repeat what was already
    said: then nothing it said is saved, and the reply says so.
    """
    # 1. Too exhausted to think? It rests instead of answering.
    if n.energy < TOO_TIRED:
        n.rest()
        reply = "I'm too tired to think right now. I need to rest for a moment."
        n.remember("rest", "I was too tired to think, so I rested.", from_who=from_who)
        if save:
            n.save()
        return {"nanite": n.name, "reply": reply, "energy_spent": 0, "seconds": 0,
                "rested": True, "repeated": False}

    # 2. Build the prompt and think, a little warmer than its own temperature,
    #    making sure the words are new.
    #    A question about the past: first search ALL its memories (v3.0).
    if recall_about is None and from_who not in ("self", "Moiragen"):
        recall_about = message
    asker = from_who if from_who.startswith("Nanite ") else "user"   # (Moiragen passes on the human's question)
    system = build_system_prompt(n, remembering(n.name, n.memories, recall_about, asker) if recall_about else "")
    if from_who == "self":
        content = (f"(A private moment. Nobody is speaking to you.) {message}\n"
                   f"Write only the words you say out loud. If you speak to a friend, talk "
                   f"directly to them as \"you\". No narration, no stage directions.")
    else:
        speaker = "Your creator (the human)" if from_who == "user" else from_who
        content = f"{speaker} says: {message}"
    messages = [{"role": "user", "content": content}]
    max_tokens = 80 if n.energy < TIRED else 220
    temperature = round(n.temperament["temperature"] + NANITE_TEMPERATURE_BOOST, 2)
    reply, seconds = speak_freshly(n, system, messages, temperature, max_tokens, decision_id, avoid)
    repeated = reply is None

    # 3. Thinking costs energy, even when nothing new came out.
    cost = round(energy_cost(reply or ""), 2)
    n.spend_energy(cost, "thinking")

    # 4. Remember it and log it for fine-tuning, ONLY if it passed the echo check.
    if repeated:
        reply = NOTHING_NEW
        log_event("echo_quiet", n.name, about=message[:200])
        if remember and from_who != "self":   # what was said to it is still real
            n.remember("chat", f"{from_who} said: {message} | I had nothing new to say.",
                       from_who=from_who)
    else:
        if remember:
            if from_who == "self":
                n.remember("thought", f"{note or message} | I said: {reply}")
            else:
                n.remember("chat", f"{from_who} said: {message} | I replied: {reply}",
                           from_who=from_who)
            add_note(n, reply, message)      # v2.6: a story told as if it were real gets a gentle note
        record_training_example(n.name, system, messages, reply, NANITES, decision_id,
                                temperature=temperature,
                                **({"decision_id": decision_id, "task": task} if decision_id else {}))

    if save:
        n.save()
    return {"nanite": n.name, "reply": reply, "energy_spent": cost,
            "seconds": seconds, "rested": False, "repeated": repeated}

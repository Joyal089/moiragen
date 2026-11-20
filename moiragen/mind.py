"""How a nanite thinks: turning its body, feelings and memories into a reply.

The nanite has no role or personality written in. What makes each one
different is:
  1. its temperament numbers (e.g. "temperature" sets how adventurous the
     LLM is allowed to be),
  2. its current body and feelings (a tired nanite answers briefly),
  3. its own memories (what it has lived through so far).
As memories pile up, the nanites grow apart. That is their personality.
"""

from .llm import think
from .memory_log import log_event
from .nanite import Nanite

# --- Energy rules (easy to tune) ---
THINK_BASE_COST = 5        # every thought costs at least this much energy
THINK_COST_PER_50_WORDS = 3  # longer answers cost more
TOO_TIRED = 8              # below this a nanite cannot think, it must rest
TIRED = 30                 # below this it keeps answers short

# How many recent memories to remind the nanite of each time.
# Small, because gemma3:4b has limited attention and we want speed.
RECENT_MEMORIES = 8


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


def build_system_prompt(n: Nanite) -> str:
    """The instructions the nanite sees before every thought.

    Notice there is no personality here: only facts about its situation.
    """
    short = n.energy < TIRED
    return (
        f"You are {n.name}, one of three small thinking nanites inside a digital being "
        f"called Moiragen. Moiragen listens to all three nanites and makes the final choice. "
        f"The other nanites are your friends. You have no fixed role. You are still "
        f"discovering who you are, only through what you experience.\n\n"
        f"Your body right now: {describe_state(n)}\n"
        f"Your feelings may show in how you answer, but only as much as you really feel them. "
        f"These numbers are for your own awareness; do not recite them.\n\n"
        f"Your recent memories:\n{recent_memories_text(n)}\n\n"
        f"{lessons_text(n)}"
        f"Speak as yourself, in first person. When someone talks to you, reply to them "
        f"directly, not about them. Nanites have no gender: call another nanite by name or \"they\". "
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


def nanite_think(n: Nanite, message: str, from_who: str = "user", save: bool = True) -> dict:
    """Ask a nanite something and get its reply.

    message:  what is said to the nanite
    from_who: who is speaking ("user", "Moiragen", "Nanite Two", ...)
              or "self" for a private moment where nobody is speaking and
              the message describes the situation (e.g. "You chose to talk to...")

    Returns {"nanite", "reply", "energy_spent", "seconds", "rested"}.
    """
    # 1. Too exhausted to think? It rests instead of answering.
    if n.energy < TOO_TIRED:
        n.rest()
        reply = "I'm too tired to think right now. I need to rest for a moment."
        n.remember("rest", "I was too tired to think, so I rested.", from_who=from_who)
        if save:
            n.save()
        return {"nanite": n.name, "reply": reply, "energy_spent": 0, "seconds": 0, "rested": True}

    # 2. Build the prompt and think, using its own temperature.
    system = build_system_prompt(n)
    if from_who == "self":
        content = (f"(A private moment. Nobody is speaking to you.) {message}\n"
                   f"Write only the words you say out loud. If you speak to a friend, talk "
                   f"directly to them as \"you\". No narration, no stage directions.")
    else:
        speaker = "Your creator (the human)" if from_who == "user" else from_who
        content = f"{speaker} says: {message}"
    messages = [{"role": "user", "content": content}]
    max_tokens = 80 if n.energy < TIRED else 220
    result = think(messages, temperature=n.temperament["temperature"],
                   max_tokens=max_tokens, system=system)
    reply = result["text"]

    # 3. Pay the energy cost and remember the conversation.
    cost = round(energy_cost(reply), 2)
    n.spend_energy(cost, "thinking")
    if from_who == "self":
        n.remember("thought", f"{message} | I said: {reply}")
    else:
        n.remember("chat", f"{from_who} said: {message} | I replied: {reply}", from_who=from_who)

    # 4. Log the full exchange in a fine-tuning friendly shape.
    log_event("training_example", n.name, system=system, messages=messages, reply=reply,
              temperature=n.temperament["temperature"])

    if save:
        n.save()
    return {"nanite": n.name, "reply": reply, "energy_spent": cost,
            "seconds": result["seconds"], "rested": False}

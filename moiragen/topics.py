"""Fresh things to talk about, so every social moment starts somewhere new.

Why: with an open prompt ("say anything you want") the nanites fell back on
the memories in front of them and repeated those, again and again (the echo
loop, see echo.py). Specific questions with a set shape broke the loop every
time, so every talk now starts from ONE specific prompt. The kinds take turns:
  - a question with a set shape   ("one word for how you feel, then why")
  - one of the speaker's own older memories, to discuss in new words
  - something that recently had everyone's attention (from the stage)
A question shape is not used again until all the others have been used
(like dealing from a shuffled deck), and each memory or stage thought is
only talked about once.

Plain Python, no LLM.
"""

import random
from dataclasses import dataclass, field

from .mind import RECENT_MEMORIES

# Questions with a set shape. {friend} becomes the listener's name.
QUESTION_SHAPES = [
    'Ask {friend} one question that starts with "What if".',
    "Tell {friend} how you feel right now in exactly one word, then give one reason for that word.",
    "Tell {friend} one thing you are unsure about, then ask what they think. Two sentences.",
    "Tell {friend} one thing you would like to try, in one sentence starting with \"I'd like to\".",
    "Describe one thing you sense in your body right now as a comparison (\"it feels like...\"), "
    "then ask {friend} if they sense it too.",
    "Ask {friend} a question they can answer with a number from 1 to 10, and say why you ask.",
    "Ask {friend} one question about the human who made you.",
    "Ask {friend} what one thing they would change about how Moiragen chooses, and why.",
    "Ask {friend} which feeling is strongest in them right now.",
    "Give {friend} a choice between two things (\"Would you rather...\") and say which you would pick.",
    "Tell {friend} one thing you are proud of, in one sentence, then ask them the same.",
    "Ask {friend} what being a nanite means to them, in their own words.",
    "Tell {friend} one question you would like to ask Moiragen, then ask what they would ask him.",
    "Make a short guess about what will happen next inside Moiragen, then ask {friend} for theirs.",
]

# Ways to comfort a friend who feels left out or disappointed (also dealt fresh).
SUPPORT_SHAPES = [
    "Remind them of one good thing about them that you know from your memories. One or two sentences.",
    "Ask them one gentle question about how they feel, and tell them you are listening.",
    "Tell them, in your own words, that their idea still mattered, and say why.",
    "Offer them one small idea that might help them feel better. One or two sentences.",
    "Tell them one honest thing you like about thinking alongside them.",
]

# Memories worth talking about (not resting, not stage notices).
TALKABLE = {"chat", "thought", "chosen", "not_chosen", "praised", "mistake", "helped", "helped_by"}
# Stage thoughts NOT worth talking about (small talk, resting, tiredness).
STAGE_SKIP = {"talk", "rest", "tired"}


@dataclass
class Topic:
    kind: str                                          # "question", "memory" or "stage"
    prompt: str                                        # the instruction the speaker gets
    avoid: list[str] = field(default_factory=list)     # texts the reply must not copy
    about: str = ""                                    # a short label for the log and viewer


class TopicPicker:
    """Deals out a fresh, specific prompt for every talk and every comfort."""

    KINDS = ("question", "memory", "stage")

    def __init__(self):
        self.turn = 0                    # which kind goes first next time
        self.deck: list[str] = []        # question shapes not dealt yet
        self.support_deck: list[str] = []
        self.used: set = set()           # memories and stage thoughts already talked about

    def for_talk(self, speaker, friend, stage_history=(), rng=random) -> Topic:
        """The prompt for `speaker` starting a talk with `friend`."""
        start = self.turn % len(self.KINDS)
        self.turn += 1
        for kind in self.KINDS[start:] + self.KINDS[:start]:
            if kind == "memory":
                topic = self._memory(speaker, friend, rng)
            elif kind == "stage":
                topic = self._stage(speaker, friend, stage_history)
            else:
                topic = self._question(friend, rng)
            if topic:
                return topic
        return self._question(friend, rng)   # (not reached: a question always works)

    def for_support(self, rng=random) -> str:
        """A fresh way to comfort a friend."""
        if not self.support_deck:
            self.support_deck = list(SUPPORT_SHAPES)
            rng.shuffle(self.support_deck)
        return self.support_deck.pop()

    def _question(self, friend, rng) -> Topic:
        if not self.deck:                # all shapes used: shuffle them again
            self.deck = list(QUESTION_SHAPES)
            rng.shuffle(self.deck)
        shape = self.deck.pop()
        return Topic("question", shape.format(friend=friend.name),
                     about=shape.format(friend="them")[:70])

    def _memory(self, speaker, friend, rng) -> Topic | None:
        """One of the speaker's older memories (its newest ones are already in
        every prompt), with something real in it, not talked about before."""
        older = [m for m in speaker.memories[:-RECENT_MEMORIES]
                 if m["kind"] in TALKABLE and len(m["text"]) >= 40
                 and (speaker.id, m["time"], m["text"][:40]) not in self.used]
        if not older:
            return None
        m = rng.choice(older)
        self.used.add((speaker.id, m["time"], m["text"][:40]))
        text = m["text"] if len(m["text"]) <= 300 else m["text"][:300] + "..."
        when = m["time"][:16].replace("T", " ")
        prompt = (f"You remember this, from {when}:\n\"{text}\"\n"
                  f"Tell {friend.name} what you think about that memory NOW, in new words of "
                  f"your own (do not repeat it), then ask them one question about it. "
                  f"Two or three sentences.")
        return Topic("memory", prompt, avoid=[m["text"]], about=f"a memory from {when}")

    def _stage(self, speaker, friend, stage_history) -> Topic | None:
        """The newest thing that had everyone's attention (not the speaker's own words)."""
        fresh = [t for t in list(stage_history)[-10:]
                 if t.source != speaker.name and t.kind not in STAGE_SKIP and t.text
                 and (t.time, t.text[:40]) not in self.used]
        if not fresh:
            return None
        t = fresh[-1]
        self.used.add((t.time, t.text[:40]))
        prompt = (f"Earlier, everyone's attention went to this ({t.source}): \"{t.text[:250]}\"\n"
                  f"Tell {friend.name} what you make of it, in two sentences of your own, "
                  f"then ask them one question about it.")
        return Topic("stage", prompt, avoid=[t.text], about=f"the stage: {t.kind}")


# One picker for the whole program, so the deck carries on between rounds.
picker = TopicPicker()

"""The stage: Moiragen's "global workspace".

Idea (from Global Workspace Theory): many parts of a mind work at once,
but only ONE thing at a time gets into the spotlight of attention. Whatever
wins is "broadcast" to every part, so they all know about it.

Here:
  - Anyone (nanites, body cells, the predictor, you) can POST a thought
    with an importance from 0 to 1.
  - Every tick, the thoughts COMPETE. Salience = importance, minus a penalty
    if the same source won recently (so one voice cannot hog attention),
    plus a tiny bit of randomness (so ties are not always broken the same way).
  - The winner goes into the spotlight and is broadcast to all listeners.
  - Losers get older; strong ones get another chance next tick, old ones fade.
"""

from dataclasses import dataclass, field
from datetime import datetime
import random

REPEAT_PENALTY = 0.15   # per recent win by the same source
RECENT_WINDOW = 3       # how many recent winners count for the penalty
MAX_AGE = 2             # a losing thought gets this many more chances


@dataclass
class Thought:
    source: str          # who posted it: "Nanite One", "body", "predictor", "user", ...
    kind: str            # what sort: "help", "surprise", "question", "hot", ...
    text: str            # the thought itself in words
    importance: float    # 0..1, how much the poster thinks it matters
    data: dict = field(default_factory=dict)
    time: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    age: int = 0
    salience: float = 0.0  # filled in when competing

    def as_dict(self) -> dict:
        return {"source": self.source, "kind": self.kind, "text": self.text,
                "importance": round(self.importance, 2), "salience": round(self.salience, 2),
                "time": self.time, **({"data": self.data} if self.data else {})}


class Stage:
    def __init__(self):
        self.candidates: list[Thought] = []
        self.spotlight: Thought | None = None
        self.history: list[Thought] = []   # past winners, newest last
        self.listeners = []                # functions called with each winner

    def post(self, source: str, kind: str, text: str, importance: float, **data) -> Thought:
        """Offer a thought to the stage."""
        t = Thought(source, kind, text, max(0.0, min(1.0, importance)), data)
        self.candidates.append(t)
        return t

    def subscribe(self, fn) -> None:
        """fn(thought) is called whenever a thought wins the spotlight."""
        self.listeners.append(fn)

    def compete(self, rng=random) -> Thought | None:
        """Pick the winner for this moment and broadcast it."""
        if not self.candidates:
            return None
        recent = [t.source for t in self.history[-RECENT_WINDOW:]]
        for t in self.candidates:
            t.salience = (t.importance
                          - REPEAT_PENALTY * recent.count(t.source)
                          + rng.uniform(0, 0.05))
        winner = max(self.candidates, key=lambda t: t.salience)

        # Losers age; only those still young enough stay for the next round.
        survivors = []
        for t in self.candidates:
            if t is winner:
                continue
            t.age += 1
            if t.age <= MAX_AGE:
                survivors.append(t)
        self.candidates = survivors

        self.spotlight = winner
        self.history.append(winner)
        self.history = self.history[-50:]
        for fn in self.listeners:
            fn(winner)
        return winner

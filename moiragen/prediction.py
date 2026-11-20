"""Prediction and surprise: Moiragen always guesses what comes next.

A mind that predicts can notice when the world does something unexpected.
That "surprise" is a signal worth paying attention to.

Two simple predictors, both plain Python:

1. Numbers (GPU temperature, CPU load, battery...)
   Keeps a running average and a running "usual wobble". The next value is
   expected near the average. Surprise = how many wobbles away it landed.

2. Events (what wins the stage: "talk", "help", "question", ...)
   Counts which kind of event usually follows which (a tiny Markov chain).
   Surprise = 1 - how likely the event was, given the previous one.

Surprise is always between 0 (expected) and 1 (very surprising).
"""

from collections import defaultdict


class NumberPredictor:
    """Learns what a number usually is and how much it normally wobbles."""

    def __init__(self, floor: float, smoothing: float = 0.3, warmup: int = 3):
        self.floor = floor            # smallest wobble we accept (avoids dividing by ~0)
        self.smoothing = smoothing    # how fast the average follows new values
        self.warmup = warmup          # readings needed before we judge surprise
        self.average = None
        self.wobble = 0.0
        self.seen = 0

    def expect(self) -> float | None:
        return self.average

    def observe(self, value: float) -> float | None:
        """Take a new reading. Returns surprise 0..1 (None while still learning)."""
        if value is None:
            return None
        self.seen += 1
        if self.average is None:
            self.average = value
            return None
        error = abs(value - self.average)
        surprise = None
        if self.seen > self.warmup:
            surprise = min(1.0, error / (3 * max(self.wobble, self.floor)))
        # Learn from this reading (after judging it).
        a = self.smoothing
        self.average = (1 - a) * self.average + a * value
        self.wobble = (1 - a) * self.wobble + a * error
        return surprise


class EventPredictor:
    """Learns which kind of event tends to follow which."""

    def __init__(self, warmup: int = 5):
        self.counts = defaultdict(lambda: defaultdict(int))  # counts[previous][next]
        self.kinds = set()
        self.previous = None
        self.seen = 0
        self.warmup = warmup

    def predict(self) -> str | None:
        """The kind of event expected next."""
        following = self.counts.get(self.previous)
        if not following:
            return None
        return max(following, key=following.get)

    def probability(self, kind: str) -> float:
        """How likely `kind` is next. Add-one smoothing: unseen things are unlikely, not impossible."""
        following = self.counts.get(self.previous, {})
        total = sum(following.values())
        n_kinds = max(len(self.kinds | {kind}), 1)
        return (following.get(kind, 0) + 1) / (total + n_kinds)

    def observe(self, kind: str) -> float | None:
        """See an event. Returns surprise 0..1 (None while still learning)."""
        surprise = None
        if self.previous is not None and self.seen >= self.warmup:
            surprise = round(1 - self.probability(kind), 2)
        if self.previous is not None:
            self.counts[self.previous][kind] += 1
        self.kinds.add(kind)
        self.previous = kind
        self.seen += 1
        return surprise


class Predictor:
    """All of Moiragen's expectations in one place."""

    SURPRISE_LEVEL = 0.6  # above this, the surprise is posted to the stage

    def __init__(self):
        self.numbers = {
            "gpu_c": NumberPredictor(floor=4),        # degrees C
            "cpu_percent": NumberPredictor(floor=15),
            "battery_percent": NumberPredictor(floor=3),
        }
        self.events = EventPredictor()

    def check_body(self, snapshot: dict) -> list[dict]:
        """Compare body readings with expectations. Returns the surprising ones."""
        readings = {
            "gpu_c": snapshot["temperature"]["gpu_c"],
            "cpu_percent": snapshot["load"]["cpu_percent"],
            "battery_percent": snapshot["energy"]["battery_percent"],
        }
        surprises = []
        for name, value in readings.items():
            expected = self.numbers[name].expect()
            s = self.numbers[name].observe(value)
            if s is not None and s >= self.SURPRISE_LEVEL:
                surprises.append({"what": name, "expected": round(expected, 1),
                                  "got": value, "surprise": round(s, 2)})
        return surprises

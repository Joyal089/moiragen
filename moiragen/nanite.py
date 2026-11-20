"""A nanite's body: its stats, feelings, friendships and memories.

This step is only the BODY. Thinking (talking to the LLM) comes in step 3.

Each nanite lives in its own file:  memory/nanites/<id>.json
That file holds its stats, its memories, and its own copy of the blueprint.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import os

from .blueprint import get_blueprint, random_temperament
from .config import MEMORY_DIR
from .memory_log import log_event, read_events

NANITE_DIR = MEMORY_DIR / "nanites"
NANITE_DIR.mkdir(parents=True, exist_ok=True)

# The three thinking nanites. ids are used for file names; display names
# are what we show. Later each nanite will choose its own name.
NANITES = {
    "nanite_one": "Nanite One",
    "nanite_two": "Nanite Two",
    "nanite_three": "Nanite Three",
}


class BrokenNaniteError(Exception):
    """A nanite's file is missing parts or cannot be read."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Nanite:
    id: str
    display_name: str
    temperament: dict
    blueprint: dict
    health: float = 100
    energy: float = 100
    mood: float = 50
    emotions: dict = field(default_factory=dict)     # {"happy": 0.4, ...}
    friendships: dict = field(default_factory=dict)  # {"nanite_two": 50, ...}
    memories: list = field(default_factory=list)     # recent memories
    lessons: list = field(default_factory=list)      # things it learned; these shape who it becomes
    chosen_name: str | None = None                   # filled in later by the nanite itself
    born: str = field(default_factory=_now)

    # ---------- name ----------

    @property
    def name(self) -> str:
        """The name to show: its own chosen name if it has one."""
        return self.chosen_name or self.display_name

    # ---------- creating ----------

    @classmethod
    def create(cls, nanite_id: str, rng=None) -> "Nanite":
        """Build a brand-new nanite from the blueprint."""
        bp = get_blueprint()
        stats = bp["stats"]
        n = cls(
            id=nanite_id,
            display_name=NANITES[nanite_id],
            temperament=random_temperament(bp, rng),
            blueprint=bp,
            health=stats["health"]["start"],
            energy=stats["energy"]["start"],
            mood=stats["mood"]["start"],
            emotions={e: 0.0 for e in bp["emotions"]},
            friendships={other: bp["friendship_start"] for other in NANITES if other != nanite_id},
        )
        log_event("birth", n.name, temperament=n.temperament)
        return n

    # ---------- small helpers ----------

    def _clamp(self, stat: str, value: float) -> float:
        """Keep a stat inside the min/max range from the blueprint."""
        limits = self.blueprint["stats"][stat]
        return round(max(limits["min"], min(limits["max"], value)), 2)

    def remember(self, kind: str, text: str, **details) -> None:
        """Add a memory to this nanite and to the shared life log."""
        self.memories.append({"time": _now(), "kind": kind, "text": text, **details})
        keep = self.blueprint["memory_keep"]
        self.memories = self.memories[-keep:]  # forget the oldest beyond the limit
        log_event(kind, self.name, text=text, **details)

    def learn(self, lesson: str, source: str) -> None:
        """Keep a lesson. Lessons last longer than ordinary memories and are
        shown to the nanite every time it thinks, so they slowly shape it."""
        self.lessons.append({"time": _now(), "lesson": lesson, "source": source})
        self.lessons = self.lessons[-20:]
        log_event("lesson", self.name, text=lesson, source=source)

    # ---------- body changes ----------

    def spend_energy(self, amount: float, reason: str) -> None:
        """Working or helping costs energy. Low energy makes it feel tired."""
        self.energy = self._clamp("energy", self.energy - amount)
        if self.energy < 30:
            self.feel("tired", 0.3)
        log_event("energy", self.name, change=-amount, energy=self.energy, reason=reason)

    def rest(self, amount: float = 20) -> None:
        """Resting refills energy and eases tiredness."""
        self.energy = self._clamp("energy", self.energy + amount)
        self.emotions["tired"] = max(0.0, self.emotions.get("tired", 0) - 0.3)
        log_event("rest", self.name, change=amount, energy=self.energy)

    def hurt(self, amount: float, reason: str) -> None:
        """Being wrong lowers health and makes it a bit sad."""
        self.health = self._clamp("health", self.health - amount)
        self.feel("sad", 0.3)
        self.remember("mistake", reason, health=self.health)

    def heal(self, amount: float, helper: "Nanite | None" = None) -> None:
        """Recover health, by resting alone or with a friend's help."""
        self.health = self._clamp("health", self.health + amount)
        if helper:
            self.feel("grateful", 0.4)
            self.change_friendship(helper.id, +5)
            self.remember("helped_by", f"{helper.name} helped me recover.", helper=helper.name, health=self.health)

    def feel(self, emotion: str, amount: float) -> None:
        """Make a feeling stronger (or weaker, with a negative amount).

        Feelings also nudge mood: good ones lift it, bad ones lower it.
        """
        if emotion not in self.emotions:
            raise ValueError(f"Unknown emotion {emotion!r}; the blueprint allows {list(self.emotions)}")
        self.emotions[emotion] = round(max(0.0, min(1.0, self.emotions[emotion] + amount)), 2)
        good = {"happy", "grateful", "curious"}
        mood_push = 10 * amount if emotion in good else -10 * amount
        if emotion != "tired":  # being tired does not change mood by itself
            self.mood = self._clamp("mood", self.mood + mood_push)
        log_event("emotion", self.name, emotion=emotion, strength=self.emotions[emotion], mood=self.mood)

    def change_friendship(self, other_id: str, amount: float) -> None:
        """Friendship rises when helped or supported, falls when ignored."""
        old = self.friendships.get(other_id, self.blueprint["friendship_start"])
        self.friendships[other_id] = round(max(0, min(100, old + amount)), 2)

    def fade_emotions(self) -> None:
        """Called on every tick of time: feelings slowly fade back to calm."""
        fade = self.blueprint["emotion_fade_per_tick"]
        for e, strength in self.emotions.items():
            self.emotions[e] = round(max(0.0, strength - fade), 2)

    def strongest_emotion(self) -> tuple[str, float] | None:
        """The feeling it has most right now, or None if it is calm."""
        e, s = max(self.emotions.items(), key=lambda kv: kv[1])
        return (e, s) if s > 0 else None

    # ---------- saving and loading ----------

    @property
    def path(self):
        return NANITE_DIR / f"{self.id}.json"

    def save(self) -> None:
        """Write the nanite to its file.

        We write to a temporary file first and then swap it in, so a crash
        in the middle can never leave a half-written (broken) file.
        """
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, nanite_id: str) -> "Nanite":
        """Read a nanite from its file. Raises BrokenNaniteError if damaged."""
        path = NANITE_DIR / f"{nanite_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except FileNotFoundError:
            raise
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            raise BrokenNaniteError(f"{nanite_id} is damaged: {e}") from e

    # ---------- rebuilding a broken nanite ----------

    @classmethod
    def rebuild_from_friend(cls, nanite_id: str, friend: "Nanite") -> "Nanite":
        """Rebuild a broken nanite using a friend's copy of the blueprint.

        Its body starts fresh, but it gets back its memories from the shared
        life log, so it still remembers its past.
        """
        name = NANITES[nanite_id]
        bp = json.loads(json.dumps(friend.blueprint))  # deep copy of friend's blueprint
        stats = bp["stats"]
        n = cls(
            id=nanite_id,
            display_name=name,
            temperament=random_temperament(bp),
            blueprint=bp,
            health=stats["health"]["start"] * 0.5,  # comes back weak and needs care
            energy=stats["energy"]["start"] * 0.5,
            mood=stats["mood"]["start"],
            emotions={e: 0.0 for e in bp["emotions"]},
            friendships={o: bp["friendship_start"] for o in NANITES if o != nanite_id},
        )
        # Recover what we can from the life log: original temperament + memories.
        births = read_events(kind="birth", who=name, last=1)
        if births:
            n.temperament = births[0]["temperament"]
        recovered = [e for e in read_events(who=name, last=2000) if "text" in e]
        n.memories = [
            {"time": e["time"], "kind": e["kind"], "text": e["text"]} for e in recovered
        ][-bp["memory_keep"]:]
        n.lessons = [
            {"time": e["time"], "lesson": e["text"], "source": e.get("source", "")}
            for e in read_events(kind="lesson", who=name, last=20)
        ]
        n.change_friendship(friend.id, +10)  # it was a friend who saved it
        n.remember("rebuilt", f"I was broken and {friend.name} rebuilt me from the blueprint.", helper=friend.name)
        n.save()
        return n


def load_all() -> dict[str, Nanite]:
    """Wake up all three nanites.

    - If a nanite has never existed, it is born.
    - If its file is broken, a healthy friend rebuilds it.
    """
    nanites: dict[str, Nanite] = {}
    broken: list[str] = []

    for nid in NANITES:
        try:
            nanites[nid] = Nanite.load(nid)
        except FileNotFoundError:
            nanites[nid] = Nanite.create(nid)
            nanites[nid].save()
        except BrokenNaniteError:
            broken.append(nid)

    for nid in broken:
        friends = [n for n in nanites.values()]
        if not friends:
            # Nobody left to help: build from the original blueprint.
            nanites[nid] = Nanite.create(nid)
            nanites[nid].save()
            continue
        helper = max(friends, key=lambda f: f.health)  # the healthiest friend helps
        nanites[nid] = Nanite.rebuild_from_friend(nid, helper)
        helper.spend_energy(15, f"rebuilt {nanites[nid].name}")
        helper.save()

    return nanites

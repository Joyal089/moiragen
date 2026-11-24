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
from .early_life import make_room
from .memory_log import log_event, noted_changes, read_events
from .styles import starting_style

NANITE_DIR = MEMORY_DIR / "nanites"
NANITE_DIR.mkdir(parents=True, exist_ok=True)

# Sleep: while the app is closed (or nobody uses it), the nanites sleep and
# their energy slowly comes back, like a night's sleep.
SLEEP_ENERGY_PER_HOUR = 40   # 30 -> 70 takes one hour; empty -> full takes 2.5 hours
SLEEP_MAX_HOURS = 8          # sleep longer than this counts as 8 hours (a full night)

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
    style: dict = field(default_factory=dict)        # its own way of seeing (see styles.py)
    chosen_name: str | None = None                   # filled in later by the nanite itself
    born: str = field(default_factory=_now)
    last_awake: str = field(default_factory=_now)    # when it was last awake (set on every save)

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
        log_event(kind, self.name, text=text, **details)
        # Beyond the limit the oldest become short early-life notes; nothing is dropped (v2.7).
        self.memories, notes = make_room(self.memories, self.blueprint["memory_keep"])
        for note in notes:
            log_event("early_life", self.name, text=note["text"], since=note["since"], count=note["count"])

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

    def hours_asleep(self, now: datetime | None = None) -> float:
        """Hours since it was last awake (0 if the clock seems to have gone backwards)."""
        try:
            since = datetime.fromisoformat(self.last_awake)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, ((now or datetime.now()) - since).total_seconds() / 3600)

    def sleep(self, hours: float) -> float:
        """It slept for `hours` (the app was closed, or nobody was using it).
        Energy comes back at SLEEP_ENERGY_PER_HOUR, counting at most
        SLEEP_MAX_HOURS, and never above full. Returns the energy gained."""
        hours = min(max(hours, 0.0), SLEEP_MAX_HOURS)
        before = self.energy
        self.energy = self._clamp("energy", self.energy + hours * SLEEP_ENERGY_PER_HOUR)
        gained = round(self.energy - before, 2)
        if hours >= 0.5:                     # a real sleep also eases tiredness
            self.emotions["tired"] = 0.0
        if gained > 0:
            log_event("sleep", self.name, hours=round(hours, 2), change=gained, energy=self.energy)
        return gained

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

    def lift_mood(self, amount: float, reason: str) -> None:
        """A small boost to mood, e.g. for an honest answer or a good question.
        (Used for rewards that are not one of the blueprint's feelings.)"""
        self.mood = self._clamp("mood", self.mood + amount)
        log_event("mood_lift", self.name, change=amount, mood=self.mood, reason=reason)

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

        Saving also marks it as awake now. (While everyone rests, nothing
        saves the nanites, so last_awake keeps the moment they fell asleep.)
        """
        self.last_awake = _now()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, nanite_id: str) -> "Nanite":
        """Read a nanite from its file. Raises BrokenNaniteError if damaged."""
        path = NANITE_DIR / f"{nanite_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "last_awake" not in data:
                # Files from before sleep existed: it was last awake when its file was last saved.
                data["last_awake"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
            n = cls(**data)
            # Its own copy of the blueprint may be from when the limit was 200 (v2.7).
            n.blueprint["memory_keep"] = max(n.blueprint.get("memory_keep", 0), get_blueprint()["memory_keep"])
            return n
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
        # (Early-life notes are made again from the memories themselves.)
        recovered = [e for e in read_events(who=name, last=10**9) if "text" in e and e["kind"] != "early_life"]
        notes = noted_changes(name)      # labels added to a memory later (v2.6)
        n.memories, _ = make_room([
            {"time": e["time"], "kind": e["kind"], "text": notes.get((e["time"], e["text"]), e["text"])}
            for e in recovered
        ], bp["memory_keep"])
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

    # Nanites from before styles were tracked start from their known way of seeing.
    for n in nanites.values():
        if not n.style:
            n.style = starting_style(n.id)
            n.save()
    return nanites

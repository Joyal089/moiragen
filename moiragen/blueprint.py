"""The core blueprint: the "DNA" every nanite is built from.

Every nanite keeps its own copy of this blueprint inside its memory file.
If one nanite's file breaks, a friend's copy can be used to rebuild it
(see nanite.rebuild_from_friend).

The blueprint describes HOW a nanite is built, never WHO it is. There are
no roles or personalities here; only ranges that random temperaments are
drawn from. Personality grows later from experience.
"""

import copy
import random

BLUEPRINT = {
    "version": 1,

    # Body stats all run from 0 to 100.
    "stats": {
        "health": {"start": 100, "min": 0, "max": 100},
        "energy": {"start": 100, "min": 0, "max": 100},
        "mood":   {"start": 50,  "min": 0, "max": 100},  # 50 = neutral
    },

    # Friendship with each other nanite, 0 (strangers) to 100 (best friends).
    "friendship_start": 50,

    # Feelings a nanite can have. Each has a strength from 0.0 to 1.0
    # and slowly fades back to 0.
    "emotions": [
        "happy", "sad", "tired", "grateful",
        "disappointed", "left_out", "curious", "worried",
    ],
    "emotion_fade_per_tick": 0.05,

    # Temperament: a few numbers drawn at birth, each a little different.
    # The ranges are narrow on purpose: nanites start similar and grow apart.
    "temperament_ranges": {
        "temperature": (0.55, 0.85),  # how adventurous its thinking is (LLM temperature)
        "curiosity":   (0.35, 0.65),  # how likely to ask questions / start talks
        "boldness":    (0.35, 0.65),  # how strongly it pushes its own idea
        "warmth":      (0.35, 0.65),  # how likely to help and comfort others
        "patience":    (0.35, 0.65),  # how long before it gets tired or annoyed
    },

    # Keep this many recent memories inside the nanite file.
    # (Everything is also in memory/log.jsonl forever.)
    "memory_keep": 200,
}


def get_blueprint() -> dict:
    """Return a fresh copy, so nobody can change the original by accident."""
    return copy.deepcopy(BLUEPRINT)


def random_temperament(blueprint: dict, rng: random.Random | None = None) -> dict:
    """Draw a slightly different random temperament from the blueprint ranges."""
    rng = rng or random.Random()
    return {
        trait: round(rng.uniform(low, high), 3)
        for trait, (low, high) in blueprint["temperament_ranges"].items()
    }

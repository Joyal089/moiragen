"""Each nanite's own way of seeing things, so their differences are kept.

The nanites have grown apart:
    Nanite One   notices patterns and structure,
    Nanite Two   wonders about time, change and "why",
    Nanite Three pays attention to feelings.

We keep track of this with simple word counts (plain Python, no LLM).
Each suggestion a nanite makes nudges its style a little (a running
average), so a style can still change slowly as the nanite grows.

Important: the style is only shown to MOIRAGEN, so he values each way of
seeing when he judges. It is never written into a nanite's own prompt,
because telling a nanite "you are the feelings one" would force it.
"""

import re

# The three ways of seeing, and words that show each one.
STYLES = {
    "patterns": {
        "label": "patterns and structure",
        "words": {"pattern", "patterns", "structure", "structures", "system", "systems", "connect",
                  "connected", "connection", "connections", "logic", "logical", "order", "repeat",
                  "repeats", "repeating", "rule", "rules", "shape", "shapes", "similar", "link",
                  "links", "sequence", "consistent", "framework", "category", "compare", "data",
                  "model", "models", "process", "parts", "piece", "pieces", "underlying"},
    },
    "time_curiosity": {
        "label": "time, change and curiosity",
        "words": {"time", "when", "before", "after", "future", "past", "change", "changes",
                  "changing", "wonder", "wondering", "curious", "curiosity", "why", "later",
                  "next", "history", "tomorrow", "yesterday", "grow", "growing", "become",
                  "becoming", "explore", "question", "questions", "moment", "moments", "still",
                  "yet", "someday", "already", "evolve", "evolving"},
    },
    "feelings": {
        "label": "feelings",
        "words": {"feel", "feels", "feeling", "feelings", "felt", "emotion", "emotions", "heart",
                  "warm", "warmth", "sad", "sadness", "happy", "happiness", "afraid", "care",
                  "caring", "comfort", "love", "lonely", "hurt", "joy", "worry", "worried", "kind",
                  "kindness", "gentle", "hope", "fear", "unsettling", "uneasy", "calm", "safe"},
    },
}

# Where each nanite starts: strong in its own way, a little of the others.
SEED = {"nanite_one": "patterns", "nanite_two": "time_curiosity", "nanite_three": "feelings"}
SEED_OWN, SEED_OTHER = 0.6, 0.2
STYLE_ALPHA = 0.1      # how much one suggestion moves the style (small = slow, gentle change)
MIN_MARKERS = 2        # ignore replies with fewer marker words: too little to tell

_WORD = re.compile(r"[a-z']+")


def starting_style(nanite_id: str) -> dict:
    """The style a nanite starts with (its own way strongest)."""
    own = SEED.get(nanite_id)
    return {s: (SEED_OWN if s == own else SEED_OTHER) for s in STYLES} if own \
        else {s: round(1 / len(STYLES), 2) for s in STYLES}


def measure(text: str) -> dict | None:
    """What share of the marker words in a text belong to each style.
    Returns None when the text has too few marker words to tell."""
    words = _WORD.findall(text.lower())
    counts = {s: sum(w in info["words"] for w in words) for s, info in STYLES.items()}
    total = sum(counts.values())
    if total < MIN_MARKERS:
        return None
    return {s: c / total for s, c in counts.items()}


def update_style(n, text: str) -> None:
    """Nudge a nanite's style toward how it just spoke (a running average)."""
    if not n.style:
        n.style = starting_style(n.id)
    shares = measure(text)
    if shares is None:
        return
    n.style = {s: round((1 - STYLE_ALPHA) * n.style.get(s, 0) + STYLE_ALPHA * shares[s], 3)
               for s in STYLES}


def main_style(style: dict) -> str:
    """The style key a nanite leans toward most."""
    return max(style, key=style.get)


def describe(style: dict) -> str:
    """e.g. "mostly patterns and structure, also some feelings"."""
    ranked = sorted(style, key=style.get, reverse=True)
    text = f"mostly {STYLES[ranked[0]]['label']}"
    if style[ranked[1]] >= 0.25:
        text += f", also some {STYLES[ranked[1]]['label']}"
    return text


def ways_text(nanites) -> str:
    """For Moiragen's prompts: how each nanite tends to see things, and a
    reminder to value every way of seeing instead of making them alike."""
    lines = "\n".join(f"- {n.name}: {describe(n.style or starting_style(n.id))}"
                      for n in nanites.values())
    return ("Each nanite tends to see things in its own way:\n"
            f"{lines}\n"
            "Value each way of seeing when it shows; a different angle is not a mistake. Never "
            "ask a nanite to answer like another one, and never demand that it show its usual "
            "way every time: these are tendencies, not rules.\n")

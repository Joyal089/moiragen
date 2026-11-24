"""Real or story? (v2.6)

After story time a mind sometimes talks about a story as if it had really happened:
"I remembered helping Mr. Tan find Whiskers." That is never punished and the words are
never changed. Only a gentle note is added to its memory, right after what it said:

    That happened in a story we played, not in your real life.

It is plain Python, for the stories labelled as pretend play (training_rules.py):

  1. a sentence with a name from the story, where the speaker (or the friend it talks to)
     lives it: "I remembered helping Mr. Tan", "Lumi looked up at me", or
  2. a memory without names that is told with the story's own words: "the memory of her
     hand brushing against my casing as she tucked the drawing back into my storage".

Saying that it was a story ("in the story, I helped Mr. Tan") never gets a note. Neither
does answering a story-time question, nor talking about how Moiragen played ("he", "Moiragen").
"""

import re

from .echo import COMMON, words
from .memory_log import LOG_FILE, read_events
from .training_rules import STORY_MARK, pretend_stories

NOTE = "That happened in a story we played, not in your real life."

# It knows that it was a story.
KNOWS = re.compile(r"\b(?:story|stories|storytime|tale|play(?:ed|ing|s)?|pretend\w*|narrat\w+|fiction\w*|"
                   r"character|imagin\w+|simulat\w+)\b", re.IGNORECASE)
# It talks about how Moiragen played his part, not about its own life.
HOW_HE_PLAYED = re.compile(r"\bhe\b|\bhis (?:actions?|attempts?|efforts?|responses?|choices?|words|answers?|play\w*)\b"
                           r"|\bmoiragen\b", re.IGNORECASE)
# "I remembered helping...", "My sensors detected...", "You handled...", "did you observe...".
LIVED = re.compile(
    r"\b(?:I|we|you|my|our|your)(?:['’](?:ve|d))?(?:\W+\w+){0,2}?\W+(?:remember\w*|recall\w*|help\w*|handl\w+|saw|"
    r"seen|watch\w+|observ\w+|met|found|find|told|asked|heard|detect\w+|sens(?:ed|ing)|process\w+|regist\w+|"
    r"gave|kept|carr(?:y|ied)|show\w+|offer\w+|promis\w+|lost|walk\w+|hugg\w+|held|comfort\w+|rescu\w+|"
    r"search\w+|apologi[sz]\w+|visit\w*|talk\w*|spoke|went|was with|were with)\b", re.IGNORECASE)
# "Lumi looked up at me", "Mira told me".
TO_ME = re.compile(r"\b(?:look|smil|said|talk|ran|came|turn|wav|gave|hand|show|point|lean|reach)\w*(?:\W+\w+){0,3}?\W+"
                   r"(?:at|to|for|with|beside|towards?) (?:me|us)\b|\b(?:told|asked|gave|hugged|thanked|showed|"
                   r"helped|handed) (?:me|us)\b", re.IGNORECASE)
A_MEMORY = re.compile(r"\bmemor(?:y|ies) of\b|\bI (?:still )?(?:remember|recall)(?:ed)?\b", re.IGNORECASE)
ABOUT_ME = re.compile(r"\b(?:I|me|my|we|us|our)\b", re.IGNORECASE)
NOT_A_STORY_WORD = {"memory", "memories", "remember", "remembered", "recall", "recalled", "still", "felt", "feel",
                    "feels", "feeling", "like", "again", "against", "know", "something", "moment", "right", "back"}
OWN_WORDS_NEEDED = 3          # a memory without names needs this many of the story's own words


def sentences(text: str) -> list[str]:
    """The sentences of a text; "Mr. Tan" stays in one piece."""
    parts = re.split(r"(?<=[.!?])(?<!\bMr\.)(?<!\bMs\.)(?<!\bMrs\.)(?<!\bDr\.)[\"”’']*\s+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _telling(text: str) -> set[str]:
    """The words that say something (four letters or more, not "with", "remember"...)."""
    return {w for w in words(text) if len(w) >= 4 and w not in COMMON and w not in NOT_A_STORY_WORD}


def _same(word: str, other: str) -> bool:
    """ "tucked" and "tuck", "brushing" and "brush" """
    return word.startswith(other) or other.startswith(word)


def _told_in_its_words(sentence: str, story: dict) -> int:
    """How many of the sentence's words are the story's own (0 if too few: at least three,
    half of them, and one that nobody had used before the story)."""
    mine, whole = _telling(sentence), _telling(story["words"])
    shared = {w for w in mine if any(_same(w, o) for o in whole)}
    new = any(_same(w, o) for w in shared for o in whole & story["new_words"])
    return len(shared) if new and len(shared) >= OWN_WORDS_NEEDED and len(shared) * 2 >= len(mine) else 0


def as_if_real(text: str, stories: dict) -> tuple[str, str] | None:
    """(the sentence, the story's title) if the text tells a story event as if it really
    happened to the speaker, else None. stories: see training_rules.pretend_stories."""
    if KNOWS.search(text or ""):
        return None                                       # it says itself that it was a story
    own = [s for s in sentences(text) if not HOW_HE_PLAYED.search(s)]
    for s in own:                                         # 1. with a name from the story
        for title, story in stories.items():
            if any(re.search(rf"\b{n}\b", s) for n in story["names"]):
                if LIVED.search(s) or TO_ME.search(s):
                    return s, title
    for s in own:                                         # 2. a memory in the story's own words
        if A_MEMORY.search(s) and ABOUT_ME.search(s):
            best = max(stories, key=lambda title: _told_in_its_words(s, stories[title]), default=None)
            if best and _told_in_its_words(s, stories[best]):
                return s, best
    return None


# The stories, read from the life log (again only when the log has grown).
_known = {"size": -1, "stories": {}}


def known_stories() -> dict:
    size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    if size != _known["size"]:
        _known.update(size=size, stories=pretend_stories(read_events(last=10**9)))
    return _known["stories"]


def add_note(mind, said: str, question: str = "") -> str | None:
    """Add the gentle note to a mind's memory if it just talked about a story as if it were
    real. Nothing else changes: no health, no mood, and its words stay. Returns the note."""
    if STORY_MARK.search(question):
        return None                                       # it was asked about the story
    found = as_if_real(said, known_stories())
    if not found:
        return None
    sentence, title = found
    note = f"A gentle note about \"{title}\" (I said: \"{sentence.strip('“”')}\"): {NOTE}"
    mind.remember("story_note", note, story=title, said=sentence)
    return note

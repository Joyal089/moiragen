"""What must never become fine-tuning data (v2.5).

A model learns from everything it is shown, in the reply and in the prompt. So the
export (export.py) leaves out an example if any part of it contains:

  made_up    words the made-up memory checks flagged
  corrected  words that got a correction note later
  pretend    anything from a story that is labelled as pretend play

Only pretend play has an exception: it may stay in if its own question clearly says it
is that story ("(Story time, after the pretend story "..." ...)"). Made-up and corrected
words never stay in, not even in a story.

The life log itself is never changed: the rules are worked out from it at export time,
so a correction or a label you add today also covers everything from before.
"""

import ast
from datetime import datetime
import re

# A label written on a memory, or a story announced as pretend play.
LABEL = re.compile(r"\[(?:about )?pretend play|\bpretend (?:play|story)\b", re.IGNORECASE)
# A question that starts by saying it is a story ("Your creator (the human) says: (Story time, ...").
STORY_MARK = re.compile(r"^.{0,60}\((?:pretend )?story time\b|^.{0,60}here is a short story\b",
                        re.IGNORECASE | re.DOTALL)
# Capital letters that are not a name from a story.
ORDINARY = set("Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June "
               "July August September October November December Mama Papa Mum Dad Grandma Grandpa".split())
# How the first story sessions wrote their flags into the journal line.
OLD_FLAG = re.compile(r"\(made-up memory check: (\[.*\])\)", re.DOTALL)


def plain(text: str) -> str:
    """The text in one simple form, so curly quotes, capitals or line breaks never hide a match."""
    text = (text or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.split())


def base_title(title: str) -> str:
    """'The Rainy Day (pretend play): what the nanites noticed' -> 'The Rainy Day'"""
    return re.split(r"\s*\(|: ", title or "")[0].strip()


# ---------------- 1. made-up words ----------------

def made_up_words(events: list[dict]) -> list[str]:
    """Every sentence that a made-up memory check flagged."""
    out = []
    for e in events:
        if e["kind"] == "decision_full":                     # a nanite's claim about the past (facts.py)
            for claims in ((e.get("checks") or {}).get("false_claims") or {}).values():
                out += claims
        elif e["kind"] == "invented_feedback":               # words he said a nanite wrote (mother.py)
            out += e.get("removed") or []
        elif e["kind"] in ("story_flag", "round_flag", "lesson_flag"):   # a story, a Turn Round, a lesson
            out += e.get("made_up") or []
        elif e["kind"] == "path_story":
            found = OLD_FLAG.search(e.get("text") or "")
            if found:
                try:
                    out += ast.literal_eval(found.group(1))
                except (ValueError, SyntaxError):
                    pass
    mistakes = taken_back(events)
    return [plain(t) for t in out if t and plain(t) not in mistakes]


def taken_back(events: list[dict]) -> set[str]:
    """v3.0: claims that were flagged by mistake (they were true after all), so they are free again."""
    return {plain(e["claim"]) for e in events if e["kind"] == "flag_removed"}


# ---------------- 2. corrected words ----------------

def corrected_words(events: list[dict]) -> tuple[list[str], set]:
    """(the corrected words, {(who, decision_id)} for a decision that was corrected).

    A correction says whose words it corrects and from when. If it quotes the wrong words,
    only those count; otherwise the whole reply (or Moiragen's whole reason) does."""
    words, decisions = [], set()
    for e in events:
        if e["kind"] == "flag_removed":              # the mistaken words themselves ("that did not happen")
            words += [plain(w) for w in e.get("wrong_words") or []]
    for c in events:
        if c["kind"] != "correction" or not c.get("corrects"):
            continue
        for e in events:
            if e["who"] != c["who"] or e["kind"] not in ("training_example", "decision_full"):
                continue
            apart = datetime.fromisoformat(e["time"]) - datetime.fromisoformat(c["corrects"])
            if abs(apart.total_seconds()) > 1:        # a thought and its log line can be a second apart
                continue
            said = e.get("reply") or e.get("reason")
            if e["kind"] == "decision_full":
                decisions.add((e["who"], e.get("id")))
            if said:
                quoted = [plain(q) for q in re.findall(r'["“](.+?)["”]', c.get("text") or "")]
                quoted = [q for q in quoted if q in plain(said)]
                words += quoted or [plain(said)]
    return words, decisions


# ---------------- 3. pretend play ----------------

def pretend_stories(events: list[dict]) -> dict[str, dict]:
    """Every story labelled as pretend play: {title: {"since": time, "names": [...],
    "words": the whole story, "new_words": those nobody had used before it}}.

    The names are the new names in the narrator's words ("Lumi", "Rosa"): words with a capital
    letter in the middle of a sentence, never written before the story began, and never
    written with a small letter ("park"). If a name is left out by mistake the title still
    counts; if an ordinary example is left out by mistake, nothing false was learned."""
    titles = set()
    for e in events:
        title = e.get("title") or e.get("story")
        if e["kind"] in ("path_story", "story_time", "story_talk") and isinstance(title, str) \
                and "pretend play" in title.lower():
            titles.add(base_title(title))
        if e["kind"] == "memory_note":                       # a label added to a memory later
            for c in e.get("changes") or []:
                named = re.search(r'Story time, "([^"]+)"', c.get("new") or "")
                if named and LABEL.match(c["new"]):
                    titles.add(base_title(named.group(1)))
    # Every word anybody ever wrote with a small letter: ordinary words, not names.
    small = {w for e in events for w in re.findall(r"\b[a-z]+\b", str(e.get("reply") or e.get("text") or ""))}
    stories = {}
    for title in titles:
        its_events = [e for e in events if base_title(str(e.get("title") or e.get("story") or "")) == title]
        its_events = [e for e in its_events if e["kind"] in ("path_story", "story_time", "story_talk")]
        if not its_events:
            continue
        since = min(e["time"] for e in its_events)
        # What the narrator told (names come from here), and every word of the story.
        told = " ".join(e["text"].split("||")[0] for e in its_events
                        if str(e.get("text")).startswith("Narrator:") and e["kind"] == "path_story"
                        or e["kind"] == "story_time" and e["who"] == "mind")
        whole = " ".join(str(e.get("text") or "") for e in its_events)
        names = set(re.findall(r"(?:(?<=[a-z,;] )|(?<=Mr\. )|(?<=Ms\. )|(?<=Mrs\. ))[A-Z][a-z]{2,}\b", told))
        old = " ".join(str(e.get("reply") or e.get("text") or "") for e in events if e["time"] < since)
        known = set(re.findall(r"\w+", old)) | ORDINARY
        stories[title] = {"since": since, "words": whole,
                          "new_words": set(re.findall(r"[a-z]+", whole.lower()))
                          - set(re.findall(r"[a-z]+", old.lower())),
                          "names": sorted(n for n in names if n not in known and n.lower() not in small)}
    return stories


def labelled_words(events: list[dict]) -> list[str]:
    """The text of every memory that was given a pretend-play label later (for "Story
    time: I said: ..." also just what was said)."""
    old = [plain(c["old"]) for e in events if e["kind"] == "memory_note" for c in e.get("changes") or []
           if LABEL.match(c.get("new") or "") and c.get("old")]
    # ... and what a mind told as if a story were real (it got a gentle note, see real_or_story.py).
    old += [plain(e["said"]) for e in events if e["kind"] == "story_note" and e.get("said")]
    return old + [w.split("i said: ", 1)[1] for w in old if len(w.split("i said: ", 1)[-1]) > 30 and "i said: " in w]


# ---------------- the rule ----------------

class TrainingRules:
    """Reads the life log once; then why_not(example) says why an example must stay out."""

    def __init__(self, events: list[dict]):
        self.made_up = made_up_words(events)
        self.corrected, self.corrected_decisions = corrected_words(events)
        self.stories = pretend_stories(events)
        self.labelled = labelled_words(events)

    def stories_in(self, example: dict, text: str) -> set:
        """The pretend stories this example touches (by title or by a name from the story)."""
        return {title for title, s in self.stories.items() if example["time"] >= s["since"]
                and (plain(title) in plain(text)
                     or any(re.search(rf"\b{n}\b", text) for n in s["names"]))}

    def story_mark(self, example: dict) -> str | None:
        """The title of the pretend story its question clearly announces, or None."""
        question = example["messages"][-1]["content"]
        if not STORY_MARK.search(question):
            return None
        return next((t for t in self.stories if plain(t) in plain(question)), None)

    def why_not(self, example: dict) -> str | None:
        """"made_up", "corrected" or "pretend" if this example must be left out, else None."""
        text = "\n".join([example["system"]] + [m["content"] for m in example["messages"]] + [example["reply"]])
        flat, reply = plain(text), plain(example["reply"])
        if any(w in flat for w in self.made_up):
            return "made_up"
        if any(w in flat for w in self.corrected) \
                or (example["who"], example.get("decision_id")) in self.corrected_decisions:
            return "corrected"
        touched = self.stories_in(example, text)
        pretend = (touched or LABEL.search(text) or any(w in flat for w in self.labelled)
                   or any(len(reply) > 30 and reply in w for w in self.labelled))
        # A pretend story stays in only if the question says it is that story, and no other
        # pretend story is mixed in (in the nanite's memories, for example).
        if pretend and (self.story_mark(example) is None or touched != {self.story_mark(example)}):
            return "pretend"
        return None

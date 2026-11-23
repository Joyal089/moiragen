"""The echo guard: stops the nanites repeating themselves and each other.

What went wrong (November 2026): a small model copies text it can see, and
the nanites see their recent memories in every prompt. Once a line got into
memory they kept saying it again, which put it into memory again: an echo
loop. In 11 minutes "It's... interesting, isn't it, how things shift?" was
said 11 times, and shown back to the minds in their prompts 80 times.

How the guard breaks the loop:
  * check(line) compares a new line with the recent lines of EVERY nanite.
    The line is "too similar" if it repeats a sentence of 6+ words that a
    nanite said recently, or if the whole line is mostly the same as a
    recent line.
  * mind.nanite_think() rejects a line like that and asks the nanite to say
    something new. If it still repeats itself, the copied sentences are cut.
  * Only lines that pass are saved, remembered here as "recent", and written
    to the fine-tuning log (record_training_example is the only way in).

Two nanites answering the SAME question alike is agreement, not an echo, so
suggestions for one decision are not compared with each other.

v1.8, short echoes: in the teaching session "They're quiet." and "They seem
quieter than usual. It's alright." spread between Two and Three, too short for
the 6-word rule. So the guard also catches:
  * a short opener (the first sentence, 2-5 words) that starts or appears in a
    recent line ("They're quiet."), unless it is a natural short phrase like
    "I don't know." or "Thank you.";
  * a phrase of 5 words copied from ANOTHER nanite's recent line ("understand
    patterns better than anyone"), when it has at least 3 real words (so
    "Moiragen chose Nanite One's answer" can still be said). Words in quotation
    marks, and the human's own question words, are allowed.

Everything here is plain Python (difflib from the standard library), no LLM.
"""

import re
import threading
from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .memory_log import log_event, read_events

# --- Tunable numbers ---
RECENT_LINES = 12          # how many recent lines of each speaker we compare with
SENTENCE_MIN_WORDS = 6     # shorter sentences ("I don't know.") may repeat naturally
SENTENCE_LIMIT = 0.85      # two sentences at least this alike (0..1) count as the same
LINE_MIN_WORDS = 8         # whole lines shorter than this ("Paris.") are not compared
LINE_LIMIT = 0.7           # two whole lines at least this alike count as the same
SEED_EXAMPLES = 300        # on start, read this many recent training examples from the log
# v1.8: short echoes
OPENER_MIN_WORDS = 2       # a one-word opener ("Hmm.") may repeat naturally
PHRASE_WORDS = 5           # a run of this many words copied from another nanite is an echo...
PHRASE_REAL_WORDS = 3      # ...if at least this many of them are real words (not "the", "a", names)
ALLOWED_KEEP = 20          # how many of the human's recent questions may be repeated freely

NANITES = "nanites"        # the group whose lines are all compared with each other

# Short phrases anyone may say again and again: honesty, thanks, agreement.
NATURAL_SHORT = re.compile(
    r"^(?:i (?:really |truly )?(?:don't|do not) (?:know|understand|remember)|i'm not (?:sure|certain)|"
    r"i am not (?:sure|certain)|i'm unsure|i'm sorry|i am sorry|thank you|thanks|yes|no|okay|ok|"
    r"i see|i agree|i understand|me too|i'm okay|i am okay|i'm here|i'm listening|"
    r"i think you're wrong|i think you are wrong)\b")    # how a nanite starts a disagreement
# Small words that do not make a phrase special (plus the nanites' names).
COMMON = set("""a an the and or but so of to in on at by for with from as is are was were be been
being it it's its this that these those there here they them their they're i i'm me my we us our
you your you're he she his her not no do does did don't can could would should will just than then
very more most much some any all also too what which who how why when where if about into over
moiragen nanite nanites one two three another other others""".split())


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------

def words(text: str) -> list[str]:
    """Lower-case words without punctuation: "It's… interesting!" -> ["it's", "interesting"]."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)*", text)


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Where each sentence starts and ends in the text.

    "…" and "..." are pauses, not sentence ends (the nanites use them a lot),
    so "It's… interesting, isn't it?" stays one sentence.
    """
    scan = text.replace("...", "…" * 3)   # same length, so positions still match
    cuts = [m.end() for m in re.finditer(r"[.!?]+[\"'”’)\]*]*(?=\s|$)|\n", scan)]
    spans, start = [], 0
    for end in cuts + [len(text)]:
        s, e = start, end
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if s < e:
            spans.append((s, e))
        start = end
    return spans


def split_sentences(text: str) -> list[str]:
    return [text[s:e] for s, e in sentence_spans(text)]


QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”")


def without_quotes(text: str) -> str:
    """The text with anything in double quotation marks taken out: quoting what
    someone said (or the human's question) is not copying it."""
    return QUOTED.sub(" ", text)


def phrases(text: str, n: int = PHRASE_WORDS, allowed: set[str] = frozenset()) -> set[tuple[str, ...]]:
    """Every run of n words in the text (outside quotation marks) that has at
    least PHRASE_REAL_WORDS real words in it, not counting `allowed` words
    (the human's question: "why people sleep at night" is its words)."""
    w = words(without_quotes(text))
    base = [x[:-2] if x.endswith("'s") else x for x in w]      # "one's" counts as "one"
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)
            if sum(x not in COMMON and x not in allowed for x in base[i:i + n]) >= PHRASE_REAL_WORDS}


def is_natural_short(sentence_words: list[str]) -> bool:
    """ "I don't know.", "Thank you.", "Yes." ... may always be said again."""
    return bool(NATURAL_SHORT.match(" ".join(sentence_words)))


def alike(a: list[str], b: list[str], at_least: float = 0.0) -> float:
    """How alike two word lists are: 0 = nothing shared, 1 = identical.

    `at_least` lets us skip the slower exact measure when two texts cannot
    possibly be that alike (their lengths or words are too different).
    """
    if not a or not b:
        return 0.0
    m = SequenceMatcher(None, a, b, autojunk=False)
    if m.real_quick_ratio() < at_least or m.quick_ratio() < at_least:
        return 0.0
    return m.ratio()


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

@dataclass
class Check:
    """The result of checking one new line."""
    too_similar: bool
    repeated: list[str] = field(default_factory=list)  # its sentences that were said recently
    similar_to: str = ""                               # the recent line most like it
    score: float = 0.0                                 # how alike the whole line is to that one

    def nudge(self) -> str:
        """What we tell the nanite so it tries again with something new."""
        said = self.repeated[0] if self.repeated else self.similar_to
        start = " ".join(said.split()[:6])
        return (f"That repeats what was said very recently (\"{start}...\"). "
                f"Say something new instead, in different words, without repeating it.")


class EchoGuard:
    """Remembers the recent lines of each speaker and checks new lines against them."""

    def __init__(self, seed_from_log: bool = True):
        # group -> speaker -> the speaker's recent (line, context) pairs, newest last
        self._recent: dict[str, dict[str, deque]] = {}
        self._seeded = not seed_from_log
        self._lock = threading.Lock()
        self._allowed = deque(maxlen=ALLOWED_KEEP)   # the human's recent questions (v1.8)

    def allow(self, text: str) -> None:
        """Words that anyone may repeat, like the human's question: talking about
        "why people sleep at night" is not copying another nanite."""
        with self._lock:
            self._allowed.append(text)

    def _seed(self) -> None:
        """On first use, fill in recent lines from the life log, so the guard
        also knows what was said before Moiragen was restarted."""
        if self._seeded:
            return
        self._seeded = True
        for e in read_events(kind="training_example", last=SEED_EXAMPLES):
            group = "Moiragen" if e["who"] == "Moiragen" else NANITES
            self._add(e["who"], e.get("reply", ""), group, e.get("decision_id"))

    def _add(self, speaker: str, line: str, group: str, context) -> None:
        if line.strip():
            by_speaker = self._recent.setdefault(group, {})
            by_speaker.setdefault(speaker, deque(maxlen=RECENT_LINES)).append((line, context))

    def add(self, speaker: str, line: str, group: str = NANITES, context=None) -> None:
        """Remember a line that was accepted. `context` is e.g. a decision id."""
        with self._lock:
            self._seed()
            self._add(speaker, line, group, context)

    def recent_by(self, group: str = NANITES, context=None) -> list[tuple[str, str]]:
        """(speaker, line) for everyone's recent lines in the group (minus the same context)."""
        with self._lock:
            self._seed()
            return [(speaker, line) for speaker, lines in self._recent.get(group, {}).items()
                    for line, ctx in lines if context is None or ctx != context]

    def recent(self, group: str = NANITES, context=None) -> list[str]:
        """Recent lines of everyone in the group (minus those from the same context)."""
        return [line for _, line in self.recent_by(group, context)]

    def check(self, line: str, group: str = NANITES, context=None,
              avoid: list[str] | None = None, speaker: str | None = None) -> Check:
        """Is `line` too close to something said recently?

        avoid:   extra texts the line must not copy either (e.g. a memory the
                 nanite was asked to talk about).
        speaker: who is saying it, so a phrase copied from ANOTHER nanite is caught
                 (without it, that rule is skipped).
        """
        by = self.recent_by(group, context)
        pool = [l for _, l in by] + [a for a in (avoid or []) if a]
        if not pool or not line.strip():
            return Check(False)

        # 1. Does it repeat a whole sentence (6+ words) from a recent line?
        pool_sentences = []
        for p in pool:
            for s in split_sentences(p):
                w = words(s)
                if len(w) >= SENTENCE_MIN_WORDS:
                    pool_sentences.append(w)
        repeated = []
        for s in split_sentences(line):
            w = words(s)
            if len(w) >= SENTENCE_MIN_WORDS and any(
                    alike(w, p, SENTENCE_LIMIT) >= SENTENCE_LIMIT for p in pool_sentences):
                repeated.append(s)

        # 2. Is the whole line mostly the same as a recent line?
        line_words = words(line)
        score, similar_to = max(((alike(line_words, words(p)), p) for p in pool), key=lambda x: x[0])
        same_line = len(line_words) >= LINE_MIN_WORDS and score >= LINE_LIMIT

        # 3. (v1.8) A short opener said recently: "They're quiet." again.
        sentences = split_sentences(line)
        if sentences:
            first = words(sentences[0])
            if (OPENER_MIN_WORDS <= len(first) < SENTENCE_MIN_WORDS and not is_natural_short(first)
                    and sentences[0] not in repeated):
                for p in pool:
                    if any(alike(first, words(s)) >= SENTENCE_LIMIT for s in split_sentences(p)):
                        repeated.append(sentences[0])
                        similar_to = similar_to if score >= LINE_LIMIT else p
                        break

        # 4. (v1.8) A 5-word phrase copied from another nanite's recent line.
        if speaker:
            with self._lock:
                allowed = {w for a in self._allowed for w in words(a)}
            theirs = {}
            for who, p in by:
                if who != speaker:
                    for ph in phrases(p, allowed=allowed):
                        theirs.setdefault(ph, p)
            for s in sentences:
                if s in repeated:
                    continue
                copied = next((theirs[ph] for ph in phrases(s, allowed=allowed) if ph in theirs), None)
                if copied:
                    repeated.append(s)
                    similar_to = similar_to if score >= LINE_LIMIT else copied

        return Check(bool(repeated) or same_line, repeated, similar_to, round(score, 2))

    def strip_repeats(self, line: str, group: str = NANITES, context=None,
                      avoid: list[str] | None = None, speaker: str | None = None) -> str:
        """The line with every recently-said sentence cut out ("" if nothing is left)."""
        repeated = set(self.check(line, group, context, avoid, speaker).repeated)
        kept = [line[s:e] for s, e in sentence_spans(line) if line[s:e] not in repeated]
        return " ".join(kept).strip()


# One guard for the whole program (the mind loop runs in a single thread,
# but the lock keeps it safe if a terminal tool uses it at the same time).
guard = EchoGuard()


def record_training_example(who: str, system: str, messages: list[dict], reply: str,
                            group: str = NANITES, context=None, **labels) -> bool:
    """Write a training example to the life log, ONLY if the reply passes the
    echo check, then remember the reply as a recent line.

    This is the one door into the fine-tuning log, so a copied line can never
    become training data. Returns True if the example was written.
    """
    check = guard.check(reply, group, context, speaker=who)
    if check.too_similar:
        log_event("training_skipped", who, reason="too similar to a recent line",
                  similar_to=check.similar_to[:200], score=check.score,
                  task=labels.get("task", "chat"))
        return False
    log_event("training_example", who, system=system, messages=messages, reply=reply, **labels)
    guard.add(who, reply, group, context)
    return True

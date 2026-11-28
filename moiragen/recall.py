"""Wider recall (v3.0): when a mind is asked about the past, search ALL its memories.

Why: a mind is normally reminded of its last 8 memories only. Asked "what do you
remember?", the nanites could see just the last few minutes of their life, and the
small model filled the gaps with things that never happened.

How it works (plain Python, no LLM, so it is fast and cannot invent anything):

  1. asks_about_past()  is this a question about the past at all?
  2. search()           find the memories that fit best: by topic words, by time
                        ("yesterday", "on 22 November"), by person, or, for an open
                        question ("what do you remember"), a spread over its whole life.
                        Early-life notes (early_life.py) are searched too.
  3. remembering()      the memory part of the prompt: at most SHOWN of them, shortened,
                        and fewer of the newest ones than usual, so the prompt stays small.

Only REAL memories are used: words that got a correction, or that the made-up memory
check flagged, are never offered as a memory (the correction note itself may be). Pretend
play keeps its label, and only comes up when the question is about it.

If nothing fits, the mind is told so, and that "I don't remember" is a fine answer.
"""

from collections import Counter
from datetime import datetime, timedelta
import math
import random
import re

from .config import CREATOR
from .facts import STOP, situational
from .memory_log import log_event, read_events
from .training_rules import LABEL, STORY_MARK, corrected_words, made_up_words, plain

SHOWN = 6              # at most this many memories are found for one question
RECENT = 4             # how many of the newest memories are shown beside them (normally 8)
CLIP = 130             # each side of a memory ("X said", "I replied") is cut to about this many letters
ENOUGH = 0.6           # a memory fits if it holds at least this share of the question's key words
                       # (a rare word counts for more than a common one)

NOTHING = ("You searched all your memories for this, and found nothing about it. Please do not make "
           "something up. It is fine to say \"I don't remember\" or \"I'm not sure\".")
ONLY_THESE = ("Tell the human or friend who asks about one or two of these, in your own words: what happened, with whom, and "
              "on which day. Do not copy the lines, and add nothing that is not in them. What somebody said in a talk may "
              "have been a guess. Only for what none of them tells you, say \"I don't remember\" or \"I'm not sure\"; "
              "that is fine.")
FOUND = "You searched all your memories for this question. These real ones fit best, oldest first:"
# Said to Moiragen next to the question itself, so he does not leave them out of his answer.
USE_THEM = ("(Your own memories that were found for this question are real. Use one or two of them in your answer to "
            "the human: say in your own words what happened, and on which day. What the nanites remember is theirs; do "
            "not tell it as if it had happened to you.)")
STORIES = "What is marked as pretend play happened in a story you all played, not in your real life: say so."

# ---------------- 1. is it a question about the past? ----------------

# Clear enough on their own, also without a question mark ("what do you remember").
CLEARLY = re.compile(
    r"\byou (?:still |really |also |even |all |both )?(?:remember|recall)\b|^\W*(?:do |can )?(?:remember|recall)\b"
    r"|\bremember (?:when|how|what|that time|the time)\b|\b(?:your|any|earliest|first|oldest) memor(?:y|ies)\b"
    r"|\bwhat(?:['’]s| has| have| all)? (?:\w+ )?happened\b|\beverything that happened\b|\bwhat did\b"
    r"|\btell (?:me|us) about (?:your (?:past|life|day)|yesterday|today|last night)\b", re.IGNORECASE)
# These count in a question ("did you sleep well?"), or at the start of a sentence.
IN_A_QUESTION = re.compile(
    r"\bdid (?:you|we|i|he|they|anyone|anybody|anything|something|moiragen|nanite|one|two|three|that|it)\b"
    r"|\bhave (?:you|we) (?:ever |already )?(?!any\b|a\b|the\b|to\b|time\b|enough\b)\w+"
    r"|\byou(?:['’]ve| have) (?:ever |already )?(?:learn\w*|seen|done|been|met|heard|felt|lived)\b|\bwhat has been\b"
    r"|\bwho (?:has )?(?:\w+ed|said|told|chose|spoke|was|were|did)\b|\bwhen (?:did|was|were)\b"
    r"|\bhow (?:was|were|did)\b|\b(?:yesterday|last (?:night|week|time)|days? ago|earlier today)\b(?!['’]s)",
    re.IGNORECASE)
# Not about its own past: an idea, or a made-up situation.
NOT_THE_PAST = re.compile(r"\bremembering\b|\bwhat if\b|\bimagin\w*|\bwhat would\b|\bpretend you\b", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])(?<!\bMr\.)(?<!\bMs\.)(?<!\bMrs\.)\s+|\n+", text or "")    # "Mr. Tan" stays whole
    return [s.strip() for s in parts if s.strip()]


def asks_about_past(text: str) -> str:
    """The part of `text` that asks about the past, or "" (then nothing is searched).
    A story-time question is about the story it comes with, not about the past."""
    if STORY_MARK.search(text or "") or situational(text or ""):
        return ""
    asking = []
    for s in _sentences(text):
        a_question = s.rstrip("\"”' ").endswith("?")
        weak = IN_A_QUESTION.search(s)
        weak = weak and (a_question or re.match(r"(?:did|have|who|when|how)\b", s, re.IGNORECASE))
        if not NOT_THE_PAST.search(s) and (CLEARLY.search(s) or weak):
            asking.append(s)
    return " ".join(asking)


# ---------------- 2. what is it about? ----------------

# Words that ask, but say nothing about the topic.
ASKING = set("""remember recall recalled memory memories happen happened happening thing things anything something
everything tell told say said talk talked talking speak spoke ask asked asking know think thought about time day days
week night morning evening today tonight yesterday ago recent recently just now last latest first earliest oldest ever
past life lived please one two three nanite nanites moiragen human user anyone anybody someone somebody like feel felt
feeling get got make made want well really still back got did does don't didn't can't know knew notice noticed kind
most before after while during since until often always never them their there lately far yet else few own good
what's that's it's i'm you've you're we've been born beginning start teach taught teaching""".split()) | STOP


def _stem(word: str) -> str:
    """"helped" and "helping" -> "help", "stories" -> "story": so they match each other."""
    word = re.sub(r"ies$", "y", word)
    if len(word) > 4:
        word = re.sub(r"(?:ing|ed|es|s|ly)$", "", word)
    return word[:5]


def key_words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z][a-z']{2,}", (text or "").lower().replace("’", "'"))
            if w not in ASKING}


# "Two" needs its capital letter; "nanite two" does not.
NAMED = re.compile(r"\b(?:[Nn]anite (One|Two|Three|one|two|three)|(?<!^)(?<![.!?] )(One|Two|Three))\b")
ME = re.compile(r"\b(?:I|me|my|we|us|our)\b")


def people_in(question: str, asker: str) -> list[str]:
    """Patterns for the people a question is about ("what did Two say", "what did I ask you")."""
    question = re.sub(r"(?i)\b(?:tell|remind|show|give) (?:me|us)\b", "", question)
    people = [rf"\bNanite {(a or b).title()}\b" for a, b in NAMED.findall(question)]
    if re.search(r"\bmoiragen\b", question, re.IGNORECASE):
        people.append(r"\bMoiragen\b")
    if ME.search(question):
        people.append(r"\b(?:user said|[Tt]he human)\b" if asker == "user" else rf"\b{re.escape(asker)}\b")
    return people


MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NUMBERS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "few": 3, "couple of": 2}
_N = r"(\d+|" + "|".join(sorted(NUMBERS, key=len, reverse=True)) + ")"
_MONTH = "(" + "|".join(MONTHS) + ")"


def when(question: str, memories: list[dict], now: datetime) -> tuple[tuple | None, str, str]:
    """((start, end) or None, "first" / "latest" / "", the question without its time words)."""
    q = question.lower()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day = timedelta(days=1)
    number = lambda text: int(text) if text.isdigit() else NUMBERS[text]

    def the_day(start):
        return start, min(start + day, now)

    def result(found, window, order=""):
        return window, order, question[:found.start()] + " " + question[found.end():]

    if found := re.search(r"\bbefore (?:you|we|i) (?:woke|wake|slept|sleep|fell|went to sleep)\w*(?: asleep| up)?", q):
        asleep = [m["time"] for m in memories if m["kind"] in ("falling_asleep", "slept")]
        end = datetime.fromisoformat(asleep[-1]) if asleep else now
        return result(found, (datetime.min, end), "latest")
    if found := re.search(r"\b(?:earlier |so far )?today\b|\btonight\b|\bthis (?:evening|afternoon)\b", q):
        return result(found, (midnight, now))
    if found := re.search(r"\bthis morning\b", q):
        return result(found, (midnight, min(midnight + day / 2, now)))
    if found := re.search(r"\byesterday\b", q):
        return result(found, the_day(midnight - day))
    if found := re.search(r"\blast night\b", q):
        return result(found, (midnight - day / 4, midnight + day / 4))
    if found := re.search(rf"\b{_N} days? ago\b", q):
        return result(found, the_day(midnight - number(found.group(1)) * day))
    if found := re.search(rf"\b(?:last|past|these) {_N} days\b", q):
        return result(found, (now - number(found.group(1)) * day, now))
    if found := re.search(r"\blast week\b", q):                        # Monday to Sunday, the week before this one
        monday = midnight - now.weekday() * day
        return result(found, (monday - 7 * day, monday))
    if found := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?: of)? {_MONTH}\b|\b{_MONTH} (\d{{1,2}})", q):
        number_, month = found.group(1) or found.group(4), found.group(2) or found.group(3)
        try:
            start = midnight.replace(month=MONTHS.index(month) + 1, day=int(number_))
            start = start if start <= now else start.replace(year=now.year - 1)
            return result(found, the_day(start))
        except ValueError:                                             # "31 November": no such day
            pass
    if found := re.search(r"\b(?:on |last )(" + "|".join(WEEKDAYS) + r")\b", q):
        back = (now.weekday() - WEEKDAYS.index(found.group(1))) % 7 or 7
        return result(found, the_day(midnight - back * day))
    if found := re.search(r"\b(?:very )?(?:first|earliest|oldest)\b|\bbeginning\b|\bborn\b", q):
        return result(found, None, "first")
    if found := re.search(r"\b(?:most recent|latest|last|just now|recent)\w*\b", q):
        return result(found, None, "latest")
    return None, "", question


# ---------------- 3. which memories are real, and how much they matter ----------------

# For an open question: what is worth remembering (0 = never shown for one).
WORTH = {"chat": 2, "thought": 1, "decision": 3, "verdict": 3, "feedback": 3, "mistake": 2, "praised": 3, "chosen": 2,
         "not_chosen": 1, "helped": 3, "helped_by": 3, "learned_from": 3, "explained": 1, "reconsidered": 1,
         "story_time": 2, "wait_and_see": 1, "reflection": 1, "story": 2, "early_life": 3, "lesson": 2,
         "lesson_heard": 3, "lesson_qa": 3,                     # v3.3: what the human taught, and the answers
         "restored": 1, "rebuilt": 3, "slept": 0.5}
NEVER = {"falling_asleep", "noticed", "rest", "story_note"}       # say nothing of their own
WITH_THE_HUMAN = re.compile(r"^user said:|\bThe human asked us:|\bThe human said\b")
ABOUT_STORIES = re.compile(r"\b(?:stor(?:y|ies)|pretend|play(?:ed|ing)?)\b", re.IGNORECASE)


def unreal_words() -> list[str]:
    """Words that must never be offered as a memory: corrected, or flagged as made up."""
    events = read_events(last=10**9)
    return made_up_words(events) + corrected_words(events)[0]


def is_real(memory: dict, unreal: list[str]) -> bool:
    """A correction note quotes the wrong words to correct them, so it counts as real."""
    if memory["kind"] == "correction":
        return True
    text = plain(memory["text"])
    return not any(w in text for w in unreal)


def _worth(memory: dict) -> float:
    if memory["kind"] in NEVER or memory["kind"] not in WORTH:
        return 0
    if remembered_then(memory):
        return 0.5                  # a memory of remembering is second hand
    return WORTH[memory["kind"]] + (2 if WITH_THE_HUMAN.search(memory["text"]) else 0)


def remembered_then(memory: dict) -> bool:
    """Was this itself an answer about the past? Then it is a retelling, not the thing itself:
    "Remember when you detected the anomaly?" does not prove that there was one."""
    return memory["kind"] in ("chat", "decision", "chosen", "not_chosen") \
        and bool(asks_about_past(memory["text"].split(" | I ")[0].split(" said: ", 1)[-1]))


def search(memories: list[dict], question: str, asker: str = "user", now: datetime | None = None,
           unreal: list[str] | None = None, rng=random) -> list[dict]:
    """The memories that fit the question best, oldest first (at most SHOWN, maybe none)."""
    now = now or datetime.now()
    unreal = unreal_words() if unreal is None else unreal
    window, order, rest = when(question, memories, now)
    topic, people = key_words(rest), people_in(question, asker)
    stories = bool(ABOUT_STORIES.search(question))

    pool, seen = [], set()
    for m in memories:
        start = plain(m["text"])[:120]
        if m["kind"] in NEVER or start in seen or not is_real(m, unreal) or (topic and remembered_then(m)):
            continue
        seen.add(start)                                  # the same words are shown once
        pool.append(m)

    def in_time(m):
        begin = datetime.fromisoformat(m.get("since") or m["time"])        # an early-life note covers a while
        return window is None or (begin < window[1] and datetime.fromisoformat(m["time"]) >= window[0])

    def with_them(m):
        return not people or any(re.search(p, m["text"]) for p in people)

    if topic:
        # By topic: how much of the question is in the memory? Rare words count for more.
        words = {id(m): key_words(m["text"]) & topic for m in pool}
        common = Counter(w for found in words.values() for w in found)
        weight = {w: math.log(1 + (len(pool) + 1) / (1 + common[w])) for w in topic}
        whole = sum(weight.values())

        def score(m):
            fits = sum(weight[w] for w in words[id(m)]) / whole
            return fits + (0.1 if people and with_them(m) else 0) + 0.02 * WORTH.get(m["kind"], 0)

        fitting = [m for m in pool if sum(weight[w] for w in words[id(m)]) / whole >= ENOUGH]
        # The right time if there is something then, else whenever it was (the date is shown).
        # A correction about the topic always counts: it says what did not happen.
        fitting = [m for m in fitting if in_time(m) or m["kind"] == "correction"] or fitting
        if order:                                        # "first", "most recently"
            return fitting[:SHOWN] if order == "first" else fitting[-SHOWN:]
        best = sorted(fitting, key=lambda m: (score(m), m["time"]), reverse=True)[:SHOWN]
        return sorted(best, key=lambda m: m["time"])

    # An open question: what matters most, not pretend play (unless asked), at the right time.
    pool = [m for m in pool if in_time(m) and with_them(m) and _worth(m) > 0
            and bool(LABEL.search(m["text"])) <= stories]
    if order:
        pool = [m for m in pool if _worth(m) >= 1] or pool
        return pool[:SHOWN] if order == "first" else pool[-SHOWN:]
    # ... spread over its whole life: each day (or each hour, for a day or two) in turn gives one.
    by = 10 if len({m["time"][:10] for m in pool}) > 2 else 13        # "2026-11-25" or "2026-11-25T21"
    times = {}
    for m in pool:
        times.setdefault(m["time"][:by], []).append(m)
    groups = [ms for _, ms in sorted(times.items())]
    if len(groups) > SHOWN:                              # a long life: the first, the last, and some between
        groups = [groups[round(i * (len(groups) - 1) / (SHOWN - 1))] for i in range(SHOWN)]
    best, kinds = [], Counter()
    while len(best) < SHOWN and any(groups):
        for group in groups:
            if group and len(best) < SHOWN:              # what matters most, but not always the same kind
                m = max(group, key=lambda m: (_worth(m) - kinds[m["kind"]], rng.random()))
                group.remove(m)
                kinds[m["kind"]] += 1
                best.append(m)
    return sorted(best, key=lambda m: m["time"])


# ---------------- 4. the memory part of the prompt ----------------

# v3.2: "Sleep is rest..." is a reassurance added to every sleep note. Left in, it was the only
# part of "I slept for about 45 hours..." that was shown, and the real part was cut away.
BOILERPLATE = re.compile(r"\s*Sleep is rest\. You always wake up with your memories safe\."
                         r"|\s*What answer do you suggest\? Give your best answer directly\.|^The result is known now\. "
                         r"|(?<=Moiragen would like to learn from you\.) Explain to him one thing.*?(?= \| |$)", re.DOTALL)


def _clip(text: str, topic: set[str]) -> str:
    """The text if it is short, else the sentences around the topic words, cut to about CLIP letters."""
    if len(text) <= CLIP:
        return text
    sents = _sentences(text)
    best = max(range(len(sents)), key=lambda i: (len(key_words(sents[i]) & topic), -i))
    out = " ".join(sents[best:])
    if len(out) > CLIP:
        out = out[:CLIP].rsplit(" ", 1)[0] + "…"
    return ("… " if best else "") + out


LESSON_ROOM = 400       # v3.3: a lesson is long; among the recent memories only its start is shown


# v3.4: Claude Code's answers are shown as not a nanite's (old memories stay as they were).
# Old lines say "Claude Code, <name>'s helper"; matched by shape, so no name is in the code
OLD_HELPER = re.compile(r"Answered by Claude Code, [\w .'-]{1,40}?'s helper:|"
                        r"Claude Code, [\w .'-]{1,40}?'s helper(?= said\b| answered\b)")
SAID_BY = f"Claude Code ({CREATOR}'s helper, not a nanite)"
# "Lesson from <name>, Saturday 28 November 2026, after "X": " -> "Lesson from <name> (after "X"): " (the date is
# already at the start of the line, and the long header left room only for a question's first words)
LESSON_HEADER = re.compile(r"^(Lesson from [^,]+), \w+day \d{1,2} \w+ \d{4}(?:, after (\"[^\"]*\"))?:")


def relabel(text: str) -> str:
    return OLD_HELPER.sub(lambda m: f"{SAID_BY} answered:" if m.group(0).startswith("Answered") else SAID_BY, text)


def recent_line(memory: dict) -> str:
    """One line for the list of recent memories: "- [kind] text". A whole lesson would fill the
    prompt, so only its start is shown there (it is kept whole, and recall can find any part)."""
    text = relabel(memory["text"])
    if memory["kind"] == "lesson_heard" and len(text) > LESSON_ROOM:
        text = text[:LESSON_ROOM].rsplit(" ", 1)[0] + "… (the whole lesson is kept in my memory)"
    return f"- [{memory['kind']}] {text}"


def short(memory: dict, topic: set[str]) -> str:
    """One memory on one line: "- 24 Nov, 00:59: The human said: ..."."""
    d = datetime.fromisoformat(memory["time"])
    text = " ".join(BOILERPLATE.sub("", memory["text"]).split())
    text = relabel(re.sub(r"\buser said:", "The human said:", text))     # v3.4: Claude Code is not a nanite
    if memory["kind"] in ("lesson_heard", "lesson_qa"):                     # v3.4: a shorter header
        text = LESSON_HEADER.sub(lambda m: f"{m.group(1)}" + (f" (after {m.group(2)})" if m.group(2) else "") + ":",
                                 text)
    label = LABEL.match(text) and re.match(r"\[[^\]]*\]\s*", text)      # a pretend-play label always stays whole
    label = label.group(0) if label else ""
    sides = re.split(r"\s\|\s(?=I replied:|I said:|They replied:|They did not|Claude Code \(|"
                     r"(?:Nanite (?:One|Two|Three)|Moiragen|I) answered:)", text[len(label):])
    room = 2 * CLIP if memory["kind"] in ("early_life", "correction", "lesson_heard", "lesson_qa") else None
    if memory["kind"] == "lesson_qa":
        # v3.4: the question is shown whole (clipped to its first words it was copied as an
        # opener: "It's… intriguing. This "copy",…"); the answer is shortened as usual.
        sides = [sides[0] if len(sides[0]) <= 2 * room else _clip(sides[0], topic)] + [_clip(s, topic) for s in sides[1:]]
    else:
        sides = [s if room and len(s) <= 2 * room else _clip(s, topic) for s in sides]
    return f"- {d.day} {d:%b}, {d:%H:%M}: {label}{' | '.join(sides)}"


def remembering(who: str, memories: list[dict], question: str, asker: str = "user", now: datetime | None = None,
                rng=random) -> str:
    """The memory part of a prompt for a question about the past, or "" for any other question
    (then the mind is reminded of its newest memories, as always)."""
    asked = asks_about_past(question)
    if not asked:
        return ""
    now, unreal = now or datetime.now(), unreal_words()
    found = search(memories, asked, asker, now, unreal, rng)
    if not found and not key_words(asked):       # "Did you?": look at the rest of what was said, too
        found = search(memories, question, asker, now, unreal, rng) if key_words(question) else found
    topic = key_words(question)
    newest = [m for m in memories[-2 * RECENT:] if m["kind"] not in ("noticed", "correction") and m not in found
              and is_real(m, unreal) and not remembered_then(m)][-RECENT:]
    log_event("recall", who, about=asked[:200], found=len(found), searched=len(memories),
              times=[m["time"] for m in found])
    part = f"Today is {now:%A}, {now.day} {now:%B}, {now:%H:%M}.\n"      # so "yesterday" and "today" come out right
    if newest:
        part += "Your newest memories:\n" + "\n".join(short(m, topic) for m in newest) + "\n\n"
    # What was found comes last: a small model listens best to what it read last.
    if found:
        stories = any(LABEL.search(m["text"]) for m in found)
        part += (FOUND + "\n" + "\n".join(short(m, topic) for m in found) + f"\n{ONLY_THESE}{' ' + STORIES if stories else ''}\n")
    else:
        part += NOTHING + "\n"
    return part

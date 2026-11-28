"""Turn Rounds (v3.1): a free conversation where everyone takes turns asking.

Each round has one asker and three answerers. The asker changes every round, always in
this order: Nanite One, Nanite Two, Nanite Three, Moiragen, then Nanite One again.
Moiragen is a normal member here, not the judge.

One round:
  1. ASK      The asker chooses its own question. Nobody gives it a topic or an example.
              Only if it asks a question it has asked before does it hear one soft nudge
              (NUDGE), once, and then whatever it asks is its question.
  2. ANSWER   The three others answer it, each in its own way (the usual echo guard,
              recall and honesty checks are on).
  3. RESPOND  The asker sees the answers as A, B and C, shuffled and without names, and
              replies however it likes: nobody tells it what to say or to choose anyone.
  4. REVEAL   Then it hears who wrote each answer, and may react if it wants to.
              The answerers hear what the asker said to them.
  5. MEMORY   Everyone remembers the whole round, with the date ("turn_round" memories),
              and the whole round is in the life log ("turn_round_full" event).

v3.2, after the first cycle:
  - The asker chooses its question with a mix of memories from its whole life in front of
    it (life_sample), not only its newest ones. Still no topics or examples.
  - The asker always has the round in front of it: "you are the asker, you asked ...".
  - A gentler echo check: only a line almost the same as one the same speaker said earlier
    in the same round is asked for again, once. No line is ever replaced by a stock line.
  - The asker hears that it may reply to each answer on its own, or to all of them together.
  - An answer to a question that is not about the past is told so, so "I don't remember"
    is said when it fits, not as a habit.

No judging: no scores, no health or mood changes, no lessons. Thinking costs energy as
always. Before each round, if a nanite's energy is below STOP_BELOW, the rounds stop so
they can sleep; next time the rounds carry on with the next asker in the order.

Fine-tuning: every line said in a round is labelled "turn_round" (the round's id) and a
task ("round_question", "round_answer", "round_response", "round_reaction"), so the
export can keep them in or leave them out (export.py --skip-rounds).
"""

from datetime import datetime
import difflib
import random
import re
import uuid

from .echo import NANITES, alike, guard as echo_guard, record_training_example, words
from .facts import false_past_claims
from .llm import think
from .memory_log import log_event, read_events
from .mind import FEELINGS_ARE_FINE, NOTHING_NEW, nanite_think, recent_memories_text
from .mother import MADE_OF_NANITES, Moiragen, brief, hide_names
from .nanite import Nanite
from .real_or_story import add_note
from .recall import LABEL, asks_about_past, is_real, short, unreal_words
from .training_rules import plain

ORDER = ["Nanite One", "Nanite Two", "Nanite Three", "Moiragen"]
LABELS = "ABC"
STOP_BELOW = 30          # a nanite below this energy needs to sleep before the next round
SAME_QUESTION = 0.8      # this alike (0..1) to one of its own earlier questions = asked before
NUDGE = "You've asked that before. You can ask something new if you like."
ALMOST_SAME = 0.9        # v3.2: this alike to its own earlier line in the round = said again
SAID_AGAIN = "You said almost exactly this already in this round. Say it in new words."
PER_PART = 2             # v3.2: memories taken from each part of its life for choosing a question
NOT_THE_PAST = ("(The question you are answering is not about your past. Say what you think or "
                "feel about it now.)")
CLIP = 160               # in the memory's text each part is cut to this many characters
                         # (the whole words are kept beside it, so prompts stay small)

# What everyone is told about Turn Rounds. No topics, no examples, no wording to copy.
ABOUT = ("This is Turn Rounds, a free conversation. Everyone takes turns asking a question, "
         "and the others answer. Nobody is judged and there are no right answers.")


# ---------------- 1. whose turn it is ----------------

def next_asker(events: list[dict] | None = None) -> str:
    """Who asks next: the one after the last round's asker (Nanite One to begin with)."""
    events = read_events(last=10**9) if events is None else events
    last = next((e.get("asker") for e in reversed(events) if e["kind"] == "turn_round_full"), None)
    return ORDER[(ORDER.index(last) + 1) % len(ORDER)] if last in ORDER else ORDER[0]


def answerers(asker: str) -> list[str]:
    """The other three, in the usual order, starting after the asker."""
    i = ORDER.index(asker)
    return [ORDER[(i + k) % len(ORDER)] for k in range(1, len(ORDER))]


def together(names: list[str]) -> str:
    """["Nanite Two", "Nanite Three", "Moiragen"] -> "Nanite Two, Nanite Three and Moiragen"."""
    return ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else "".join(names)


# ---------------- 2. a question asked before ----------------

def asked_before(who: str, question: str, events: list[dict] | None = None) -> str | None:
    """The earlier question of `who` that this one repeats, or None."""
    events = read_events(last=10**9) if events is None else events
    new = plain(question).strip(" ?!.")
    for e in events:
        if e["kind"] == "turn_round_full" and e.get("asker") == who:
            old = plain(e.get("question", "")).strip(" ?!.")
            if old and difflib.SequenceMatcher(None, new, old).ratio() >= SAME_QUESTION:
                return e["question"]
    return None


# ---------------- 3. blind answers ----------------

def blind(answers: dict[str, str], rng=random) -> tuple[dict[str, str], dict[str, str]]:
    """Shuffle the answers and label them A, B, C, with names in the words hidden.
    Returns ({"A": text the asker sees, ...}, {"A": "Nanite Two", ...})."""
    names = list(answers)
    rng.shuffle(names)
    shown = {letter: hide_names(answers[name]) for letter, name in zip(LABELS, names)}
    return shown, dict(zip(LABELS, names))


YOU_ASKED = "In this round you are the asker. You asked the others: \"{question}\""
BY_LETTER = ("You may reply to each answer on its own, by its letter, or to all of them together, "
             "in any way you like.")


def listed(shown: dict[str, str]) -> str:
    return "\n\n".join(f"Answer {letter}: \"{text}\"" for letter, text in shown.items())


def blind_text(question: str, shown: dict[str, str]) -> str:
    """What the asker sees: its own question and role, and the answers A, B, C. Nothing
    else is suggested; it does not have to choose anyone."""
    return (f"{ABOUT}\n{YOU_ASKED.format(question=question)}\n\nHere are their three answers, in a "
            f"random order and without names:\n\n{listed(shown)}\n\nNow you can reply to them. {BY_LETTER}")


def reveal_prompt(question: str, shown: dict[str, str], reply: str, reveal: str) -> str:
    """After the reveal the asker has the whole round in front of it (v3.2: Two once said "I
    don't recall initiating the inquiry" right after asking)."""
    return (f"{ABOUT}\n{YOU_ASKED.format(question=question)}\n\nTheir answers, without names:\n\n"
            f"{listed(shown)}\n\nYou replied: \"{reply}\"\n\nNow the names are revealed: {reveal}\n"
            "If you would like to say something about that, you can. You do not have to.")


# "Answer B ..." or "B: ..." at the start of a sentence (a plain "A" is just a word).
NAMES_A_LABEL = re.compile(r"\bAnswer ([ABC])\b|^\W*([ABC])\s*[:)\-–—]")


def split_reply(text: str) -> dict[str, str]:
    """Which part of the asker's reply was said to which answer.
    {"A": ..., "B": ..., "C": ..., "all": what was not said to one answer}. A sentence
    that names one answer starts a part for it; the sentences after it belong to it too,
    until another answer is named. A sentence that names two answers is said to all."""
    parts = {key: [] for key in (*LABELS, "all")}
    current = "all"
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if not sentence.strip():
            continue
        named = {a or b for a, b in NAMES_A_LABEL.findall(sentence)}
        if len(named) == 1:
            current = named.pop()
        elif len(named) > 1:
            current = "all"
        parts[current].append(sentence.strip())
    return {key: " ".join(lines) for key, lines in parts.items() if lines}


def reveal_text(names: dict[str, str]) -> str:
    """"Answer A was Nanite Two, Answer B was Moiragen and Answer C was Nanite Three." """
    return together([f"Answer {letter} was {name}" for letter, name in names.items()]) + "."


# ---------------- 4. speaking ----------------

IN_ROUNDS = "In Turn Rounds you are one of the group, taking turns like your nanites.\n"


def moiragen_speaks(m: Moiragen, message: str, round_id: str | None = None, task: str = "chat",
                    recall_about: str = "", situation: str = IN_ROUNDS, context: str | None = None,
                    memories: str | None = None, echo: bool = True, labels: dict | None = None) -> str:
    """Moiragen says something freely, as one of the group (in a round, or when the human
    talks to him directly). The echo guard is on (he is asked once for new words, then copied
    sentences are cut), and the line is labelled for the fine-tuning export. No verdicts are
    asked of him and none of his words are judged.
    round_id:     the round (also the echo guard's context), or None outside Turn Rounds
    recall_about: a question about the past: then all his memories are searched (recall.py).
    context:      for the echo guard, if not the round (see ask_context).
    memories:     (v3.2) the memory part of his prompt, chosen by the caller
    echo:         False in Turn Rounds, which has its own gentler check (v3.2)
    labels:       (v3.3) labels for the fine-tuning export, e.g. {"lesson": id}"""
    context = round_id if context is None else context
    if memories is None:
        memories = m.memories_text(recall_about) if recall_about else \
            f"Your recent memories:\n{m.recent_memories_text()}\n"
    system = (f"You are Moiragen, a digital being. {MADE_OF_NANITES}\n{FEELINGS_ARE_FINE}\n"
              f"{situation}{m.self_text()}{memories}"
              "Speak as yourself, as \"I\". Write only the words you say: no narration. Be honest; if you "
              "do not know, say so. Only use what is in your memories: do not invent past events. "
              "Keep it under 100 words.")
    messages = [{"role": "user", "content": message}]

    def copied(text: str) -> list[str]:
        return (echo_guard.check(text, NANITES, context, speaker="Moiragen").repeated
                + echo_guard.check(text, "Moiragen", context, speaker="Moiragen").repeated)

    text = brief(think(messages, temperature=0.6, max_tokens=200, system=system)["text"], 6)
    if echo and copied(text):
        log_event("echo_rejected", "Moiragen", text=text[:300], similar_to="turn rounds", attempt=1)
        again = messages + [{"role": "assistant", "content": text},
                            {"role": "user", "content": "That repeats words that were said very recently. "
                                                        "Say it again in your own, new words."}]
        text = brief(think(again, temperature=0.7, max_tokens=200, system=system)["text"], 6)
    gone = set(copied(text)) if echo else set()
    if gone:
        text = " ".join(s for s in re.split(r"(?<=[.!?])\s+", text) if s not in gone).strip()
    if not text:
        return NOTHING_NEW
    labels = {**({"decision_id": round_id, "turn_round": round_id} if round_id else {}), **(labels or {})}
    record_training_example("Moiragen", system, messages, text, "Moiragen", context, task=task, **labels)
    return text


def ask_context(asker: str) -> str:
    """The echo guard's context for an asker's questions. Its own earlier questions are left
    out of the echo check, so a repeated question hears only the soft NUDGE, nothing more."""
    return f"turn-rounds-asks:{asker}"


def _say_once(who: str, minds: dict, message: str, round_id: str, task: str, from_who: str,
              recall_about: str, context: str | None, remembered: str | None) -> str:
    if who == "Moiragen":
        if from_who != "user":
            message = f"{from_who} says: {message}"
        return moiragen_speaks(minds[who], message, round_id, task, recall_about, context=context,
                               memories=remembered, echo=False)
    out = nanite_think(minds[who], message, from_who=from_who, remember=False, save=False,
                       decision_id=round_id, task=task, recall_about=recall_about,
                       labels={"turn_round": round_id}, context=context, remembered=remembered, echo=False)
    return out["reply"]


def almost_same(text: str, earlier: list[str]) -> str | None:
    """The earlier line (of the same speaker, in the same round) that `text` nearly repeats."""
    mine = words(text)
    return next((e for e in earlier if alike(mine, words(e), ALMOST_SAME) >= ALMOST_SAME), None)


def speak(who: str, minds: dict, message: str, round_id: str, task: str, from_who: str = "user",
          recall_about: str = "", context: str | None = None, remembered: str | None = None,
          earlier: list[str] | None = None) -> str:
    """One member says something. A nanite thinks the usual way (energy, recall); nothing is
    remembered yet: the whole round is remembered at the end.

    The echo guard is gentler here (v3.2): only a line that is almost the same as one this
    speaker already said in this round (`earlier`) is asked for again, once, and whatever
    comes then is kept. Nothing is ever replaced by a stock line."""
    text = _say_once(who, minds, message, round_id, task, from_who, recall_about, context, remembered)
    again = almost_same(text, earlier or [])
    if again:
        log_event("round_echo", who, turn_round=round_id, text=text[:300], similar_to=again[:200])
        text = _say_once(who, minds, f"{message}\n\n{SAID_AGAIN}", round_id, task, from_who, recall_about,
                         context, remembered)
    if earlier is not None:
        earlier.append(text)
    return text


# ---------------- v3.2: memories from its whole life, for choosing a question ----------------

# The parts of a life. A memory belongs to the first part that fits it.
NOT_FOR_ASKING = {"noticed", "falling_asleep", "slept", "rest", "correction", "story_note", "surprise",
                  "early_life_note"}


HUM = re.compile(r"\bhum(?:ming|s)?\b", re.IGNORECASE)      # "the hum" they talk about (not "human")


def part_of_life(m: dict) -> str:
    text = m.get("text", "")
    if m["kind"] == "early_life":
        return "early life"
    if m["kind"] in ("slept", "rest", "falling_asleep"):
        return "sleep"
    if m["kind"] in ("lesson_heard", "lesson_qa"):
        return "lessons"
    if HUM.search(text):
        return "the hum"
    if m["kind"] in ("story_time", "story", "path_story") or LABEL.search(text):
        return "stories"
    if m["kind"] == "turn_round":
        return "turn rounds"
    if m["kind"] == "chat" and m.get("from_who") == "user" or text.startswith(("user said:", "The human said:")):
        return "the human"
    if m["kind"] == "chat" or re.match(r"(?:Nanite \w+|Moiragen) said:|I (?:told|asked) ", text):
        return "the others"
    return "thoughts"


def life_sample(memories: list[dict], rng=random, per_part: int = PER_PART, now: datetime | None = None,
                sleep: bool = False, header: str | None = None) -> str:
    """A mix of memories from all through its life, oldest first: its first days, stories, talks
    with the others, talks with the human (greetings), Turn Rounds, its own thoughts, and the
    newest. Nothing corrected or made up is offered. (Retellings may be: they are only something
    to ask from, and a greeting like "How did you sleep?" is one.) No topics are added.
    sleep:  (v3.3) its sleep notes are part of the mix too
    header: (v3.3) the line above the memories, instead of the usual one"""
    unreal = unreal_words()
    skip = NOT_FOR_ASKING - {"slept"} if sleep else NOT_FOR_ASKING
    real = [m for m in memories if m["kind"] not in skip and is_real(m, unreal)]
    first = real[:20]                                # its first days count as early life too
    parts: dict[str, list[dict]] = {}
    for m in real[:-3]:
        parts.setdefault("early life" if m in first else part_of_life(m), []).append(m)
    chosen = [m for group in parts.values() for m in rng.sample(group, min(per_part, len(group)))] + real[-3:]
    where = {id(m): i for i, m in enumerate(real)}
    chosen = sorted({id(m): m for m in chosen}.values(), key=lambda m: where[id(m)])     # as they were lived
    now = now or datetime.now()
    lines = "\n".join(short(m, set()) for m in chosen) or "(none yet)"
    header = header or "Some of your memories, from all through your life (a mix, oldest first):"
    return f"Today is {now:%A}, {now.day} {now:%B}.\n{header}\n{lines}\n"


def answer_memories(who: str, minds: dict, question: str) -> str | None:
    """For an answer: the usual memories. A question about the past searches them all (recall);
    any other question is said not to be about the past (v3.2), so "I don't remember" is not
    said out of habit."""
    if asks_about_past(question):
        return None
    mind = minds[who]
    recent = mind.recent_memories_text() if who == "Moiragen" else recent_memories_text(mind)
    return f"Your recent memories:\n{recent}\n\n{NOT_THE_PAST}\n"


def honesty(who: str, minds: dict, text: str, question: str, round_id: str, part: str) -> list[str]:
    """The usual honesty checks on one line: a claim about the past that the life log does
    not back up is logged ("round_flag", so it never becomes fine-tuning data), and a story
    told as if it were real gets the usual gentle note. The words themselves stay."""
    made_up = false_past_claims([{"nanite": who, "text": text}], question, round_id).get(who, [])
    if made_up:
        log_event("round_flag", who, turn_round=round_id, part=part, made_up=made_up)
    add_note(minds[who], text, question)
    return made_up


# ---------------- 5. one round ----------------

def too_tired(nanites: dict[str, Nanite]) -> list[str]:
    """The nanites whose energy is below STOP_BELOW."""
    return [n.name for n in nanites.values() if n.energy < STOP_BELOW]


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= CLIP else text[:CLIP - 1].rstrip() + "…"


def memory_text(r: dict, me: str) -> str:
    """The round in one memory for `me`: who asked, the question, every answer, what the
    asker said to them, and the reveal. Each part is short; the whole words are kept beside."""
    day = datetime.fromisoformat(r["time"]).strftime("%A %d %B %Y").replace(" 0", " ")
    asker = "I" if me == r["asker"] else r["asker"]
    lines = [f"Turn Rounds, {day}: {asker} asked: \"{_clip(r['question'])}\""]
    for letter, name in r["names"].items():
        who = "I" if name == me else name
        lines.append(f"Answer {letter} ({who}): \"{_clip(r['answers'][name])}\"")
    if r["reply"]:
        lines.append(f"{asker} replied to the answers, without knowing whose they were: \"{_clip(r['reply'])}\"")
    lines.append(f"Then the names were revealed. {r['reveal']}")
    if r["reaction"]:
        lines.append(f"{asker} said about that: \"{_clip(r['reaction'])}\"")
    return " | ".join(lines)


def turn_round(moiragen: Moiragen, nanites: dict[str, Nanite], asker: str | None = None,
               rng=random, notify=None) -> dict:
    """One whole round. Returns the round: {"id", "time", "asker", "question", "nudged",
    "answers" {name: text}, "shown" {A: text}, "names" {A: name}, "reply", "to" {A/B/C/all:
    part of the reply}, "reveal", "reaction", "flags" {name: [claims]}}."""
    minds = {n.name: n for n in nanites.values()}
    minds["Moiragen"] = moiragen
    asker = asker or next_asker()
    others = answerers(asker)
    rid = "r" + uuid.uuid4().hex[:7]
    time = datetime.now().isoformat(timespec="seconds")
    say = notify or (lambda *a, **k: None)
    say("turn_round_start", round_id=rid, asker=asker, answerers=others)

    # 1. ASK: its own question; one soft nudge only if it asked that before.
    say("thinking", who=asker, about="Turn Rounds: choosing a question")
    ask = f"{ABOUT}\nIt is your turn to ask. {together(others)} will answer. Write only your question."
    life = life_sample(minds[asker].memories, rng)            # v3.2: from its whole life
    question = speak(asker, minds, ask, rid, "round_question", context=ask_context(asker), remembered=life)
    before, nudged = asked_before(asker, question), False
    if before and question != NOTHING_NEW:
        nudged = True
        log_event("round_nudge", asker, turn_round=rid, question=question, asked_before=before)
        question = speak(asker, minds, f"{ask}\n\nYou wrote: \"{question}\"\n{NUDGE}", rid, "round_question",
                         context=ask_context(asker), remembered=life)
    question = question.strip().strip("\"“”")
    if question == NOTHING_NEW:                     # it had nothing to ask: the turn passes on
        log_event("turn_round_full", "mind", id=rid, asker=asker, question="", skipped=True,
                  text=f"Turn Rounds: {asker} had nothing to ask this time.")
        say("turn_round_end", id=rid, asker=asker, question="", skipped=True)
        return {"id": rid, "time": time, "asker": asker, "question": "", "skipped": True}
    say("turn_question", round_id=rid, asker=asker, question=question, nudged=nudged)

    # 2. ANSWER: each of the three, in its own way.
    answers = {}
    shown_order = list(others)
    rng.shuffle(shown_order)                       # the letters are given now, so the viewer stays blind
    letter_of = dict(zip(shown_order, LABELS))
    for name in others:
        say("thinking", who=name, about="Turn Rounds: answering")
        answers[name] = speak(name, minds, question, rid, "round_answer", from_who=asker, recall_about=question,
                              remembered=answer_memories(name, minds, question))
        say("turn_answer", round_id=rid, label=letter_of[name], text=hide_names(answers[name]))
    names = {letter: name for name, letter in letter_of.items()}
    names = dict(sorted(names.items()))
    shown = {letter: hide_names(answers[name]) for letter, name in names.items()}

    # 3. RESPOND: blind, in its own words.
    say("thinking", who=asker, about="Turn Rounds: replying to the answers")
    mine = [question]                              # what the asker said in this round (the gentle echo check)
    reply = speak(asker, minds, blind_text(question, shown), rid, "round_response", earlier=mine)
    to = split_reply(reply)
    say("turn_reply", round_id=rid, asker=asker, text=reply, to=to)

    # 4. REVEAL: who wrote what; the asker may react if it wants to.
    reveal = reveal_text(names)
    say("turn_reveal", round_id=rid, names=names, text=reveal)
    say("thinking", who=asker, about="Turn Rounds: the names")
    reaction = speak(asker, minds, reveal_prompt(question, shown, reply, reveal), rid, "round_reaction",
                     earlier=mine)
    say("turn_reaction", round_id=rid, asker=asker, text=reaction)

    # The usual honesty checks, on everything that was said.
    flags = {}
    for who, text, part in ([(asker, question, "question")] + [(n, answers[n], "answer") for n in others]
                            + [(asker, reply, "reply"), (asker, reaction, "reaction")]):
        found = honesty(who, minds, text, question, rid, part)
        if found:
            flags.setdefault(who, []).extend(found)

    # 5. MEMORY: everyone remembers the whole round, with the date.
    r = {"id": rid, "time": time, "asker": asker, "question": question, "nudged": nudged,
         "answers": answers, "shown": shown, "names": names, "reply": reply, "to": to,
         "reveal": reveal, "reaction": reaction, "flags": flags}
    log_event("turn_round_full", "mind", **{k: v for k, v in r.items() if k != "time"},
              text=f"Turn Rounds: {asker} asked \"{question}\"")
    for name, mind in minds.items():
        mine = {"turn_round": rid, "asker": asker, "question": question}
        if name in answers:
            letter = letter_of[name]
            mine.update(label=letter, my_answer=answers[name],
                        said_to_me=" ".join(x for x in (to.get(letter, ""), to.get("all", "")) if x))
        else:
            mine.update(answers=answers, names=names, reply=reply, reaction=reaction)
        mind.remember("turn_round", memory_text(r, name), **mine)
        mind.save()
    say("turn_round_end", **r)
    return r


def turn_rounds(moiragen: Moiragen, nanites: dict[str, Nanite], count: int = 4, rng=random,
                notify=None) -> dict:
    """Up to `count` rounds, each with the next asker in the order. Stops early (before a
    round) if a nanite is too tired: it sleeps, and next time the order carries on.
    Returns {"rounds": [...], "stopped": None or the tired nanites' names}."""
    rounds, stopped = [], None
    for _ in range(count):
        tired = too_tired(nanites)
        if tired:
            stopped = tired
            text = f"Turn Rounds paused: {together(tired)} need{'s' if len(tired) == 1 else ''} to sleep first."
            log_event("turn_rounds_paused", "mind", too_tired=tired, next_asker=next_asker(), text=text)
            if notify:
                notify("turn_rounds_paused", too_tired=tired, text=text)
            break
        rounds.append(turn_round(moiragen, nanites, rng=rng, notify=notify))
    return {"rounds": rounds, "stopped": stopped}

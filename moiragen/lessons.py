"""Lessons (v3.3): the human teaches, and everyone may ask questions.

Teaching only: nothing here gives Moiragen or the nanites any internet access, tools or
network calls. They hear words, think with the usual local model, and remember.

How a lesson goes:
  1. GIVE      The lesson is shared word for word with One, Two, Three and Moiragen, and
               saved in every memory, with the date ("lesson_heard", labelled "Lesson from ...").
  2. ASK       They take turns: One, Two, Three, Moiragen, then One again. Each may ask up to
               MAX_QUESTIONS, one at a time, in its own words, or say it has no question.
               When it chooses, it has a mix of real memories from its whole life in front of
               it (life_sample, sleep and early life included), with dates, and it hears every
               question and answer so far. Nobody suggests a topic, an example or wording.
  3. ANSWER    The human's helper (Claude Code) answers each question. The answer is saved in
               every memory as answered by Claude Code, the creator's helper, so they know who said it.

No judging: no scores, no health or mood changes. Asking costs energy, as thinking always does.
A lesson starts only if every nanite has at least READY energy.

Their questions, and the answers, go into the fine-tuning export with the label "lesson"
(export.py --skip-lessons leaves them out).

v3.4, after lessons 1 and 2:
  - The helper's answers are labelled "Claude Code (<creator>'s helper, not a nanite)" in every
    prompt and in new memories (Two had credited them to Nanite Three three times).
  - A question that copies words another member just asked in this lesson is asked for
    again, once, in its own words; whatever comes then is kept (Two once began with One's
    question word for word). Nothing is banned. (Copying its OWN earlier openings came from
    clipped memories, see recall.short.)

v3.5, a check-up for Two and nanites answering each other:
  - A question addressed to a member by name ("Three, explain...") is answered by that
    member first, in its own words; then the helper adds to it or gently corrects it, or
    says briefly that it was right. Memory: "Nanite Three answered: ..." and "Claude Code
    (<creator>'s helper, not a nanite) added: ...".
  - A member that asks a question it already asked in this lesson hears the same soft
    nudge as in Turn Rounds, once: "You've asked that before. You can ask something new if
    you like." Nothing more; whatever comes then is kept.

v3.6, fixes after lesson 4:
  - A member answers at most MAX_NAMED_ANSWERS named questions per lesson, and none while
    its energy is below ANSWER_ENERGY; then the helper answers (and says so kindly).
  - A member's answer that repeats its own earlier answer in this lesson is asked for once
    more, in new words; whatever comes then is kept.
  - Answering a named question is talking with each other, so it costs half (mind.py).
  - If Ollama refuses a prompt, the member keeps its turn. A prompt longer than the
    model's context is never cut: the lesson pauses ("lesson_paused") and can be
    resumed later from the life log (Lesson.resume), with the lesson text whole.

v3.7, copy checks after lesson 5:
  - A trailing "no question" is stripped before comparing for repeats or copies.
  - The copy check also compares with the helper's answers in the lesson (words in
    quotation marks are quoting, not copying).
  - Asked once for its own words, a member whose second try copies again (another
    member, the helper or itself) passes its turn: "chose not to ask" in its memory. Both
    attempts stay in the life log, out of memory and the export.
"""

from datetime import datetime
import difflib
import re
import uuid

from .config import CREATOR
from .echo import NANITES, EchoGuard, guard as echo_guard, record_training_example
from .facts import false_past_claims
from .llm import BrainError
from .memory_log import log_event, read_events
from .mind import nanite_think
from .real_or_story import add_note
from .training_rules import QUOTED, core, plain, without_no_question
from .turnrounds import NUDGE, ORDER, SAME_QUESTION, life_sample, moiragen_speaks, together

MAX_QUESTIONS = 3        # each member may ask up to this many questions
MAX_NAMED_ANSWERS = 2    # v3.6: a member answers at most this many named questions per lesson
ANSWER_ENERGY = 40       # v3.6: below this energy a member does not answer named questions
READY = 70               # a lesson starts only when every nanite has more energy than this
# v3.6: the creator's name comes from the local .env (config.CREATOR), never from the code
HELPER = f"Claude Code, {CREATOR}'s helper"                 # who says it, in the life log and the export
SAID_BY = f"Claude Code ({CREATOR}'s helper, not a nanite)"    # v3.4: how the minds see who answered
OWN_WORDS = ("Some of those words were just asked by someone else in this lesson. If you have a question of "
             "your own, ask it in your own words.")

# "no question", "I have no more questions", "Nothing to ask." (with no question mark)
NO_QUESTION = re.compile(r"^\W*(?:no(?: more| other| further)? questions?|i (?:have|don['’]t have) no(?: more)? "
                         r"questions?|i have no questions?|nothing(?: more)?(?: to ask)?(?: right now| now)?)\b",
                         re.IGNORECASE)
# v3.5: "Three, can you...", "Nanite One: could you..." at the start of a sentence
ADDRESSED = re.compile(r"(?:^|[.!?…]\s*)[\"“‘']?(?:Nanite\s+)?(One|Two|Three|Moiragen)\s*[,:]\s",
                       re.IGNORECASE)
ANSWERED_BY = "Answered by"         # (lessons 1 and 2; new memories say SAID_BY answered)
NEW_WORDS = "You can answer in new words if you like."


def too_long(error: Exception) -> bool:
    """Did Ollama refuse the prompt because it is longer than the model's context?"""
    return "context length" in str(error).lower()


def _day(when: str) -> str:
    return datetime.fromisoformat(when).strftime("%A %d %B %Y").replace(" 0", " ")


def has_no_question(text: str) -> bool:
    """Did it say it has no question? Only if it says so and asks nothing ("?")."""
    return "?" not in text and bool(NO_QUESTION.search(text.strip().strip("\"“”")))


def addressed_to(question: str, asker: str) -> str | None:
    """The member a question is addressed to by name ("Three, explain..."), or None."""
    for found in ADDRESSED.finditer(question):
        word = found.group(1).title()
        name = "Moiragen" if word == "Moiragen" else f"Nanite {word}"
        if name != asker:
            return name
    return None


def lesson_memories(memories: list[dict], rng=None, lesson_id: str = "") -> str:
    """The memory part of its prompt when it chooses a question: a mix from its whole life,
    with dates, nothing corrected or made up (see turnrounds.life_sample)."""
    import random
    memories = [m for m in memories if not lesson_id or m.get("lesson") != lesson_id]   # the lesson is shown whole
    return life_sample(memories, rng or random.Random(), sleep=True,
                       header="These are your own real memories, from all through your life, with their dates "
                              "(oldest first). They really happened, so you can talk about them honestly:")


class Lesson:
    """One lesson and the questions after it. Kept by the Mind while the questions go on."""

    def __init__(self, title: str, text: str, by: str = CREATOR, rng=None):
        import random
        self.id = "l" + uuid.uuid4().hex[:7]
        self.title, self.text, self.by = title, text, by
        self.time = datetime.now().isoformat(timespec="seconds")
        self.rng = rng or random.Random()
        self.asked = {name: 0 for name in ORDER}
        self.finished: set[str] = set()      # said it has no (more) questions, or asked MAX_QUESTIONS
        self.turn = 0                        # whose turn it is next, in ORDER
        self.pending: dict | None = None     # a question waiting for its answer
        self.qa: list[dict] = []             # {"who", "question", "answer", "number"}
        self.paused = False                  # v3.6: a prompt was too long; resume it later
        self.passes = {name: 0 for name in ORDER}    # v3.7: turns passed after copying twice
        self.passed: list[str] = []          # who passed, in order (shown in heard())

    @property
    def label(self) -> str:
        return f"Lesson from {self.by}"

    def state(self) -> dict:
        return {"id": self.id, "title": self.title, "by": self.by, "time": self.time, "qa": self.qa,
                "pending": self.pending, "asked": self.asked, "finished": sorted(self.finished),
                "done": self.done, "paused": self.paused, "said_by": SAID_BY}

    @property
    def done(self) -> bool:
        return self.pending is None and (self.paused or len(self.finished) == len(ORDER))

    @classmethod
    def resume(cls, lesson_id: str, rng=None) -> "Lesson":
        """A lesson that was paused (or cut off when the app closed), rebuilt from the life
        log: its text, the questions and answers so far, who is done, and whose turn it is.
        It is not given again; everyone already has it in memory (v3.6)."""
        events = [e for e in read_events(last=10**9) if e.get("lesson") == lesson_id]
        given = next((e for e in events if e["kind"] == "lesson_given"), None)
        if not given:
            raise ValueError(f"No lesson {lesson_id} in the life log.")
        lesson = cls(given["title"], given["text"], given.get("by", CREATOR), rng=rng)
        lesson.id, lesson.time = lesson_id, given["time"]
        last = None
        for e in events:
            if e["kind"] == "lesson_qa_full":
                who = e.get("detail_who", e["who"])        # (the log keeps the asker as "detail_who")
                keep = ("question", "number", "answer", "member", "member_answer", "member_skipped")
                lesson.qa.append({"who": who, **{k: e[k] for k in keep if k in e}})
                lesson.asked[who] = max(lesson.asked[who], e.get("number", 0))
                if lesson.asked[who] >= MAX_QUESTIONS:
                    lesson.finished.add(who)
                last = who
            elif e["kind"] == "lesson_no_question":
                lesson.finished.add(e["who"])
                last = e["who"]
            elif e["kind"] == "lesson_passed":
                lesson.passes[e["who"]] += 1
                lesson.passed.append(e["who"])
                if lesson.asked[e["who"]] + lesson.passes[e["who"]] >= MAX_QUESTIONS:
                    lesson.finished.add(e["who"])
                last = e["who"]
        lesson.turn = ORDER.index(last) + 1 if last else 0
        echo_guard.allow(lesson.text)
        log_event("lesson_resumed", "mind", lesson=lesson_id, title=lesson.title, questions=len(lesson.qa))
        return lesson

    def named_answers(self, member: str) -> int:
        """How many named questions this member has answered in this lesson."""
        return sum(1 for q in self.qa if q.get("member") == member and q.get("member_answer"))

    def cannot_answer(self, member: str, minds: dict) -> str | None:
        """Why a member does not answer a named question now (v3.6), or None."""
        if self.named_answers(member) >= MAX_NAMED_ANSWERS:
            return "answered_a_lot"
        if getattr(minds[member], "energy", 100) < ANSWER_ENERGY:
            return "tired"
        return None

    def pause(self, who: str, error: Exception, notify=None) -> dict:
        """The prompt was longer than the model's context: nothing is cut; the lesson pauses
        and can go on next time (Lesson.resume)."""
        self.paused = True
        log_event("lesson_paused", "mind", lesson=self.id, who=who, error=str(error)[:300],
                  questions=len(self.qa))
        if notify:
            notify("lesson_paused", lesson=self.id, who=who, questions=len(self.qa))
        return {"who": who, "question": None, "number": 0, "done": True, "paused": True}

    # ---------- 1. give the lesson ----------

    def give(self, minds: dict, notify=None) -> None:
        """Share the lesson, word for word, and save it in every memory with the date."""
        echo_guard.allow(self.text)                  # anyone may use the lesson's own words
        log_event("lesson_given", "mind", lesson=self.id, title=self.title, by=self.by, text=self.text)
        for mind in minds.values():
            mind.remember("lesson_heard", f"{self.label}, {_day(self.time)}: \"{self.title}\". {self.by} said: "
                                         f"{self.text}", lesson=self.id, title=self.title, by=self.by)
            mind.save()
        if notify:
            notify("lesson_start", lesson=self.id, title=self.title, by=self.by, text=self.text, time=self.time)

    # ---------- 2. the next question ----------

    def heard(self) -> str:
        if not self.qa:
            return "Nobody has asked a question yet."
        lines = []
        for q in self.qa:
            lines.append(f"- {q['who']} asked: \"{q['question']}\"")
            if q.get("member_answer"):
                lines.append(f"  {q['member']} answered: \"{q['member_answer']}\"")
                lines.append(f"  {SAID_BY} added: \"{q['answer']}\"")
            else:
                lines.append(f"  {SAID_BY} answered: \"{q['answer']}\"")
        lines += [f"- {name} chose not to ask this turn." for name in self.passed]
        return "Questions already asked after this lesson, and their answers:\n" + "\n".join(lines)

    def ask_prompt(self, who: str) -> str:
        left = MAX_QUESTIONS - self.asked[who]
        return (f"{self.by} (the human) shares a lesson with you, \"{self.title}\":\n\n{self.text}\n\n"
                f"{self.heard()}\n\n"
                f"Now you may ask a question of your own, in your own words. {SAID_BY} will answer it. "
                f"You can ask {left} more question{'s' if left != 1 else ''}, one at a time. "
                "If you have no question, write only: no question.")

    def next_question(self, minds: dict, notify=None) -> dict:
        """Let the next member choose a question (or none). Returns {"who", "question" or
        None, "number", "done"}. The question waits for answer() before the next one."""
        if self.pending:
            raise ValueError(f"{self.pending['who']}'s question is waiting for its answer first.")
        while len(self.finished) < len(ORDER):
            who = ORDER[self.turn % len(ORDER)]
            self.turn += 1
            if who in self.finished:
                continue
            if notify:
                notify("lesson_thinking", lesson=self.id, who=who)
            try:
                text, passed = self._speak(who, minds)
            except BrainError as e:
                self.turn -= 1                           # v3.6: it keeps its turn
                if too_long(e):
                    return self.pause(who, e, notify)
                raise
            if passed:                                   # v3.7: copied again after being asked
                self.pass_turn(who, passed, minds, notify)
                continue
            if not text or has_no_question(text):
                self.finished.add(who)
                log_event("lesson_no_question", who, lesson=self.id, text=text,
                          after=self.asked[who])
                if notify:
                    notify("lesson_no_question", lesson=self.id, who=who, after=self.asked[who])
                continue
            self.asked[who] += 1
            if self.asked[who] + self.passes[who] >= MAX_QUESTIONS:
                self.finished.add(who)
            self.pending = {"who": who, "question": text, "number": self.asked[who]}
            self._honesty(who, minds, text)
            if notify:
                notify("lesson_question", lesson=self.id, **self.pending)
            member = addressed_to(text, who)
            why = self.cannot_answer(member, minds) if member else None
            if why:                                      # v3.6: the helper answers instead
                self.pending.update(member=member, member_skipped=why)
                log_event("lesson_member_rests", member, lesson=self.id, why=why,
                          answered=self.named_answers(member), energy=getattr(minds[member], "energy", None))
            elif member:                                 # v3.5: the one it asked answers first
                if notify:
                    notify("lesson_thinking", lesson=self.id, who=member)
                try:
                    said = self.member_answers(member, who, text, minds)
                except BrainError as e:                  # its question still stands; the helper answers
                    self.pending.update(member=member, member_skipped="too_long" if too_long(e) else "unavailable")
                    log_event("lesson_member_rests", member, lesson=self.id, why=self.pending["member_skipped"],
                              error=str(e)[:300])
                else:
                    self.pending.update(member=member, member_answer=said)
                    self._honesty(member, minds, said)
                    if notify:
                        notify("lesson_member_answer", lesson=self.id, who=who, number=self.pending["number"],
                               member=member, text=said)
            return {**self.pending, "done": False}
        if notify:
            notify("lesson_end", lesson=self.id, questions=len(self.qa))
        return {"who": None, "question": None, "number": 0, "done": True}

    def member_answers(self, member: str, asker: str, question: str, minds: dict) -> str:
        """A member answers a question addressed to it, in its own words (v3.5). It has the
        lesson and everything said after it in front of it, and its own memories."""
        text = self._answer_once(member, asker, question, minds)
        earlier = self.answered_already(member, text)
        if earlier:
            # v3.6: its own earlier answer, word for word: asked once for new words; whatever comes is kept
            log_event("lesson_answer_nudge", member, lesson=self.id, text=text[:300])
            text = self._answer_once(member, asker, f"{question}\n\n(You already answered with these words "
                                                    f"earlier in this lesson: \"{earlier}\" {NEW_WORDS})",
                                     minds)
        return text

    def _answer_once(self, member: str, asker: str, question: str, minds: dict) -> str:
        mind = minds[member]
        context = (f"Today {self.by} (the human) shared a lesson with you, \"{self.title}\":\n{self.text}\n\n"
                   f"{self.heard()}\n\n{lesson_memories(mind.memories, self.rng, self.id)}")
        labels = {"lesson": self.id}
        if member == "Moiragen":
            text = moiragen_speaks(mind, f"{asker} asks you: {question}", None, "lesson_member_answer",
                                   situation="", memories=context, echo=False,
                                   labels={"decision_id": self.id, **labels})
        else:
            text = nanite_think(mind, question, from_who=asker, remember=False, decision_id=self.id,
                                task="lesson_member_answer", labels=labels, context=f"lesson-answers:{member}",
                                remembered=context, echo=False, talk=True)["reply"]
        return " ".join(text.split()).strip("\"“”")

    def answered_already(self, member: str, text: str) -> str | None:
        """Its own earlier answer in this lesson that this one repeats (v3.6)."""
        new = plain(text).strip(" ?!.")
        for q in self.qa:
            old = plain(q.get("member_answer", "")).strip(" ?!.")
            if q.get("member") == member and old and difflib.SequenceMatcher(None, new, old).ratio() >= SAME_QUESTION:
                return q["member_answer"]
        return None

    def asked_already(self, who: str, text: str) -> str | None:
        """Its own earlier question in this lesson that this one repeats (as in Turn Rounds)."""
        new = core(text)                         # v3.7: a trailing "no question" never counts
        for q in self.qa:
            old = core(q["question"])
            if q["who"] == who and old and difflib.SequenceMatcher(None, new, old).ratio() >= SAME_QUESTION:
                return q["question"]
        return None

    def copied(self, who: str, text: str) -> bool:
        """Does it copy words another member asked in this lesson? The usual echo rules
        (a sentence, an opener, a 5-word phrase or most of the line), against their
        questions and, since v3.7, the helper's answers; the lesson's own words may be used
        freely, and so may words in quotation marks (quoting is not copying)."""
        others = EchoGuard(seed_from_log=False)
        others.allow(self.text)
        for q in self.qa:
            if q["who"] != who:
                others.add(q["who"], without_no_question(q["question"]), NANITES)
            others.add(HELPER, q["answer"], NANITES)
        mine = " ".join(QUOTED.sub(" ", without_no_question(text)).split())
        return bool(mine) and others.check(mine, NANITES, speaker=who).too_similar

    def pass_turn(self, who: str, attempts: list[str], minds: dict, notify=None) -> None:
        """v3.7: it copied again after being asked for its own words, so it passes this turn.
        Both attempts stay in the life log for the record (out of memory and the export)."""
        self.passes[who] += 1
        self.passed.append(who)
        if self.asked[who] + self.passes[who] >= MAX_QUESTIONS:
            self.finished.add(who)
        log_event("lesson_passed", who, lesson=self.id, attempts=attempts, after=self.asked[who])
        mind = minds[who]
        mind.remember("lesson_pass", f"{self.label}, {_day(self.time)}, after \"{self.title}\": "
                                     f"I chose not to ask this turn.", lesson=self.id)
        mind.save()
        if notify:
            notify("lesson_pass", lesson=self.id, who=who)

    def _speak(self, who: str, minds: dict) -> tuple[str, list[str] | None]:
        """Its question, and None; or, when it copied again after being asked for its own
        words, its last words and both attempts (then it passes its turn, v3.7)."""
        text = self._speak_once(who, minds, self.ask_prompt(who))
        if not text or has_no_question(text):
            return text, None
        if self.asked_already(who, text):
            # v3.5: the same soft nudge as in Turn Rounds, once
            log_event("lesson_nudge", who, lesson=self.id, text=text[:300], attempt=text)
            again = f"{self.ask_prompt(who)}\n\nYou wrote: \"{text}\"\n{NUDGE}"
        elif self.copied(who, text):
            log_event("lesson_echo", who, lesson=self.id, text=text[:300], attempt=text)
            again = f"{self.ask_prompt(who)}\n\n{OWN_WORDS}"
        else:
            return text, None
        second = self._speak_once(who, minds, again)
        if second and not has_no_question(second) and (self.asked_already(who, second) or self.copied(who, second)):
            return second, [text, second]                # v3.7: a second copy is a pass
        return second, None

    def _speak_once(self, who: str, minds: dict, prompt: str) -> str:
        mind = minds[who]
        memories = lesson_memories(mind.memories, self.rng, self.id)
        labels = {"lesson": self.id}
        if who == "Moiragen":
            text = moiragen_speaks(mind, prompt, None, "lesson_question", situation="", memories=memories,
                                   echo=False, labels={"decision_id": self.id, **labels})
        else:
            text = nanite_think(mind, prompt, from_who="user", remember=False, decision_id=self.id,
                                task="lesson_question", labels=labels, context=f"lesson-asks:{who}",
                                remembered=memories, echo=False)["reply"]
        return " ".join(text.split()).strip("\"“”")

    def _honesty(self, who: str, minds: dict, text: str) -> None:
        """The usual checks: a made-up claim about the past is logged (and kept out of the
        export); a story told as if it were real gets the usual gentle note. Words stay."""
        made_up = false_past_claims([{"nanite": who, "text": text}], self.title, self.id).get(who, [])
        if made_up:
            log_event("lesson_flag", who, lesson=self.id, made_up=made_up)
        add_note(minds[who], text, self.title)

    # ---------- 3. the answer ----------

    def answer(self, text: str, minds: dict, notify=None) -> dict:
        """The helper's answer to the waiting question, saved in every memory with the date."""
        if not self.pending:
            raise ValueError("There is no question waiting for an answer.")
        text = " ".join((text or "").split())
        if not text:
            raise ValueError("Empty answer")
        q = {**self.pending, "answer": text}
        self.qa.append(q)
        self.pending = None
        log_event("lesson_qa_full", "mind", lesson=self.id, title=self.title, by=self.by, **q,
                  answered_by=HELPER)
        member = q.get("member") if q.get("member_answer") else None
        for name, mind in minds.items():
            asker = "I" if name == q["who"] else q["who"]
            first = ""
            if member:                                      # v3.5: the member it asked answered first
                first = f" | {'I' if name == member else member} answered: \"{q['member_answer']}\""
            mind.remember("lesson_qa", f"{self.label}, {_day(self.time)}, after \"{self.title}\": {asker} asked: "
                                       f"\"{q['question']}\"{first} | {SAID_BY} {'added' if member else 'answered'}: "
                                       f"\"{text}\"",
                          lesson=self.id, asker=q["who"], question=q["question"], answer=text,
                          answered_by=HELPER, **({"member": member, "member_answer": q["member_answer"]}
                                                 if member else {}))
            mind.save()
        # Labelled for the export; the helper's own words, never a mind's.
        asked = f"{q['who']} asks: {q['question']}"
        if member:
            asked += f"\n{member} answered: {q['member_answer']}"
        record_training_example(HELPER, f"You are {HELPER}. You answer a question after {self.by}'s lesson "
                                        f"\"{self.title}\", simply, kindly and honestly"
                                        + (", adding to or gently correcting a member's answer." if member else "."),
                                [{"role": "user", "content": asked}], text,
                                HELPER, self.id, task="lesson_answer", lesson=self.id)
        if notify:
            notify("lesson_answer", lesson=self.id, **q, answered_by=HELPER, said_by=SAID_BY)
        return q


def low_energy(nanites: dict) -> list[str]:
    """The nanites that need to rest before a lesson."""
    return [n.name for n in nanites.values() if n.energy <= READY]


def not_ready_text(names: list[str]) -> str:
    return f"{together(names)} need{'s' if len(names) == 1 else ''} to rest first (energy {READY} or less)."

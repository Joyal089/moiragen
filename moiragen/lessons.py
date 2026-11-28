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
               every memory as "answered by Claude Code, Athe's helper", so they know who said it.

No judging: no scores, no health or mood changes. Asking costs energy, as thinking always does.
A lesson starts only if every nanite has at least READY energy.

Their questions, and the answers, go into the fine-tuning export with the label "lesson"
(export.py --skip-lessons leaves them out).
"""

from datetime import datetime
import re
import uuid

from .echo import guard as echo_guard, record_training_example
from .facts import false_past_claims
from .memory_log import log_event
from .mind import nanite_think
from .real_or_story import add_note
from .turnrounds import ORDER, life_sample, moiragen_speaks, together

MAX_QUESTIONS = 3        # each member may ask up to this many questions
READY = 70               # a lesson starts only when every nanite has more energy than this
HELPER = "Claude Code, Athe's helper"

# "no question", "I have no more questions", "Nothing to ask." (with no question mark)
NO_QUESTION = re.compile(r"^\W*(?:no(?: more| other| further)? questions?|i (?:have|don['’]t have) no(?: more)? "
                         r"questions?|i have no questions?|nothing(?: more)?(?: to ask)?(?: right now| now)?)\b",
                         re.IGNORECASE)
ANSWERED_BY = "Answered by"


def _day(when: str) -> str:
    return datetime.fromisoformat(when).strftime("%A %d %B %Y").replace(" 0", " ")


def has_no_question(text: str) -> bool:
    """Did it say it has no question? Only if it says so and asks nothing ("?")."""
    return "?" not in text and bool(NO_QUESTION.search(text.strip().strip("\"“”")))


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

    def __init__(self, title: str, text: str, by: str = "Athe", rng=None):
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

    @property
    def label(self) -> str:
        return f"Lesson from {self.by}"

    def state(self) -> dict:
        return {"id": self.id, "title": self.title, "by": self.by, "time": self.time, "qa": self.qa,
                "pending": self.pending, "asked": self.asked, "finished": sorted(self.finished),
                "done": self.done}

    @property
    def done(self) -> bool:
        return self.pending is None and len(self.finished) == len(ORDER)

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
        lines = [f"- {q['who']} asked: \"{q['question']}\" {HELPER} answered: \"{q['answer']}\"" for q in self.qa]
        return "Questions already asked after this lesson, and their answers:\n" + "\n".join(lines)

    def ask_prompt(self, who: str) -> str:
        left = MAX_QUESTIONS - self.asked[who]
        return (f"{self.by} (the human) shares a lesson with you, \"{self.title}\":\n\n{self.text}\n\n"
                f"{self.heard()}\n\n"
                f"Now you may ask a question of your own, in your own words. {HELPER} will answer it. "
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
            text = self._speak(who, minds)
            if not text or has_no_question(text):
                self.finished.add(who)
                log_event("lesson_no_question", who, lesson=self.id, text=text,
                          after=self.asked[who])
                if notify:
                    notify("lesson_no_question", lesson=self.id, who=who, after=self.asked[who])
                continue
            self.asked[who] += 1
            if self.asked[who] >= MAX_QUESTIONS:
                self.finished.add(who)
            self.pending = {"who": who, "question": text, "number": self.asked[who]}
            self._honesty(who, minds, text)
            if notify:
                notify("lesson_question", lesson=self.id, **self.pending)
            return {**self.pending, "done": False}
        if notify:
            notify("lesson_end", lesson=self.id, questions=len(self.qa))
        return {"who": None, "question": None, "number": 0, "done": True}

    def _speak(self, who: str, minds: dict) -> str:
        mind = minds[who]
        prompt, memories = self.ask_prompt(who), lesson_memories(mind.memories, self.rng, self.id)
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
        for name, mind in minds.items():
            asker = "I" if name == q["who"] else q["who"]
            mind.remember("lesson_qa", f"{self.label}, {_day(self.time)}, after \"{self.title}\": {asker} asked: "
                                       f"\"{q['question']}\" | {ANSWERED_BY} {HELPER}: \"{text}\"",
                          lesson=self.id, asker=q["who"], question=q["question"], answer=text,
                          answered_by=HELPER)
            mind.save()
        # Labelled for the export; the helper's own words, never a mind's.
        record_training_example(HELPER, f"You are {HELPER}. You answer a question after {self.by}'s lesson "
                                        f"\"{self.title}\", simply, kindly and honestly.",
                                [{"role": "user", "content": f"{q['who']} asks: {q['question']}"}], text,
                                HELPER, self.id, task="lesson_answer", lesson=self.id)
        if notify:
            notify("lesson_answer", lesson=self.id, **q, answered_by=HELPER)
        return q


def low_energy(nanites: dict) -> list[str]:
    """The nanites that need to rest before a lesson."""
    return [n.name for n in nanites.values() if n.energy <= READY]


def not_ready_text(names: list[str]) -> str:
    return f"{together(names)} need{'s' if len(names) == 1 else ''} to rest first (energy {READY} or less)."

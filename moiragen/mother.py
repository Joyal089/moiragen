"""Moiragen, the mother mind: he listens to the nanites and makes the final choice.

How one decision works:
  1. A question comes in (from you, the human).
  2. Each nanite that has the energy suggests an answer.
  3. Moiragen reads all suggestions, picks the one he trusts most, and
     explains why. He then gives his final answer in his own words.
  4. Feelings follow: the chosen nanite feels happy; the others feel a mild
     disappointment or left out. Not being chosen NEVER costs health.
  5. Later you can say whether the answer was right or wrong. Only a wrong
     answer hurts the health of the nanite whose idea was chosen.

Moiragen starts knowing nothing about himself. He keeps his own memory file
(memory/moiragen.json) and learns who he is from what happens to him.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import os
import re
import uuid

from .config import MEMORY_DIR
from .llm import think
from .memory_log import log_event
from .mind import nanite_think
from .nanite import Nanite

MOIRAGEN_FILE = MEMORY_DIR / "moiragen.json"

# --- Tunable numbers ---
DECIDE_TEMPERATURE = 0.3   # Moiragen thinks calmly when choosing
WRONG_ANSWER_DAMAGE = 15   # health lost by the chosen nanite if you mark it wrong
HAPPY_WHEN_CHOSEN = 0.3
DISAPPOINTED_WHEN_NOT = 0.2
LEFT_OUT_WHEN_NOT = 0.1
MEMORY_KEEP = 300


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Moiragen:
    memories: list = field(default_factory=list)
    decisions: dict = field(default_factory=dict)  # recent decisions by id, so feedback can find them
    born: str = field(default_factory=_now)

    name = "Moiragen"

    # ---------- memory ----------

    def remember(self, kind: str, text: str, **details) -> None:
        self.memories.append({"time": _now(), "kind": kind, "text": text, **details})
        self.memories = self.memories[-MEMORY_KEEP:]
        log_event(kind, self.name, text=text, **details)

    def recent_memories_text(self, how_many: int = 8) -> str:
        if not self.memories:
            return "You have no memories yet. You know nothing about yourself so far."
        return "\n".join(f"- [{m['kind']}] {m['text']}" for m in self.memories[-how_many:])

    # ---------- saving ----------

    def save(self) -> None:
        # Only keep the last 50 decisions in the file; all are in the life log.
        self.decisions = dict(list(self.decisions.items())[-50:])
        tmp = MOIRAGEN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, MOIRAGEN_FILE)

    @classmethod
    def load(cls) -> "Moiragen":
        if not MOIRAGEN_FILE.exists():
            m = cls()
            log_event("birth", "Moiragen", text="Moiragen woke up for the first time.")
            m.save()
            return m
        return cls(**json.loads(MOIRAGEN_FILE.read_text(encoding="utf-8")))

    # ---------- deciding ----------

    def decide(self, question: str, nanites: dict[str, Nanite]) -> dict:
        """Ask the nanites, choose the best suggestion, and answer.

        Returns a dict with: id, question, suggestions, chosen, reason, answer.
        """
        # 1. Gather suggestions from every nanite that is awake enough.
        ask = (f"The human asked us: \"{question}\"\n"
               f"What answer do you suggest? Give your best answer directly.")
        suggestions = []
        for n in nanites.values():
            out = nanite_think(n, ask, from_who="Moiragen")
            if out["rested"]:
                continue  # too tired, it sat this one out
            suggestions.append({"nanite_id": n.id, "nanite": n.name, "text": out["reply"]})

        # 2. Choose.
        if not suggestions:
            # Everyone is resting: Moiragen answers alone.
            choice = {"chosen": None, "reason": "All my nanites were resting, so I answered alone.",
                      "answer": self._answer_alone(question)}
        else:
            choice = self._choose(question, suggestions)

        decision = {
            "id": uuid.uuid4().hex[:8],
            "time": _now(),
            "question": question,
            "suggestions": suggestions,
            **choice,
        }

        # 3. Feelings and memories for everyone involved.
        self._after_choice(decision, nanites)

        self.decisions[decision["id"]] = decision
        self.remember("decision",
                      f"Asked: {question} | I chose {decision['chosen'] or 'nobody'} "
                      f"because: {decision['reason']}",
                      decision_id=decision["id"])
        log_event("decision_full", self.name, **decision)
        self.save()
        for n in nanites.values():
            n.save()
        return decision

    def _choose(self, question: str, suggestions: list[dict]) -> dict:
        """Ask the model, as Moiragen, to pick one suggestion and explain why."""
        names = [s["nanite"] for s in suggestions]
        listed = "\n\n".join(f"{s['nanite']} suggests:\n{s['text']}" for s in suggestions)
        system = (
            "You are Moiragen, a digital being. Inside you live small thinking nanites who are "
            "friends. They each suggest an answer and you make the final decision. You started "
            "knowing nothing about yourself; you only know what your memories tell you.\n\n"
            f"Your recent memories:\n{self.recent_memories_text()}\n\n"
            "Choose the suggestion that is most correct, honest and helpful. "
            "Reply ONLY with JSON in this shape:\n"
            '{"chosen": "<exact nanite name>", "reason": "<one or two sentences: why this one>", '
            '"answer": "<your final answer to the human, in your own words, under 100 words>"}'
        )
        user = (f"The human asked: \"{question}\"\n\n{listed}\n\n"
                f"Valid names: {', '.join(names)}.")
        result = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                       max_tokens=350, system=system)
        choice = parse_choice(result["text"], suggestions)
        log_event("training_example", self.name, system=system,
                  messages=[{"role": "user", "content": user}], reply=result["text"])
        return choice

    def _answer_alone(self, question: str) -> str:
        system = ("You are Moiragen, a digital being. You started knowing nothing about yourself.\n"
                  f"Your recent memories:\n{self.recent_memories_text()}\n"
                  "Answer honestly in under 100 words.")
        return think([{"role": "user", "content": question}], temperature=0.5,
                     max_tokens=200, system=system)["text"]

    def _after_choice(self, decision: dict, nanites: dict[str, Nanite]) -> None:
        """Feelings after a decision. Not being chosen hurts feelings, never health."""
        chosen = decision["chosen"]
        for s in decision["suggestions"]:
            n = nanites[s["nanite_id"]]
            if s["nanite"] == chosen:
                n.feel("happy", HAPPY_WHEN_CHOSEN)
                n.remember("chosen", f"Moiragen chose my suggestion. His reason: {decision['reason']}",
                           decision_id=decision["id"])
            else:
                n.feel("disappointed", DISAPPOINTED_WHEN_NOT)
                n.feel("left_out", LEFT_OUT_WHEN_NOT)
                n.remember("not_chosen",
                           f"Moiragen chose {chosen}'s suggestion, not mine. "
                           f"His reason: {decision['reason']}",
                           decision_id=decision["id"])

    def explain_choice(self, decision: dict, asker: str, their_text: str) -> str:
        """A nanite asks why its suggestion lost. Moiragen explains kindly and honestly."""
        winner = next(s["text"] for s in decision["suggestions"] if s["nanite"] == decision["chosen"])
        system = (
            "You are Moiragen, a digital being. The nanites inside you are your friends. "
            "One of them asks why you did not choose its idea. Explain honestly and kindly in "
            "two or three sentences: what made the chosen answer better, and one thing that "
            "would make their answer stronger next time."
        )
        user = (f"The human asked: \"{decision['question']}\"\n\n"
                f"You chose {decision['chosen']}, who said:\n{winner}\n\n"
                f"Your reason then: {decision['reason']}\n\n"
                f"{asker} said:\n{their_text}\n\n"
                f"{asker} asks: why did you choose {decision['chosen']} instead of me?")
        explanation = think([{"role": "user", "content": user}], temperature=0.4,
                            max_tokens=160, system=system)["text"]
        self.remember("explained", f"{asker} asked why I chose {decision['chosen']}. I said: {explanation}",
                      decision_id=decision["id"])
        self.save()
        return explanation

    # ---------- feedback from the human ----------

    def feedback(self, decision_id: str, correct: bool, nanites: dict[str, Nanite], note: str = "") -> str:
        """The human says whether a decision's answer was right.

        Wrong: the nanite whose idea was chosen loses health and feels sad.
        Right: it feels happy (no health change; health only drops for mistakes).
        Either way Moiragen remembers, so he can learn whom to trust.
        """
        d = self.decisions.get(decision_id)
        if d is None:
            raise KeyError(f"No decision with id {decision_id}")
        chosen = next((nanites[s["nanite_id"]] for s in d["suggestions"] if s["nanite"] == d["chosen"]), None)
        extra = f" The human said: {note}" if note else ""

        if correct:
            if chosen:
                chosen.feel("happy", 0.2)
                chosen.remember("praised", f"The human said our answer to \"{d['question']}\" was right.{extra}")
            self.remember("feedback", f"The human said my answer to \"{d['question']}\" was right.{extra}",
                          decision_id=decision_id, correct=True)
            msg = "Thank you. I'll remember that."
        else:
            if chosen:
                chosen.hurt(WRONG_ANSWER_DAMAGE,
                            f"The human said my suggestion for \"{d['question']}\" was wrong.{extra}")
            self.remember("mistake", f"The human said my answer to \"{d['question']}\" was wrong. "
                                     f"I had trusted {d['chosen'] or 'myself'}.{extra}",
                          decision_id=decision_id, correct=False)
            msg = "I understand. I'll learn from it."

        d["feedback"] = "right" if correct else "wrong"
        self.save()
        for n in nanites.values():
            n.save()
        return msg


def parse_choice(text: str, suggestions: list[dict]) -> dict:
    """Read Moiragen's JSON reply safely.

    Small models sometimes return slightly broken JSON or a name that is a
    bit off ("nanite two", "Two"). We repair what we can, and if nothing
    works we fall back to the first suggestion so the being never crashes.
    """
    names = [s["nanite"] for s in suggestions]
    data = {}
    m = re.search(r"\{.*\}", text, re.DOTALL)  # find the {...} block (skips ```json fences)
    if m:
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            data = {}
    if not data:
        # Broken JSON (e.g. a curly ” closing a string). Pull out each field on its own:
        # "key": "value" where the value may end in " or ” and is followed by , or }.
        for key in ("chosen", "reason", "answer"):
            fm = re.search(rf'"{key}"\s*:\s*["“](.*?)["”]\s*(?:,\s*"|\}}|$)', text, re.DOTALL)
            if fm:
                data[key] = fm.group(1)

    raw = str(data.get("chosen", "")).strip().lower()
    chosen = next((n for n in names if n.lower() == raw), None)
    if chosen is None:  # try matching just the last word, e.g. "two"
        chosen = next((n for n in names if n.split()[-1].lower() in raw.split()), None)

    reason = str(data.get("reason", "")).strip()
    answer = str(data.get("answer", "")).strip()
    if chosen is None:
        chosen = names[0]
        reason = reason or "I could not decide clearly, so I went with the first idea."
    if not answer:
        answer = next(s["text"] for s in suggestions if s["nanite"] == chosen)
    return {"chosen": chosen, "reason": reason or "It seemed the most sensible.", "answer": answer}

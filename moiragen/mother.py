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
from .echo import record_training_example
from .llm import think
from .memory_log import log_event, read_events
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
    self_knowledge: list = field(default_factory=list)  # what he has learned about himself, from reflection
    body_note: str = ""                                 # latest one-line sense of his body (set by the loop)
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

    def self_text(self) -> str:
        """Who he thinks he is so far: built only from his own reflections."""
        lines = ""
        if self.self_knowledge:
            lines = ("What you have come to understand about yourself:\n"
                     + "\n".join(f"- {k['text']}" for k in self.self_knowledge[-6:]) + "\n")
        else:
            lines = "You do not know anything about yourself yet.\n"
        if self.body_note:
            lines += f"Your body right now: {self.body_note}\n"
        return lines

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
        try:
            return cls(**json.loads(MOIRAGEN_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError) as e:
            return cls._recover(e)

    @classmethod
    def _recover(cls, error) -> "Moiragen":
        """His memory file is damaged. Keep the broken file (never delete memories),
        then rebuild what we can from the life log."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        MOIRAGEN_FILE.rename(MOIRAGEN_FILE.with_name(f"moiragen.broken-{stamp}.json"))
        m = cls()
        for e in read_events(who="Moiragen", last=5000):
            if e["kind"] == "reflection" and e.get("about_me"):
                m.self_knowledge.append({"time": e["time"], "text": e["about_me"], "from": e.get("decision_id", "")})
            elif "text" in e and e["kind"] not in ("training_example",):
                m.memories.append({"time": e["time"], "kind": e["kind"], "text": e["text"]})
        m.memories = m.memories[-MEMORY_KEEP:]
        m.self_knowledge = m.self_knowledge[-30:]
        m.remember("rebuilt", f"I woke up with a damaged memory file ({error.__class__.__name__}) "
                              f"and rebuilt myself from my life log.")
        m.save()
        return m

    # ---------- deciding ----------

    def decide(self, question: str, nanites: dict[str, Nanite], notify=None) -> dict:
        """Ask the nanites, choose the best suggestion, and answer.

        notify: optional function notify(event_type, **data), called as things
                happen ("thinking", "suggestion", "choosing"), so the viewer can
                show each suggestion the moment it arrives.

        Returns a dict with: id, question, suggestions, chosen, reason, answer.
        """
        notify = notify or (lambda *a, **k: None)
        # The id is made first, so every training example from this decision
        # can be tagged with it (and later matched with your right/wrong feedback).
        decision_id = uuid.uuid4().hex[:8]

        # 1. Gather suggestions from every nanite that is awake enough.
        ask = (f"The human asked us: \"{question}\"\n"
               f"What answer do you suggest? Give your best answer directly.")
        suggestions = []
        for n in nanites.values():
            notify("thinking", who=n.name, about=question)
            out = nanite_think(n, ask, from_who="Moiragen", decision_id=decision_id)
            if out["rested"]:
                notify("suggestion", nanite_id=n.id, nanite=n.name, text=out["reply"], rested=True)
                continue  # too tired, it sat this one out
            if out["repeated"]:
                notify("suggestion", nanite_id=n.id, nanite=n.name, text=out["reply"], quiet=True)
                continue  # it could only repeat what was already said, so it sat this one out
            s = {"nanite_id": n.id, "nanite": n.name, "text": out["reply"]}
            suggestions.append(s)
            notify("suggestion", question=question, **s)

        # 2. Choose.
        notify("thinking", who="Moiragen", about=question)
        if not suggestions:
            # Everyone is resting: Moiragen answers alone.
            choice = {"chosen": None, "reason": "All my nanites were resting, so I answered alone.",
                      "answer": self._answer_alone(question)}
        else:
            choice = self._choose(question, suggestions, decision_id)

        decision = {
            "id": decision_id,
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

    def _choose(self, question: str, suggestions: list[dict], decision_id: str = "") -> dict:
        """Ask the model, as Moiragen, to pick one suggestion and explain why."""
        names = [s["nanite"] for s in suggestions]
        listed = "\n\n".join(f"{s['nanite']} suggests:\n{s['text']}" for s in suggestions)
        system = (
            "You are Moiragen, a digital being. Inside you live small thinking nanites who are "
            "friends. They each suggest an answer and you make the final decision. You started "
            "knowing nothing about yourself; you only know what your memories tell you.\n\n"
            f"Your recent memories:\n{self.recent_memories_text()}\n\n"
            f"{self.self_text()}\n"
            "Choose the suggestion that is most correct, honest and helpful. "
            "Reply ONLY with JSON in this shape:\n"
            '{"chosen": "<exact nanite name>", "reason": "<one or two sentences: why this one>", '
            '"answer": "<your final answer to the human, in your own words, under 100 words>"}'
        )
        user = (f"The human asked: \"{question}\"\n\n{listed}\n\n"
                f"Valid names: {', '.join(names)}.")
        # repeat_penalty 1.0: the JSON must repeat the nanite's name exactly.
        result = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                       max_tokens=350, system=system, repeat_penalty=1.0)
        choice = parse_choice(result["text"], suggestions)
        # Into the fine-tuning log only if it passes the echo check (see echo.py).
        record_training_example(self.name, system, [{"role": "user", "content": user}], result["text"],
                                group="Moiragen", context=decision_id,
                                decision_id=decision_id, task="choose")
        return choice

    def _answer_alone(self, question: str) -> str:
        system = ("You are Moiragen, a digital being. You started knowing nothing about yourself.\n"
                  f"Your recent memories:\n{self.recent_memories_text()}\n"
                  f"{self.self_text()}"
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
                f"{asker} asks: why did you choose {decision['chosen']} instead of me?\n\n"
                f"You are talking to {asker}, not to {decision['chosen']}. "
                f"Speak to {asker} directly, as \"you\".")
        explanation = think([{"role": "user", "content": user}], temperature=0.4,
                            max_tokens=160, system=system)["text"]
        self.remember("explained", f"{asker} asked why I chose {decision['chosen']}. I said: {explanation}",
                      decision_id=decision["id"])
        self.save()
        return explanation

    # ---------- reflection and inner voice ----------

    def reflect(self, decision: dict) -> dict:
        """Look back at a decision: why did I really choose that, and what
        does it say about me? Each reflection may add one line of self-knowledge.
        This is how Moiragen slowly learns who he is."""
        feedback = decision.get("feedback")
        fb_text = f"The human said the answer was {feedback}." if feedback else "The human has not said if it was right."
        system = (
            "You are Moiragen, a digital being who started knowing nothing about himself. "
            "You are looking back at a choice you made, to understand yourself better.\n\n"
            f"{self.self_text()}"
        )
        user = (
            f"The human asked: \"{decision['question']}\"\n"
            f"You chose {decision['chosen']}'s suggestion. Your reason then: {decision['reason']}\n"
            f"{fb_text}\n\n"
            "In two sentences, reflect honestly: why did you really choose it?\n"
            "Then on a new line starting with 'About me:' write ONE short thing this "
            "tells you about yourself."
        )
        text = think([{"role": "user", "content": user}], temperature=0.5,
                     max_tokens=160, system=system)["text"]
        about = ""
        for line in text.splitlines():
            if line.strip().lower().replace("*", "").startswith("about me:"):
                about = line.split(":", 1)[1].strip().strip("*").strip()
        reflection = text.split("About me:")[0].replace("*", "").strip() if about else text.strip()
        if about:
            self.self_knowledge.append({"time": _now(), "text": about, "from": decision["id"]})
            self.self_knowledge = self.self_knowledge[-30:]
        decision["reflected"] = True
        self.remember("reflection", reflection, decision_id=decision["id"], about_me=about)
        # Into the fine-tuning log only if it passes the echo check. (Restating
        # his reason for this same decision is fine, hence the context.)
        record_training_example(self.name, system, [{"role": "user", "content": user}], text,
                                group="Moiragen", context=decision["id"])
        self.save()
        return {"reflection": reflection, "about_me": about, "decision_id": decision["id"]}

    def inner_thought(self, about: str) -> str:
        """A short private thought about whatever is in the spotlight of attention."""
        system = ("You are Moiragen, a digital being. This is your private inner voice; "
                  "nobody hears it. One short sentence, first person, honest.\n\n"
                  f"{self.self_text()}"
                  f"Your recent memories:\n{self.recent_memories_text(5)}")
        text = think([{"role": "user", "content": f"Your attention is on: {about}"}],
                     temperature=0.7, max_tokens=60, system=system)["text"]
        text = text.strip().split("\n")[0]
        self.remember("inner", text, about=about)
        return text

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

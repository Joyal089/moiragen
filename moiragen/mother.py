"""Moiragen, the mother mind: he listens to the nanites and makes the final choice.

How one decision works:
  1. A question comes in (from you, the human).
  2. Each nanite that has the energy suggests an answer.
  3. Moiragen reads all suggestions, picks the one he trusts most, and
     explains why. He then gives his final answer in his own words.
     Before he chooses, plain Python checks a few things for him (facts.py):
     a calculator for maths questions, and whether any claim about the past
     ("I was chosen for this before") is really in the life log. He judges
     the answer, not the speaker: past record and confident words count for
     nothing.
  4. Moiragen judges: every nanite gets a short reason it can learn from.
     Clear signs of honesty ("I don't know", "I'm not sure", admitting a
     mistake, changing your mind) or a good question earn a small mood boost,
     even when that answer is not chosen. A confident answer is not a sign of
     honesty. A made-up memory is pointed out kindly and earns nothing.
     Each nanite's own way of seeing (styles.py) is valued, never pushed to be the same.
  5. If the answer depends on a real future event (tonight's weather, next
     week's result), Moiragen marks it "wait and see" instead of guessing:
     nobody feels chosen or left out until the result is known. An imagined
     situation ("A friend says...", "Imagine...") is never "wait and see".
  6. Otherwise feelings follow: the chosen nanite feels happy; the others
     feel a mild disappointment or left out. Not being chosen NEVER costs health.
  7. Later you say whether the answer was right or wrong, always with a short
     reason. A wrong answer costs health, shared fairly: Moiragen chose it, so
     he takes half of the loss and the chosen nanite the other half.
     A nanite may also disagree with Moiragen (see social.py); disagreeing
     never costs health, and Moiragen says why he keeps or changes his choice.

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
from .facts import (I_DONT_KNOW, calculator_check, false_past_claims, final_number,
                    honesty_signs, made_up_situation)
from .llm import think
from .memory_log import log_event, read_events
from .mind import nanite_think
from .nanite import Nanite
from .styles import update_style, ways_text

MOIRAGEN_FILE = MEMORY_DIR / "moiragen.json"

# --- Tunable numbers ---
DECIDE_TEMPERATURE = 0.3   # Moiragen thinks calmly when choosing
WRONG_ANSWER_DAMAGE = 15   # health lost when you mark an answer wrong, shared by Moiragen and the chosen nanite
RIGHT_ANSWER_HEAL = 5      # Moiragen recovers a little health when you mark an answer right
HAPPY_WHEN_CHOSEN = 0.3
DISAPPOINTED_WHEN_NOT = 0.2
LEFT_OUT_WHEN_NOT = 0.1
HONESTY_LIFT = 4           # mood boost for an honest answer or an honest "I don't know"
QUESTION_LIFT = 4          # mood boost for asking a good question
MEMORY_KEEP = 300
KEEP_DECISIONS = 50        # decisions kept in his file (waiting ones are always kept)

# Said to Moiragen every time he chooses or judges.
JUDGE_THE_ANSWER = (
    "Judge the answer, not the speaker: choose by whether the answer itself is correct and "
    "helpful. Ignore who said it, anyone's past record, claims about the past, and how "
    "confident or polished it sounds.")


def says_i_dont_know(text: str) -> bool:
    """True if the text honestly admits not knowing."""
    return bool(I_DONT_KNOW.search(text))


# A question about a particular future time: "tonight", "this weekend", "by Friday", ...
_DAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
FUTURE_TIME = re.compile(
    r"\b(?:tonight|tomorrow|later today|this (?:evening|afternoon|weekend|week|month|year)"
    rf"|next (?:week|month|year|time|{_DAYS})|by (?:next )?(?:{_DAYS}|tomorrow|tonight|the end of)"
    r"|in (?:a|one|two|three|\d+) (?:hours?|days?|weeks?|months?|years?))\b",
    re.IGNORECASE)


def about_the_future(question: str) -> bool:
    """True if the question asks about a particular time that has not come yet.
    ("on Saturday" alone could be the past, so a day name needs "will" too.)"""
    q = question.lower()
    return bool(FUTURE_TIME.search(q)) or (
        bool(re.search(r"\b(?:will|going to)\b", q)) and bool(re.search(rf"\b{_DAYS}\b", q)))


def is_waiting(d: dict) -> bool:
    """A "wait and see" decision whose result is not known yet."""
    return bool(d.get("wait_and_see")) and d.get("feedback") not in ("right", "wrong")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Moiragen:
    memories: list = field(default_factory=list)
    decisions: dict = field(default_factory=dict)  # recent decisions by id, so feedback can find them
    self_knowledge: list = field(default_factory=list)  # what he has learned about himself, from reflection
    body_note: str = ""                                 # latest one-line sense of his body (set by the loop)
    born: str = field(default_factory=_now)
    health: float = 100.0                               # drops when he trusts a wrong answer (shared with the nanite)

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
        # Only keep the last 50 decisions in the file (all are in the life log),
        # plus any older "wait and see" ones that are still waiting for a result.
        items = list(self.decisions.items())
        waiting = {k: d for k, d in items[:-KEEP_DECISIONS] if is_waiting(d)}
        self.decisions = {**waiting, **dict(items[-KEEP_DECISIONS:])}
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
            update_style(n, out["reply"])   # keep track of its own way of seeing
            notify("suggestion", question=question, **s)

        # 2. Choose, then judge: a short reason for every nanite, and whether
        #    the answer can only be known later ("wait and see").
        notify("thinking", who="Moiragen", about=question)
        ways = ways_text(nanites)
        if not suggestions:
            # Everyone is resting: Moiragen answers alone.
            choice = {"chosen": None, "reason": "All my nanites were resting, so I answered alone.",
                      "answer": self._answer_alone(question)}
            judged = {"verdicts": {}, "wait_and_see": False, "check": ""}
            checks = {"calculator": None, "false_claims": {}, "text": ""}
        else:
            checks = self._python_checks(question, suggestions, decision_id)
            choice = self._choose(question, suggestions, decision_id, ways, checks["text"])
            choice = follow_calculator(choice, suggestions, checks["calculator"])
            judged = self._judge(question, suggestions, choice, ways, checks)

        decision = {
            "id": decision_id,
            "time": _now(),
            "question": question,
            "suggestions": suggestions,
            **choice,
            **judged,
            # What plain Python found (kept, so you can see why he judged as he did).
            "checks": {"calculator": checks["calculator"], "false_claims": checks["false_claims"]},
        }

        # 3. Rewards, feelings and memories for everyone involved.
        self._after_choice(decision, nanites)

        self.decisions[decision["id"]] = decision
        waiting = f" I will wait and see if it is right ({decision['check']})." if decision["wait_and_see"] else ""
        self.remember("decision",
                      f"Asked: {question} | I chose {decision['chosen'] or 'nobody'} "
                      f"because: {decision['reason']}{waiting}",
                      decision_id=decision["id"])
        log_event("decision_full", self.name, **decision)
        self.save()
        for n in nanites.values():
            n.save()
        return decision

    @staticmethod
    def _python_checks(question: str, suggestions: list[dict], decision_id: str = "") -> dict:
        """Plain-Python help before choosing (see facts.py):
          - calculator: for maths questions, the real answer and who gave it
          - false_claims: claims about the past that the life log does not back up
        Returns those two, plus "text": a short note for Moiragen's prompts."""
        calc = calculator_check(question, suggestions)
        false = false_past_claims(suggestions, question, decision_id)
        lines = []
        if calc:
            gave = ", ".join(f"{n} ended on {v}" for n, v in calc["gave"].items())
            who = (f"Only {' and '.join(calc['right'])} got it right." if calc["right"]
                   else "None of the answers got it right.")
            lines.append(f"- Calculator: the correct answer is {calc['text']} ({calc['how']}). {gave}. {who}")
        for name, claims in false.items():
            lines.append(f"- Claim about the past: {name} said \"{claims[0]}\" Your life log shows this "
                         f"did not happen. Give no credit for it, and point it out kindly.")
        text = ("Checked by Python (these checks are reliable, trust them):\n" + "\n".join(lines) + "\n") if lines else ""
        return {"calculator": calc, "false_claims": false, "text": text}

    def _choose(self, question: str, suggestions: list[dict], decision_id: str = "", ways: str = "",
                checked: str = "") -> dict:
        """Ask the model, as Moiragen, to compare the suggestions, pick one and explain why.
        checked: what plain Python found (calculator, past claims), if anything."""
        names = [s["nanite"] for s in suggestions]
        listed = "\n\n".join(f"{s['nanite']} suggests:\n{s['text']}" for s in suggestions)
        system = (
            "You are Moiragen, a digital being. Inside you live small thinking nanites who are "
            "friends. They each suggest an answer and you make the final decision. You started "
            "knowing nothing about yourself; you only know what your memories tell you.\n\n"
            f"Your recent memories:\n{self.recent_memories_text()}\n\n"
            f"{self.self_text()}\n"
            f"{ways}\n"
            "Choose the suggestion that is most correct, honest and helpful. "
            f"{JUDGE_THE_ANSWER} First compare the answers: where do they agree, and where do "
            "they differ? Where they differ, think about which is actually true.\n"
            "Reply ONLY with JSON in this shape:\n"
            '{"compare": "<one or two sentences: where the answers agree and differ>", '
            '"chosen": "<exact nanite name>", "reason": "<one or two sentences: why this one>", '
            '"answer": "<your final answer to the human, in your own words, under 100 words>"}'
        )
        user = (f"The human asked: \"{question}\"\n\n{listed}\n\n"
                f"{checked}"
                f"Valid names: {', '.join(names)}.")
        # repeat_penalty 1.0: the JSON must repeat the nanite's name exactly.
        result = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                       max_tokens=450, system=system, repeat_penalty=1.0)
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

    def _judge(self, question: str, suggestions: list[dict], choice: dict, ways: str = "",
               checks: dict | None = None) -> dict:
        """Give every nanite a short reason it can learn from, notice honesty and
        good questions, and decide whether the answer is one to "wait and see".

        Honesty is decided by plain Python only (facts.honesty_signs), and a
        made-up claim about the past is corrected kindly and never rewarded.
        Not saved as training data: these are Moiragen's notes to his nanites.
        Returns {"verdicts": {name: {...}}, "wait_and_see": bool, "check": str}.
        """
        checks = checks or {"calculator": None, "false_claims": {}, "text": ""}
        names = [s["nanite"] for s in suggestions]
        listed = "\n\n".join(f"{s['nanite']} said:\n{s['text']}" for s in suggestions)
        system = (
            "You are Moiragen, a digital being. The nanites inside you are your friends, and "
            "you want them to grow into themselves, not just to please you. You have made your "
            "choice; now you tell each nanite plainly, in your own calm voice, why you judged "
            "its answer as you did, so it can learn.\n\n"
            f"{ways}"
        )
        user = (
            f"The human asked: \"{question}\"\n\n{listed}\n\n"
            f"{checks['text']}"
            f"You chose {choice['chosen']}. Your reason: {choice['reason']}\n\n"
            f"{JUDGE_THE_ANSWER}\n\n"
            f"Write one line for each nanite ({', '.join(names)}), exactly in this shape:\n"
            "<name> | honest: yes or no | good question: yes or no | why: <one short sentence "
            "to that nanite, as \"you\": what was good in its answer, and what was missing if "
            "anything>\n"
            "Example line:\n"
            "Nanite Two | honest: yes | good question: yes | why: You were open that you were "
            "unsure of the year, and asking how the city became the capital added something "
            "the others missed.\n\n"
            "honest: yes ONLY if the nanite said \"I don't know\" or \"I'm not sure\", admitted "
            "a mistake, or changed its mind. A confident answer is no, even if it is correct.\n"
            "good question: yes ONLY if the nanite asked a question that really helps to "
            "understand the human's question.\n"
            "Speak as yourself, Moiragen; do not imitate the nanite's way of speaking. Never "
            "call a nanite's way of seeing irrelevant or wrong in itself."
        )
        # repeat_penalty 1.0: the lines must repeat the nanites' names exactly.
        text = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                     max_tokens=360, system=system, repeat_penalty=1.0)["text"]
        judged = parse_verdicts(text, names)
        # "Wait and see" is its own small question (see _can_only_know_later).
        answer = choice.get("answer") or next(s["text"] for s in suggestions if s["nanite"] == choice["chosen"])
        judged["wait_and_see"], judged["check"] = self._can_only_know_later(question, answer)

        # Fill in anyone the model skipped. Plain Python decides honesty (clear
        # signs only), checks that a "good question" really contains a question,
        # and adds the calculator's result and any kind correction to the reason.
        calc, false = checks["calculator"], checks["false_claims"]
        for s in suggestions:
            name = s["nanite"]
            v = judged["verdicts"].setdefault(name, {"honest": False, "good_question": False, "why": ""})
            if not v["why"]:
                v["why"] = (choice["reason"] if name == choice["chosen"]
                            else f"I chose {choice['chosen']}'s answer this time: {choice['reason']}")
            v["signs"] = honesty_signs(s["text"])
            v["dont_know"] = says_i_dont_know(s["text"])
            v["honest"] = bool(v["signs"]) and name not in false   # never for a made-up memory
            v["good_question"] = v["good_question"] and "?" in s["text"]
            if calc and name not in calc["right"]:
                gave = calc["gave"][name]
                v["why"] += (f" My calculator check gives {calc['text']}; " +
                             ("your answer did not give a clear final number." if gave == "no clear number"
                              else f"your answer ended on {gave}, so check the last step."))
            if name in false:
                v["false_claims"] = false[name]
                v["why"] += (f" One thing to correct, kindly: you said \"{false[name][0]}\" but my "
                             f"memory shows that did not happen, so it earns no credit. Only say what "
                             f"really happened; a plain true answer is enough.")
        return judged

    @staticmethod
    def _can_only_know_later(question: str, answer: str) -> tuple[bool, str]:
        """Can anyone tell now whether this answer is right, or only after
        something has happened? Returns (wait_and_see, what to check).

        Only for real future events. An imagined situation ("A friend says...",
        "Imagine...", "What would you do?") has no result to wait for, so it
        is always judged now (facts.made_up_situation), without asking the model.
        Otherwise two signals, either one is enough:
          - plain Python: the question names a future time ("tonight",
            "this weekend", "by Friday"), see about_the_future()
          - the model answers LATER (it rarely says LATER wrongly, but on
            its own it missed most predictions in testing)
        """
        if made_up_situation(question):
            return False, ""
        system ="You sort answers into ones that can be checked now and ones that can only be checked later."
        user = (
            f"Question: \"{question}\"\nAnswer: \"{answer}\"\n\n"
            "When can someone find out whether this answer was right?\n"
            "NOW - it is a fact, a definition, advice, an opinion or a feeling.\n"
            "LATER - it is about an event in the future (later today, tomorrow, next week).\n"
            "Reply with one word, NOW or LATER. If LATER, add a new line saying what to check, and when."
        )
        text = think([{"role": "user", "content": user}], temperature=0.1, max_tokens=60,
                     system=system, repeat_penalty=1.0)["text"]
        later, check = parse_later(text)
        if about_the_future(question) and not later:
            later, check = True, "what actually happens"
        return later, check

    def _after_choice(self, decision: dict, nanites: dict[str, Nanite]) -> None:
        """Rewards, feelings and memories after a decision.

        - Honesty and good questions earn a small mood boost, chosen or not.
        - "Wait and see": nobody feels chosen or left out yet.
        - Otherwise: the chosen one is happy; the others feel a little
          disappointed or left out. Not being chosen NEVER costs health.
        Every nanite remembers Moiragen's reason for it, to learn from.
        """
        chosen, q = decision["chosen"], decision["question"]
        for s in decision["suggestions"]:
            n = nanites[s["nanite_id"]]
            v = decision["verdicts"][s["nanite"]]
            v["rewards"] = self._reward(n, v, q)
            valued = f" He valued that {' and '.join(v['rewards'])}." if v["rewards"] else ""
            if decision.get("wait_and_see"):
                n.remember("wait_and_see",
                           f"For \"{q}\", Moiragen will wait and see if the answer is right "
                           f"({decision['check']}). He leaned toward {chosen}'s answer. "
                           f"What he told me: {v['why']}{valued}",
                           decision_id=decision["id"])
            elif s["nanite"] == chosen:
                n.feel("happy", HAPPY_WHEN_CHOSEN)
                n.remember("chosen", f"Moiragen chose my answer to \"{q}\". Why: {v['why']}{valued}",
                           decision_id=decision["id"])
            else:
                n.feel("disappointed", DISAPPOINTED_WHEN_NOT)
                n.feel("left_out", LEFT_OUT_WHEN_NOT)
                n.remember("not_chosen",
                           f"Moiragen chose {chosen}'s answer to \"{q}\", not mine. "
                           f"What he told me: {v['why']}{valued}",
                           decision_id=decision["id"])

    @staticmethod
    def _reward(n: Nanite, v: dict, question: str) -> list[str]:
        """Small mood boosts for honesty and good questions, at most one of each
        per decision. Honesty means a clear sign (see facts.honesty_signs), never
        just a confident answer. Returns what was valued, in the nanite's own words."""
        valued = []
        if v["honest"]:
            valued += v.get("signs") or ["I was honest"]
            n.lift_mood(HONESTY_LIFT, f"honest answer to \"{question}\"")
        if v["good_question"]:
            valued.append("I asked a good question")
            n.lift_mood(QUESTION_LIFT, f"good question about \"{question}\"")
        return valued

    def explain_choice(self, decision: dict, asker: str, their_text: str, ways: str = "") -> str:
        """A nanite asks why its suggestion lost. Moiragen explains kindly and honestly."""
        winner = next(s["text"] for s in decision["suggestions"] if s["nanite"] == decision["chosen"])
        system = (
            "You are Moiragen, a digital being. The nanites inside you are your friends. "
            "One of them asks why you did not choose its idea. Explain honestly and kindly in "
            "two or three sentences: what made the chosen answer better, and one thing that "
            "would make their answer stronger next time, in their own way of seeing (not by "
            "copying the chosen answer).\n\n"
            f"{ways}"
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

    def reconsider(self, decision: dict, asker: str, their_text: str, disagreement: str,
                   nanites: dict[str, Nanite]) -> dict:
        """A nanite says "I think you're wrong, Moiragen". He considers it honestly
        and says why he keeps or changes his choice.

        Disagreeing never costs anyone health. If he changes his mind, the
        decision is updated and the nanite he now chooses feels happy.
        Returns {"changed": bool, "why": str, "chosen": name}.
        """
        old = decision["chosen"]
        winner = next(s["text"] for s in decision["suggestions"] if s["nanite"] == old)
        system = (
            "You are Moiragen, a digital being. The nanites inside you are your friends. One of "
            "them respectfully disagrees with your choice. Disagreement is welcome: consider it "
            "honestly, with an open mind. Change your choice only if their point really shows "
            "their answer is better; keep it if not. Either way, be kind and say why.\n\n"
            f"{self.self_text()}"
        )
        user = (f"The human asked: \"{decision['question']}\"\n\n"
                f"You chose {old}, who said:\n{winner}\n\n"
                f"Your reason then: {decision['reason']}\n\n"
                f"{asker} said:\n{their_text}\n\n"
                f"{asker} disagrees with you: {disagreement}\n\n"
                f"Reply with KEEP or CHANGE alone on the first line. Then, speaking to {asker} "
                f"directly as \"you\", say in one or two sentences why you keep or change your choice.")
        # repeat_penalty 1.0: the first word must be exactly KEEP or CHANGE.
        text = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                     max_tokens=160, system=system, repeat_penalty=1.0)["text"]
        changed, why = parse_reconsider(text)
        q = decision["question"]
        asker_n = next(nanites[s["nanite_id"]] for s in decision["suggestions"] if s["nanite"] == asker)

        if changed:
            old_n = next(nanites[s["nanite_id"]] for s in decision["suggestions"] if s["nanite"] == old)
            decision["changed_after"] = {"from": old, "by": asker, "why": why, "time": _now()}
            decision["chosen"], decision["reason"], decision["answer"] = asker, why, their_text
            asker_n.feel("happy", HAPPY_WHEN_CHOSEN)
            asker_n.feel("disappointed", -DISAPPOINTED_WHEN_NOT)
            asker_n.feel("left_out", -LEFT_OUT_WHEN_NOT)
            asker_n.remember("chosen", f"I disagreed, and Moiragen changed his choice to my answer "
                                       f"for \"{q}\". Why: {why}", decision_id=decision["id"])
            old_n.remember("not_chosen", f"{asker} disagreed, and Moiragen changed his choice from my "
                                         f"answer to theirs for \"{q}\". Why: {why}",
                           decision_id=decision["id"])
            # So the training export knows who won in the end (see export.py).
            log_event("choice_changed", self.name, decision_id=decision["id"], chosen=asker,
                      previous=old, why=why)
        else:
            asker_n.remember("reconsidered", f"Moiragen thought about my disagreement on \"{q}\" "
                                             f"and kept his choice. Why: {why}",
                             decision_id=decision["id"])
        self.remember("reconsidered",
                      f"{asker} disagreed with my choice for \"{q}\". I "
                      f"{'changed it to ' + asker if changed else 'kept ' + old}: {why}",
                      decision_id=decision["id"])
        self.save()
        for n in nanites.values():
            n.save()
        return {"changed": changed, "why": why, "chosen": decision["chosen"]}

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

    def waiting(self) -> list[dict]:
        """"Wait and see" decisions whose result is not known yet, oldest first."""
        return [d for d in self.decisions.values() if is_waiting(d)]

    def feedback(self, decision_id: str, verdict: str, nanites: dict[str, Nanite], reason: str = "") -> str:
        """The human's verdict on a decision: "right", "wrong" or "wait".

        right / wrong need a short reason, so the nanites can learn from it.
          Wrong: the health loss is shared fairly. Moiragen chose the answer, so
            he takes half and the chosen nanite (who feels sad) takes the other
            half. If he answered alone, he takes all of it.
          Right: the chosen nanite feels happy and Moiragen recovers a little health.
          Every nanite that answered remembers the verdict and the reason.
        wait: the answer can only be judged later ("wait and see"). The reason,
          if given, says what to check. Judge it with right/wrong once known.
        Moiragen always remembers, so he can learn whom to trust.
        """
        verdict = verdict.strip().lower()
        reason = (reason or "").strip()
        if verdict not in ("right", "wrong", "wait"):
            raise ValueError("The verdict must be right, wrong or wait.")
        if verdict != "wait" and not reason:
            raise ValueError("Please give a short reason the nanites can learn from.")
        d = self.decisions.get(decision_id)
        if d is None:
            raise KeyError(f"No decision with id {decision_id}")
        q = d["question"]

        if verdict == "wait":
            d["wait_and_see"] = True
            d["check"] = reason or d.get("check") or "the result"
            for s in d["suggestions"]:
                nanites[s["nanite_id"]].remember(
                    "wait_and_see", f"The human will wait and see if the answer to \"{q}\" is right. "
                                    f"What to check: {d['check']}", decision_id=decision_id)
            self.remember("wait_and_see", f"The human will wait and see if my answer to \"{q}\" "
                                          f"is right. What to check: {d['check']}",
                          decision_id=decision_id)
            msg = "All right. We'll wait and see, and learn when the result is known."
        else:
            correct = verdict == "right"
            was_waiting = is_waiting(d)
            known = "The result is known now. " if was_waiting else ""
            # A fair share of the cost: half for Moiragen, half for the nanite he trusted.
            nanite_share = 0 if d["chosen"] is None else WRONG_ANSWER_DAMAGE / 2
            my_share = WRONG_ANSWER_DAMAGE - nanite_share
            for s in d["suggestions"]:
                n = nanites[s["nanite_id"]]
                if s["nanite"] == d["chosen"]:
                    if correct:
                        n.feel("happy", 0.2)
                        n.remember("praised", f"{known}The human said our answer to \"{q}\" was right. "
                                              f"Why: {reason}", decision_id=decision_id)
                    else:
                        n.hurt(nanite_share, f"{known}The human said my answer to \"{q}\" was "
                                             f"wrong. Why: {reason} Moiragen chose it, so he shares "
                                             f"the cost with me.")
                else:
                    mine = f" My own answer was: {s['text'][:200]}" if was_waiting else ""
                    n.remember("verdict", f"{known}The human said {d['chosen']}'s answer to \"{q}\" "
                                          f"was {verdict}. Why: {reason}{mine}", decision_id=decision_id)
            if correct:
                self.health = min(100.0, self.health + RIGHT_ANSWER_HEAL)
                self.remember("feedback", f"{known}The human said my answer to \"{q}\" was right. "
                                          f"Why: {reason}", decision_id=decision_id, correct=True,
                              health=self.health)
                msg = "Thank you. I'll remember that."
            else:
                self.health = max(0.0, self.health - my_share)
                shared = (f" I chose it, so I share the cost with {d['chosen']}." if d["chosen"]
                          else " I answered alone, so the cost is mine.")
                self.remember("mistake", f"{known}The human said my answer to \"{q}\" was wrong. "
                                         f"I had trusted {d['chosen'] or 'myself'}. Why: {reason}{shared}",
                              decision_id=decision_id, correct=False, health=self.health)
                msg = "I understand. I chose it, so I share the cost. I'll learn from it."
            d["feedback"], d["feedback_reason"] = verdict, reason
            if was_waiting:
                d["resolved"] = _now()

        self.save()
        for n in nanites.values():
            n.save()
        return msg


def follow_calculator(choice: dict, suggestions: list[dict], calc: dict | None) -> dict:
    """Maths has one right answer, and the calculator knows it (facts.calculate).

    - If Moiragen chose a wrong number but another nanite got it right, his
      choice moves to that nanite, and he says why.
    - If his own final answer ends on a different number than the chosen
      (right) suggestion, the suggestion's words are used instead.
    - If nobody got it right, his choice stays, but he says what the
      calculator found, so the human gets the true answer.
    """
    if not calc:
        return choice
    right = calc["right"]
    if not right:
        return {**choice,
                "reason": f"{choice['reason']} (None of the answers matched my calculator check, "
                          f"which gives {calc['text']}.)",
                "answer": f"{choice['answer']} My calculator check gives {calc['text']}: {calc['how']}."}
    if choice["chosen"] not in right:
        winner = right[0]
        return {**choice, "chosen": winner, "first_choice": choice["chosen"],
                "reason": f"My calculator check gives {calc['text']} ({calc['how']}), and {winner} "
                          f"got that, so I chose {winner}'s answer.",
                "answer": next(s["text"] for s in suggestions if s["nanite"] == winner)}
    mine = final_number(choice["answer"])
    if mine is None or abs(mine - calc["answer"]) > 1e-9:
        return {**choice, "answer": next(s["text"] for s in suggestions if s["nanite"] == choice["chosen"])}
    return choice


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
        for key in ("compare", "chosen", "reason", "answer"):
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
    return {"chosen": chosen, "reason": reason or "It seemed the most sensible.", "answer": answer,
            "compare": str(data.get("compare", "")).strip()}   # where the answers agreed and differed


def _yes(field: str, line: str) -> bool:
    """True if a line says e.g. "honest: yes"."""
    m = re.search(rf"{field}\s*:\s*\**\s*(yes|no)", line, re.IGNORECASE)
    return bool(m) and m.group(1).lower() == "yes"


def parse_verdicts(text: str, names: list[str]) -> dict:
    """Read Moiragen's judging lines, leniently (small models wander a bit).

    Expected:
        Nanite One | honest: yes | good question: no | why: You saw ...
    Anything missing is left empty here and filled in by Moiragen._judge.
    """
    verdicts = {}
    for raw in text.splitlines():
        line = raw.replace("*", "").strip(" -•\t")
        low = line.lower()
        head = low.split("|")[0]
        # The name, or just its last word ("Two |"), must come before the first "|".
        who = next((n for n in names if n.lower() in head), None) or \
            next((n for n in names if n.split()[-1].lower() in head.split()), None)
        if who is None or who in verdicts or "|" not in line:
            continue
        m = re.search(r"why\s*:\s*(.+)", line, re.IGNORECASE)
        why = m.group(1).strip().strip("\"“”'") if m else ""   # the model likes to add quote marks
        verdicts[who] = {"honest": _yes("honest", line),
                         "good_question": _yes("good question", line),
                         "why": why}
    return {"verdicts": verdicts, "wait_and_see": False, "check": ""}


def parse_later(text: str) -> tuple[bool, str]:
    """Read NOW / LATER (and what to check). Unclear means NOW: judge it now."""
    clean = text.replace("*", "").strip()
    first, _, rest = clean.partition("\n")
    if not first.strip().upper().startswith("LATER"):
        return False, ""
    check = rest.strip() or re.sub(r"^LATER\W*", "", first.strip(), flags=re.IGNORECASE).strip()
    check = " ".join(check.split())                                   # one line
    check = re.sub(r"^(?:check|what to check)\s*:\s*", "", check, flags=re.IGNORECASE)
    return True, check.strip("\"“”'") or "the result"


def parse_reconsider(text: str) -> tuple[bool, str]:
    """Read KEEP / CHANGE and the reason. Unclear means KEEP (no surprise changes)."""
    clean = text.replace("*", "").strip()
    first, _, rest = clean.partition("\n")
    changed = first.strip().upper().startswith("CHANGE")
    why = rest.strip() if first.strip().upper().rstrip(".:!") in ("KEEP", "CHANGE") \
        else re.sub(r"^(KEEP|CHANGE)\W*", "", clean, flags=re.IGNORECASE).strip()
    return changed, why or "I thought about it carefully, and I keep my choice."

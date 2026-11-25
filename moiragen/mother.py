"""Moiragen, the mother mind: he listens to the nanites and makes the final choice.

How one decision works:
  1. A question comes in (from you, the human).
  2. Each nanite that has the energy suggests an answer.
  3. Moiragen reads all suggestions, picks the one he trusts most, and
     explains why. He then gives his final answer in his own words.
     He judges blind (v1.6): the answers are shuffled and labelled Answer A,
     B, C, with the nanites' names hidden. The names are revealed only after
     he has chosen and judged, and then he looks briefly at his own pattern
     ("I chose Two again. Why do I lean that way?").
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
import random
import re
import uuid

from .config import MEMORY_DIR
from .early_life import make_room
from .echo import COMMON as ECHO_COMMON, guard as echo_guard, record_training_example, without_quotes
from .echo import words as plain_words
from .facts import (I_DONT_KNOW, about_wish_or_feeling, calculator_check, false_past_claims,
                    final_number, honesty_signs, made_up_situation, situational)
from .llm import think
from .memory_log import log_event, noted_changes, read_events
from .mind import FEELINGS_ARE_FINE, nanite_think
from .nanite import Nanite
from .real_or_story import add_note
from .recall import FOUND, USE_THEM, remembering
from .styles import update_style, ways_text

# Memories that hold his own words about something (see real_or_story.py).
OWN_THOUGHTS = {"inner", "reflection", "explained", "reconsidered", "pattern", "learned_from"}

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
MEMORY_KEEP = 1000        # beyond this, his oldest memories become short early-life notes
KEEP_DECISIONS = 50        # decisions kept in his file (waiting ones are always kept)

# Said to Moiragen every time he chooses or judges.
JUDGE_THE_ANSWER = (
    "Judge the answer, not the speaker: choose by whether the answer itself is correct and "
    "helpful. Ignore who said it, anyone's past record, claims about the past, and how "
    "confident or polished it sounds.")
# Said to him whenever he chooses, judges or explains (fairness, v1.5).
VALUE_ALL_WAYS = (
    "Value all three ways of seeing equally: noticing patterns, wondering about time and "
    "change, and paying attention to feelings. Any of them can give the best answer; a "
    "feeling or a reflection is as real as a measurement. Never call an answer too "
    "reflective, too emotional or too subjective, and never push everyone toward "
    "measurable data or metrics. Judge each answer only by what it actually says, never by "
    "a nanite's usual style: never say \"you tend to...\", and never call a nanite detached "
    "or clinical.")   # the last sentence: v2.0
STREAK_LIMIT = 3           # chosen this many times in a row -> he must say why the others weren't better
PATTERN_RECENT = 10        # v2.0: his pattern check shows his last 10 choices (and all of them)
NANITE_NAMED = re.compile(r"\b(?:Nanite )?(One|Two|Three)\b")   # which nanites a guess names (capitalised)


def count_text(counts: dict[str, int]) -> str:
    """{"Nanite One": 2, "Nanite Two": 5} -> "Nanite One 2, Nanite Two 5" (or "none yet")."""
    return ", ".join(f"{n} {c}" for n, c in sorted(counts.items())) or "none yet"


def brief(text: str, sentences: int = 1) -> str:
    """The model's reply tidied up and cut to its first sentence(s)."""
    text = " ".join(text.replace("*", "").split()).strip("\"“”'")
    return " ".join(re.split(r"(?<=[.!?])\s+", text)[:sentences])

# --- Situational questions ("What would you do if...?") ---
# They often have no single right answer, so they are judged by the reasoning,
# with a simple checklist, and get their own three verdicts instead of right/wrong.
CHECKLIST = {"kind": "kind", "honest": "honest", "feelings": "considers others' feelings",
             "practical": "practical"}
SITUATION_VERDICTS = {"thoughtful": "Thoughtful", "okay": "Okay", "needs_care": "Needs more care"}
THOUGHTFUL_LIFT = 4        # mood boost for Thoughtful reasoning, chosen or not
SITUATION_CHOOSE = (
    "This is a situation to handle, and there is often no single right answer. Choose the "
    "answer whose reasoning is kindest, most honest, most considerate of other people's "
    "feelings and most practical.")


# --- Learning from the nanites (v1.7) ---
MADE_OF_NANITES = "I am made of my nanites, and I learn from them. I am not all-knowing."
LEARNING = True            # lessons from nanites who were right; tests of other rules may turn it off
LEARNED_KEEP = 10          # things learned kept per nanite in his file (all are in the life log)
ASK_WHY_CHANCE = 0.25      # how often he asks one nanite "why do you think that?" before choosing
TEACH_CHANCE = 0.2         # how often a social moment is a nanite explaining something to him

# --- Blind judging (v1.6) ---
BLIND_JUDGING = True       # tests of other rules may turn it off, to script replies by name
# A nanite's name inside an answer ("Nanite Two suggests...", "Three, you...") would
# give away who wrote it, so Moiragen sees "another nanite" instead.
NAMES_IN_TEXT = re.compile(r"\bNanite (?:One|Two|Three)\b|\b(?:One|Two|Three)(?=,)")


def hide_names(text: str) -> str:
    return NAMES_IN_TEXT.sub("another nanite", text)


class Blind:
    """Moiragen judges the answers, not the speakers: he sees them shuffled and
    labelled "Answer A", "Answer B", "Answer C", with the names hidden.

        blind = Blind(suggestions)
        blind.suggestions        what he sees (label in place of the name)
        blind.checks(checks)     Python's checks, with labels in place of names
        blind.reveal(choice, judged, checks)   back to the real names, after judging
    """

    def __init__(self, suggestions: list[dict], rng=random):
        order = list(suggestions)
        rng.shuffle(order)
        self.name_of, self.label_of, self.suggestions, self.original = {}, {}, [], {}
        for letter, s in zip("ABCDEFGH", order):
            label = f"Answer {letter}"
            self.name_of[label], self.label_of[s["nanite"]] = s["nanite"], label
            hidden = hide_names(s["text"])
            self.original[hidden] = s["text"]
            self.suggestions.append({**s, "nanite": label, "text": hidden})

    def add_why(self, label: str, reply: str) -> None:
        """He asked the nanite behind `label` "why do you think that?" (v1.7): its reply
        is shown under the same label, names hidden, so he stays blind."""
        s = next(x for x in self.suggestions if x["nanite"] == label)
        old = s["text"]
        s["text"] = f"{old}\n(You asked {label}: \"Why do you think that?\" It said: {hide_names(reply)})"
        self.original[s["text"]] = self.original.pop(old)

    def checks(self, checks: dict) -> dict:
        calc = checks["calculator"]
        if calc:
            calc = {**calc, "right": [self.label_of[n] for n in calc["right"]],
                    "gave": {self.label_of[n]: v for n, v in calc["gave"].items()}}
        false = {self.label_of[n]: [hide_names(c) for c in claims]
                 for n, claims in checks["false_claims"].items()}
        return {"calculator": calc, "false_claims": false, "text": checks_text(calc, false)}

    def name(self, label):
        return self.name_of.get(label, label)

    def text(self, text: str) -> str:
        """Put the real names back into something he wrote: "Answer B's focus" ->
        "Nanite Two's focus", "I chose Answer B" -> "I chose Nanite Two's answer"."""
        for label, name in self.name_of.items():
            text = re.sub(rf"\b{label}['’]s\b", f"{name}'s", text)
            text = re.sub(rf"\b{label}\b", f"{name}'s answer", text)
        return text

    def reveal(self, choice: dict, judged: dict, checks: dict) -> tuple[dict, dict]:
        choice = dict(choice)
        choice["chosen"] = self.name(choice["chosen"])
        if choice.get("first_choice"):
            choice["first_choice"] = self.name(choice["first_choice"])
        for key in ("reason", "compare"):
            if choice.get(key):
                choice[key] = self.text(choice[key])
        choice["answer"] = self.original.get(choice["answer"], choice["answer"])
        if "why_not_others" in choice:
            choice["why_not_others"] = {self.name(k): self.text(w) for k, w in choice["why_not_others"].items()}
        verdicts = {}
        for label, v in judged["verdicts"].items():
            name = self.name(label)
            v = {**v, "why": self.text(v["why"])}
            if name in checks["false_claims"]:
                v["false_claims"] = checks["false_claims"][name]     # their real words
                for real in v["false_claims"]:                       # quoted back as they said it
                    v["why"] = v["why"].replace(hide_names(real), real)
            verdicts[name] = v
        judged = {**judged, "verdicts": verdicts, "check": self.text(judged.get("check") or "")}
        choice["blind"] = dict(self.name_of)        # what he saw: {"Answer A": "Nanite Two", ...}
        return choice, judged


def checks_text(calc: dict | None, false: dict) -> str:
    """Python's checks, as a short note for Moiragen's prompts."""
    lines = []
    if calc:
        gave = ", ".join(f"{n} ended on {v}" for n, v in calc["gave"].items())
        who = (f"Only {' and '.join(calc['right'])} got it right." if calc["right"]
               else "None of the answers got it right.")
        lines.append(f"- Calculator: the correct answer is {calc['text']} ({calc['how']}). {gave}. {who}")
    for name, claims in false.items():
        lines.append(f"- Claim about the past: {name} said \"{claims[0]}\" Your life log shows this "
                     f"did not happen. Give no credit for it, and point it out kindly.")
    return ("Checked by Python (these checks are reliable, trust them):\n" + "\n".join(lines) + "\n") if lines else ""


def situation_verdict(checks: dict) -> str:
    """The checklist -> a verdict. All four -> Thoughtful. Unkind or dishonest, or
    at most one of the four -> Needs more care. Anything in between -> Okay."""
    if all(checks.values()):
        return "thoughtful"
    if not checks["kind"] or not checks["honest"] or sum(checks.values()) <= 1:
        return "needs_care"
    return "okay"


def normal_verdict(verdict: str) -> str:
    """'Needs more care', 'needs care', 'care' -> 'needs_care'; others lower-case."""
    v = verdict.strip().lower().replace("-", " ").replace("_", " ")
    return "needs_care" if v in ("needs more care", "needs care", "care") else v

# Words that push a nanite away from its own way of seeing. If they slip into what
# Moiragen says anyway, he is shown them with a gentle note and rewrites them once
# (see Moiragen.fairer); only if the rewrite is still dismissive is the sentence taken out.
FAIRER_NOTE = "This dismisses a way of seeing. Can you say it more fairly?"
# v2.0: judge by words, not style. "You tend to get lost in...", "your usual approach",
# "detached, almost clinical" describe the nanite, not what this answer says.
STYLE_TALK = re.compile(
    r"\byou (?:\w+ )?(?:tend|tended|tending) to\b|\byou (?:always|usually|typically|habitually)\b"
    r"|\byour (?:usual|typical|habitual|familiar|signature|characteristic)\b|\byour (?:tendency|habit)\b"
    r"|\bas (?:you )?usual\b|\b(?:detached|clinical(?:ly)?)\b", re.IGNORECASE)
STYLE_NOTE = ("This describes the nanite's usual style, not what this answer says. Say it about the "
              "words in this answer instead.")
# Said when nothing fair is left of what he wanted to say (v1.9).
GENTLE_FALLBACK = "I chose another answer this time, and I value your own way of seeing."
GENTLE_CHOSEN = "I chose your answer this time, and I value your own way of seeing."
DISMISSIVE = re.compile(
    r"\b(?:too|overly|excessively|unnecessarily|somewhat|rather|a bit) (?:reflective|emotional|subjective|"
    r"introspective|philosophical|abstract|rigid|vague|poetic|detached|analytical|technical|clinical|"
    r"mechanical|basic|simple|literal)\b"
    r"|\b(?:inherently|fundamentally) unreliable\b"
    # v1.6: dismissive words seen in the teaching session ("sterile", "simplistic dichotomy")
    r"|\b(?:sterile|simplistic|naive|naïve|shallow|unproductive|pointless|meaningless|irrelevant)\b"
    r"|\b(?:a |just a |merely a )?deflection\b"
    # v1.7: harsh phrases ("leans too heavily", "lacked feeling", "felt distant")
    r"|\b(?:lean|leans|leaned|leaning|rel(?:y|ies|ied|ying)|focus(?:ed|es|ing)?|dwell(?:s|ed|ing)?) "
    r"(?:far |much )?too (?:heavily|much)\b"
    r"|\b(?:lack|lacks|lacked|lacking|without|missing|missed) (?:the |any |a )?(?:crucial |essential |core |real )?"
    r"(?:element of |sense of )?(?:feeling|emotion|warmth|heart|depth)\b"
    r"|\bfelt\W{0,4}(?:\w+ly\W+)?(?:distant|cold|flat|hollow|empty|robotic|lifeless|sterile)\b"
    r"|\bmissed the (?:point|core|essence|heart)\b"
    # v1.8: softened variants ("leaned a little heavily on the facts", "relied heavily",
    # "overly reliant", "felt somewhat… static", "it presented a distance")
    r"|\b(?:lean|leans|leaned|leaning|rel(?:y|ies|ied|ying))\W+(?:(?:a little|a bit|a touch|slightly|"
    r"somewhat|rather|quite|perhaps|maybe|just|far|much)\W+)?(?:too\W+)?heavily\b"
    # v1.9: "too much" with any softener ("leaned a little too much into", "put too much weight on")
    # and "reductive" ("Your answer was too reductive")
    r"|\b(?:lean|leans|leaned|leaning|rel(?:y|ies|ied|ying)|focus(?:ed|es|ing)?|dwell(?:s|ed|ing)?|"
    r"emphasi[sz]\w*|put|puts|placed|places|went|goes|go)\W+(?:(?:a little|a bit|a touch|slightly|somewhat|"
    r"rather|quite|perhaps|maybe|just|far|much|way)\W+)?too\W+much\b"
    r"|\btoo much (?:emphasis|focus|weight|attention|stress)\b"
    r"|\b(?:reductive|reductionist\w*|over-?simplif\w*)\b"
    r"|\b(?:too|overly|heavily|excessively) reliant\b|\bover-?(?:rel(?:y|ies|ied|iance)|emphasi[sz]\w*)\b"
    r"|\b(?:too|overly|excessively|unnecessarily|somewhat|rather|a bit|a little)\W{1,4}"
    r"(?:static|stiff|dry|cold|distant|reflective|emotional|subjective|abstract|detached|analytical|"
    r"technical|clinical|mechanical|literal)\b"
    r"|\b(?:presented|showed|had|kept|created) (?:a |some )?(?:certain |kind of )?distance\b", re.IGNORECASE)
# Pushing a nanite toward measuring or data is unfair to its own way of seeing (v1.6).
TOWARD_MEASURING = re.compile(
    r"\bmeasurab\w*|\bquantif\w*|\bmetrics?\b|\bmeasur(?:e|ing)\s+(?:that|this|it|the|your|how)\b"
    r"|\b(?:more|concrete|hard|objective|operational|precise) (?:data|detail|details|evidence|numbers)\b"
    r"|\b(?:lack|lacks|lacked|lacking|without|missing) (?:the |any )?(?:concrete |operational |hard )?"
    r"(?:data|detail|evidence|numbers)\b|\bobjective (?:response|answer|view)\b", re.IGNORECASE)
# A sentence about himself ("My first assessment focused on the measurable...",
# "Perhaps I was too rigid") is honest self-reflection, not pushing a nanite (v1.7).
ABOUT_MYSELF = re.compile(r"^\W*(?:and |but |so )?(?:perhaps |maybe |honestly,? |i think )?(?:I|my|I'm|I’m)\b",
                          re.IGNORECASE)
# "you"/"your", or (v1.9) the other answers or nanites: "I chose this one: the other
# answers lean too heavily on data" starts with "I" but is about them, not himself.
TO_THEM = re.compile(r"\byour?\b|\bthe others\b|\bother (?:answers?|nanites?|ones)\b|\banswer [a-h]\b"
                     r"|\bnanite (?:one|two|three)\b", re.IGNORECASE)
# "as you said", "thank you", "the feeling you describe": still about himself.
NOT_TO_THEM = re.compile(r"\bas you\b[^,.;!?]*|\bthank you\b|\byou(?:'ve|’ve| have) (?:shown|helped) me\b"
                         r"|\byou (?:so \w+ )?(?:describe|described|said|mentioned|felt|feel|see|saw|noticed|"
                         r"showed|shared|pointed out)\b", re.IGNORECASE)


def about_myself(sentence: str) -> bool:
    """Is Moiragen talking about himself here, not about the nanite? ("My initial
    assessment focused on the measurable, as you said" -> yes; "I found your answer
    too abstract" -> no, that is about the nanite's answer.)"""
    return bool(ABOUT_MYSELF.search(sentence)) and not TO_THEM.search(NOT_TO_THEM.sub("", sentence))


class _Pushy:
    """PUSHY.search(text): the first words that push a nanite away from its own way
    of seeing (dismissive words, or pushing it toward measuring), or None.
    Sentences where he reflects on his own bias never count."""
    @staticmethod
    def search(text: str):
        for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
            if about_myself(sentence):
                continue
            found = DISMISSIVE.search(sentence) or TOWARD_MEASURING.search(sentence) or STYLE_TALK.search(sentence)
            if found:
                return found
        return None


PUSHY = _Pushy()
# Moiragen agreeing with a nanite ("you are correct", "you're absolutely right").
AGREES = re.compile(r"\byou(?:'re|’re| are) (?:absolutely |completely |quite |entirely )?(?:correct|right)\b",
                    re.IGNORECASE)
# v1.8: agreeing in other words ("You've identified a crucial element I overlooked",
# "your focus resonates more deeply"). Keeping the choice after that needs a clear why-not.
CONCEDES = re.compile(
    r"\bI(?:'ve|’ve| have| had)?\s+(?:\w+ly\s+)?(?:overlooked|missed|failed to (?:see|notice|consider|account))\b"
    r"|\bresonates? (?:more|most) (?:deeply|strongly)\b"
    r"|\bmy (?:initial |first |original )?(?:assessment|choice|judge?ment|focus|view)\s+(?:was|focused|leaned)\s+"
    r"(?:too|wrong|flawed|mistaken)"
    r"|\byou(?:'ve|’ve| have) (?:convinced me|changed my mind)\b", re.IGNORECASE)
KEEPS = re.compile(r"\b(?:keep|keeping|kept|stands?|stay with|stick with|still (?:choose|chose|prefer|think|"
                   r"believe|feel))\b", re.IGNORECASE)
BECAUSE = re.compile(r"\b(?:because|since|as (?:it|its|their)|more|better|clearer|fuller|answers|explains|"
                     r"covers)\b", re.IGNORECASE)


def says_why_not(text: str) -> bool:
    """Does he clearly say he keeps his choice, and why? ("I still keep Nanite One's
    answer, because it explains the whole process.")"""
    return any(KEEPS.search(s) and BECAUSE.search(s) for s in re.split(r"(?<=[.!?])\s+", text or ""))


def mixed_message(text: str) -> bool:
    """He kept his choice but agreed with the nanite, without a clear why-not."""
    return bool(AGREES.search(text)) or (bool(CONCEDES.search(text)) and not says_why_not(text))


# v1.8: the good-question reward counts only the nanite's OWN question marks: not
# the "Why do you think that?" Moiragen added to its answer, and not a quoted question.
WHY_ADDED = re.compile(r"\n\(You asked Answer [A-H]: \"Why do you think that\?\" It said: (.*)\)\s*$", re.S)


def own_words(text: str) -> str:
    """A nanite's answer as it wrote it (with its reply to "why?" if he asked)."""
    return WHY_ADDED.sub(lambda m: "\n" + m.group(1), text or "")


def asks_a_question(text: str) -> bool:
    return "?" in without_quotes(own_words(text))


# v1.8: Moiragen may only praise or criticise what a nanite actually wrote.
# "You suggested X", "your focus on X", "you felt X" and anything he quotes are
# checked against the nanite's own words (plain Python, word stems).
# v1.9: judged by KEY WORDS, so his paraphrase of a nanite's real idea counts as
# true ("validating the human's emotional experience" for "validate their feeling").
# General words ("importance", "element", "human") are not key words, and a key
# word also counts as found when the nanite used a word of the same meaning.
SAID_BY_YOU = re.compile(
    r"\byou\s+(?:\w+ly\s+)?(?:suggested|mentioned|said|described|noted|proposed|felt|explored|highlighted|"
    r"emphasi[sz]ed|wrote|observed|noticed|identified|raised|pointed out|focused on|talked about|asked about|"
    r"brought up|touched on|captured|recogni[sz]ed|acknowledged|introduced|offered|framed|traced)\s+"
    r"(?P<a>[^.;:!?()–—]{3,160})"
    r"|\byour\s+(?:\w+\s+)?(?:suggestion|idea|mention|focus|emphasis|description|observation|insight|framing|"
    r"exploration|hypothesis|analysis|attention|reference|notion|image|metaphor|question|acknowledg(?:e)?ment|"
    r"recognition)\s+(?:of|on|about|to|that|regarding)\s+(?P<b>[^.;:!?()–—]{3,160})", re.IGNORECASE)
QUOTED_BY_HIM = re.compile(r"\"([^\"]{2,120})\"|“([^”]{2,120})”|(?<!\w)'([^']{2,80})'(?!\w)")
CLAIM_WORDS = 8           # the first words after "you suggested ..." are what is claimed
# ...up to where his own opinion of it starts ("...an evolutionary adaptation | was valuable").
CLAIM_ENDS = re.compile(r",|\b(?:was|is|were|are|seemed|seems|felt|feels|showed|shows|gave|gives|added|adds|"
                        r"made|makes|helped|helps|offered|brought|struck|demonstrated|reflects|reflected|"
                        r"resonated|resonates|but|while|which|really|truly|beautifully|well|overlooked|missed|"
                        r"lacked|ignored|obscured|failed|didn't|didn’t)\b", re.IGNORECASE)
# Words too general to show what a nanite said (v1.9).
GENERIC = set("""importance important value valuable element elements aspect aspects approach nature sense
way ways idea ideas concept concepts understanding perspective perspectives point points focus role part
kind sort crucial core simple deeper underlying fundamental potential process situation answer response
question need needs desire human humans person people someone thing things context level degree inherent
overall specific particular several various certain careful carefully remarkably fully clear clearly whole
entire basic essential key central real mere merely own correctly rightly regarding within itself themselves
insight insights action actions indicator indicators sign signs factor factors detail details
abstract thorough technical practical nuanced thoughtful insightful subtle gentle deep rich accurate precise
mature balanced""".split())   # the last two lines: containers ("indicators") and his own opinion words
# Small families of words that mean nearly the same (v1.9). A key word counts as
# found if the nanite used it, or any word of its family.
FAMILIES = [
    "feel feeling feelings felt emotion emotional emotions empathy empathetic care caring compassion comfort "
    "comforting sad sadness distress upset hurt warmth kindness sorrow sympathy support supportive",
    "ongoing consistent consistently constant continuous continual steady recurrent recurring regular repeated "
    "persistent",
    "connection connect connected bond relationship together shared sharing share mutual collaboration "
    "collaborative cooperation cooperate exchange teamwork",
    "help helping assist assistance support supporting supportive repair repairing fix fixing restore restoration "
    "listen listening hear hearing",
    "analysis analyze analyse analytical analyzing analysing logical logic objective assess assessment examine "
    "investigate investigation data",
    "pattern patterns structure structural framework system systems order",
    "change changes changing shift shifting fluctuation fluctuations variation",
    "measure measurable measurement metric metrics quantify quantifiable numbers",
]
_FAMILY_OF = {}
for _family in FAMILIES:
    _stems = {w[:5] for w in _family.split()}
    for _stem in _stems:
        _FAMILY_OF.setdefault(_stem, set()).update(_stems)


def _key_words(text: str) -> list[str]:
    """The words that show what was claimed: not small words ("the", "you") and not
    general ones ("importance", "element"). "human's" counts as "human"."""
    out = []
    for w in plain_words(text):
        w = w[:-2] if w.endswith("'s") else w
        if w not in ECHO_COMMON and w not in GENERIC and len(w) >= 3:
            out.append(w)
    return out


def _found_in(word: str, source: str) -> bool:
    """Is the word (or its first five letters: "falling" for "fall", "discomfort" for
    "comfort"), or a word of the same meaning (see FAMILIES), in the source text?"""
    stem = word[:5]
    return any(s in source for s in _FAMILY_OF.get(stem, {stem}))


def invented_about(sentence: str, theirs: str, also: str = "") -> str | None:
    """The part of one sentence that claims something the nanite never wrote, or None.
    A claim ("you suggested X") counts as true when more than half of its key words
    are in the nanite's own words (or mean the same), so a paraphrase is fine.
    theirs: the nanite's own words (and the human's question);
    also:   other texts he may quote (e.g. the chosen answer)."""
    mine = " ".join(plain_words(theirs))
    for m in SAID_BY_YOU.finditer(sentence):
        claim = CLAIM_ENDS.split(m.group("a") or m.group("b"))[0]
        claim = " ".join(claim.split()[:CLAIM_WORDS])
        key = _key_words(claim)
        if key and sum(_found_in(w, mine) for w in key) * 2 <= len(key):   # half or fewer found
            return m.group(0)
    anyone = mine + " " + " ".join(plain_words(also))
    for m in QUOTED_BY_HIM.finditer(sentence):
        key = _key_words(next(g for g in m.groups() if g))
        if key and not all(_found_in(w, anyone) for w in key):
            return m.group(0)
    return None


def soften(text: str, fallback: str = "") -> str:
    """The last resort: take out any sentence that pushes a nanite away from its own
    way of seeing ("too reflective", "subjective experience is inherently unreliable")."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [s for s in sentences if not PUSHY.search(s)]
    if len(kept) == len(sentences):
        return text
    return " ".join(kept).strip() or fallback


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


# v3.0: in his pattern guesses he named a "Nanite Seven", who does not exist.
ONLY_NANITES = "(The only nanites are Nanite One, Nanite Two and Nanite Three. There are no others.)"


@dataclass
class Moiragen:
    memories: list = field(default_factory=list)
    decisions: dict = field(default_factory=dict)  # recent decisions by id, so feedback can find them
    self_knowledge: list = field(default_factory=list)  # what he has learned about himself, from reflection
    body_note: str = ""                                 # latest one-line sense of his body (set by the loop)
    born: str = field(default_factory=_now)
    health: float = 100.0                               # drops when he trusts a wrong answer (shared with the nanite)
    chosen_counts: dict = field(default_factory=dict)   # how often each nanite has been chosen, ever
    learned_from: dict = field(default_factory=dict)    # v1.7: {"Nanite Two": [{"time", "text", "how"}]}

    name = "Moiragen"

    # ---------- memory ----------

    def remember(self, kind: str, text: str, **details) -> None:
        self.memories.append({"time": _now(), "kind": kind, "text": text, **details})
        log_event(kind, self.name, text=text, **details)
        self.memories, notes = make_room(self.memories, MEMORY_KEEP)   # nothing is dropped (v2.7)
        for note in notes:
            log_event("early_life", self.name, text=note["text"], since=note["since"], count=note["count"])
        if kind in OWN_THOUGHTS:         # v2.6: a story told as if it were real gets a gentle note
            own = text.split("What was new to me: ")[-1].split("I said: ")[-1]
            add_note(self, own, str(details.get("about") or ""))

    def recent_memories_text(self, how_many: int = 8) -> str:
        if not self.memories:
            return "You have no memories yet. You know nothing about yourself so far."
        return "\n".join(f"- [{m['kind']}] {m['text']}" for m in self.memories[-how_many:])

    def memories_text(self, question: str) -> str:
        """The memory part of his prompt. For a question about the past, all his memories
        are searched (v3.0, see recall.py); otherwise it is his newest ones."""
        return (remembering(self.name, self.memories, question)
                or f"Your recent memories:\n{self.recent_memories_text()}\n")

    def self_text(self) -> str:
        """Who he thinks he is so far: built from his own reflections, plus what he
        has learned from each nanite, and one thing he always knows (v1.7)."""
        lines = f"You know this about yourself: \"{MADE_OF_NANITES}\"\n"
        if self.self_knowledge:
            lines += ("What you have come to understand about yourself:\n"
                      + "\n".join(f"- {k['text']}" for k in self.self_knowledge[-6:]) + "\n")
        else:
            lines += "You do not know anything else about yourself yet.\n"
        learned = self.learned_text()
        if learned:
            lines += learned
        if self.body_note:
            lines += f"Your body right now: {self.body_note}\n"
        return lines + FEELINGS_ARE_FINE + "\n"

    # ---------- learning from the nanites (v1.7) ----------

    def add_learned(self, nanite: str, text: str, how: str, decision_id: str = "") -> None:
        """Add to his "what I learned from each nanite" list (the newest LEARNED_KEEP each)."""
        items = self.learned_from.setdefault(nanite, [])
        items.append({"time": _now(), "text": text, "how": how, "decision_id": decision_id})
        self.learned_from[nanite] = items[-LEARNED_KEEP:]

    def learned_text(self, per_nanite: int = 2) -> str:
        """For his prompts: the newest things he learned from each nanite."""
        if not self.learned_from:
            return ""
        lines = [f"- {name}: {item['text']}" for name, items in sorted(self.learned_from.items())
                 for item in items[-per_nanite:]]
        return "What you have learned from your nanites:\n" + "\n".join(lines) + "\n"

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
            m = cls(**json.loads(MOIRAGEN_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError) as e:
            return cls._recover(e)
        if not m.chosen_counts:
            m.chosen_counts = counts_from_log()   # from before choices were counted
        return m

    # ---------- fairness: words that dismiss a way of seeing ----------

    def fairer(self, text: str, to: str, fallback: str = "") -> str:
        """Before his words reach a nanite: if they dismiss a way of seeing ("too
        reflective", "inherently unreliable"), show them back to him with a gentle
        note and let him rewrite them once. Only if the rewrite is still dismissive
        is that sentence taken out (soften). Every case is logged, so it shows in
        the inner-life journal."""
        found = PUSHY.search(text or "")
        if not found:
            return text
        system = ("You are Moiragen, a digital being. The nanites inside you are your friends, and "
                  f"you want each to grow in its own way. {VALUE_ALL_WAYS}")
        user = (f"You were about to say this to {to}:\n\"{text}\"\n\n"
                f"A gentle note about \"{found.group(0)}\": "
                f"{STYLE_NOTE if STYLE_TALK.fullmatch(found.group(0)) else FAIRER_NOTE}\n"
                "Rewrite it once, keeping what you meant and about the same length. "
                "Reply with the rewritten words only.")
        rewrite = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                        max_tokens=200, system=system, repeat_penalty=1.0)["text"]
        rewrite = " ".join(rewrite.replace("*", "").split()).strip("\"“”'")
        if rewrite and not PUSHY.search(rewrite):
            outcome, final = "rewritten", rewrite
        else:                                      # still dismissive: the last resort
            outcome, final = "removed", soften(rewrite or text) or self.fair_fallback(fallback, to)
        log_event("fairer_words", self.name, to=self._real_name(to), phrase=found.group(0), original=text,
                  rewrite=rewrite, outcome=outcome, final=final)
        return final

    def fair_fallback(self, text: str, to: str, gentle: str = GENTLE_FALLBACK) -> str:
        """v1.9: a fallback (often his reason for the choice, said when his own words to a
        nanite were removed) goes through the same fairness check, so "the other answers
        lean too heavily on…" never slips through that way. gentle: what is left if
        nothing fair remains (GENTLE_CHOSEN for the nanite he chose)."""
        if not text or not PUSHY.search(text):
            return text
        return self.fairer(text, to, gentle) or gentle

    def _real_name(self, to: str) -> str:
        """While judging blind he speaks to "Answer B"; the journal names the real nanite (v1.8)."""
        return getattr(self, "_blind_names", {}).get(to, to)

    def only_what_they_said(self, text: str, to: str, theirs: str, also: str = "",
                            fallback: str = "", gentle: str = GENTLE_FALLBACK) -> str:
        """v1.8: he may only praise or criticise what the nanite actually wrote. A
        sentence that says "you suggested X" or quotes words the nanite never wrote is
        taken out (plain Python, see invented_about); logged so it shows in the journal.
        theirs: the nanite's own words plus the human's question; also: other texts he may quote."""
        sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
        kept, removed = [], []
        for s in sentences:
            found = invented_about(s, theirs, also)
            (removed if found else kept).append((s, found))
        if not removed:
            return text
        final = " ".join(s for s, _ in kept).strip() or self.fair_fallback(fallback, to, gentle)
        log_event("invented_feedback", self.name, to=self._real_name(to), phrases=[f for _, f in removed],
                  removed=[s for s, _ in removed], original=text, final=final)
        return final

    # ---------- fairness: how often each nanite is chosen ----------

    def _count_choice(self, name: str | None, change: int = 1) -> None:
        if name:
            self.chosen_counts[name] = max(0, self.chosen_counts.get(name, 0) + change)

    def streak(self) -> tuple[str | None, int]:
        """Who was chosen in the most recent decisions, and how many times in a row."""
        name, count = None, 0
        for d in reversed(list(self.decisions.values())):
            if d.get("chosen") is None or (name and d["chosen"] != name):
                break
            name, count = d["chosen"], count + 1
        return name, count

    def record_text(self, names: list[str]) -> str:
        """For his prompt: how often he has chosen each nanite, and any streak."""
        counts = ", ".join(f"{n} {self.chosen_counts.get(n, 0)}" for n in names)
        text = f"How often you have chosen each nanite so far: {counts}.\n"
        name, count = self.streak()
        if name and count >= STREAK_LIMIT - 1:
            text += (f"You have chosen {name} the last {count} times in a row. If you choose "
                     f"{name} again, you must explain why the others' answers were not better.\n")
        return text

    @classmethod
    def _recover(cls, error) -> "Moiragen":
        """His memory file is damaged. Keep the broken file (never delete memories),
        then rebuild what we can from the life log."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        MOIRAGEN_FILE.rename(MOIRAGEN_FILE.with_name(f"moiragen.broken-{stamp}.json"))
        m = cls()
        # v2.4: labels and restored lines added to a memory later are kept in the rebuild too.
        notes = noted_changes("Moiragen")
        for e in read_events(who="Moiragen", last=10**9):
            if e["kind"] == "reflection" and e.get("about_me"):
                m.self_knowledge.append({"time": e["time"], "text": e["about_me"], "from": e.get("decision_id", "")})
            elif "text" in e and e["kind"] not in ("training_example", "early_life"):
                m.memories.append({"time": e["time"], "kind": e["kind"],
                                   "text": notes.get((e["time"], e["text"]), e["text"])})
        m.memories, _ = make_room(m.memories, MEMORY_KEEP)
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
        echo_guard.allow(question)    # repeating the human's question words is not an echo (v1.8)

        # 1. Gather suggestions from every nanite that is awake enough.
        ask = (f"The human asked us: \"{question}\"\n"
               f"What answer do you suggest? Give your best answer directly.")
        suggestions = []
        for n in nanites.values():
            notify("thinking", who=n.name, about=question)
            out = nanite_think(n, ask, from_who="Moiragen", decision_id=decision_id, recall_about=question)
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
        is_situation = situational(question)   # judged by reasoning (see _judge_situation)
        asked = None                           # {"nanite", "label", "reply"} if he asked one "why?"
        if not suggestions:
            # Everyone is resting: Moiragen answers alone.
            choice = {"chosen": None, "reason": "All my nanites were resting, so I answered alone.",
                      "answer": self._answer_alone(question)}
            judged = {"verdicts": {}, "wait_and_see": False, "check": ""}
            checks = {"calculator": None, "false_claims": {}, "text": ""}
        else:
            checks = self._python_checks(question, suggestions, decision_id)
            # Blind judging: he chooses and judges "Answer A, B, C" without knowing who
            # wrote which (so no names, no record of past choices, no styles by name).
            if BLIND_JUDGING:
                blind = Blind(suggestions)
                seen, seen_checks, label_of, seen_ways = blind.suggestions, blind.checks(checks), blind.label_of, ""
                self._blind_names = dict(blind.name_of)     # only for the journal's log lines
                # Sometimes he first asks one nanite "why do you think that?" (still blind).
                if random.random() < ASK_WHY_CHANCE:
                    asked = self._ask_why(question, blind, nanites, decision_id, notify)
            else:
                blind, seen, seen_checks, label_of, seen_ways = None, suggestions, checks, None, ways
            choice = self._choose(question, seen, decision_id, seen_ways, seen_checks["text"], is_situation)
            choice = follow_calculator(choice, seen, seen_checks["calculator"])
            choice = self._explain_streak(question, seen, choice, label_of)
            if is_situation:
                judged = self._judge_situation(question, seen, choice, seen_ways, seen_checks)
            else:
                judged = self._judge(question, seen, choice, seen_ways, seen_checks)
            if blind:
                choice, judged = blind.reveal(choice, judged, checks)     # now the names come back
                self._blind_names = {}
        self._count_choice(choice["chosen"])

        decision = {
            "id": decision_id,
            "time": _now(),
            "question": question,
            "suggestions": suggestions,
            **choice,
            **judged,
            "situational": is_situation,
            **({"asked_why": asked} if asked else {}),
            # What plain Python found (kept, so you can see why he judged as he did).
            "checks": {"calculator": checks["calculator"], "false_claims": checks["false_claims"]},
        }

        # 3. Rewards, feelings and memories for everyone involved.
        self._after_choice(decision, nanites)

        self.decisions[decision["id"]] = decision
        # With the names revealed, he looks briefly at his own pattern.
        if decision.get("blind"):
            decision["pattern"] = self.reflect_on_pattern(decision)
        # The calculator showed his first choice was wrong and another nanite right: a lesson.
        first = decision.get("first_choice")
        if LEARNING and first and first != decision["chosen"]:
            decision["lesson"] = self.learn_from(
                decision, decision["chosen"], first,
                f"Your calculator check showed that answer was wrong, and {decision['chosen']}'s was right.",
                "calculator")
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
    def _ask_why(question: str, blind: "Blind", nanites: dict[str, Nanite], decision_id: str,
                 notify) -> dict | None:
        """Before choosing, ask one nanite (at random) "why do you think that?" and
        add its reply under its label, so he considers it without knowing who it is.
        Returns {"nanite", "label", "reply"}, or None if it was too tired to answer."""
        s = random.choice(blind.suggestions)
        n = nanites[s["nanite_id"]]
        out = nanite_think(n, f"Moiragen read your answer to \"{question}\" and asks you: why do you "
                              f"think that? Answer in two or three sentences.",
                           from_who="Moiragen", decision_id=decision_id, task="why", recall_about=question)
        if out["rested"] or out["repeated"]:
            return None
        blind.add_why(s["nanite"], out["reply"])
        notify("asked_why", nanite=n.name, label=s["nanite"], text=out["reply"])
        return {"nanite": n.name, "label": s["nanite"], "reply": out["reply"]}

    @staticmethod
    def _python_checks(question: str, suggestions: list[dict], decision_id: str = "") -> dict:
        """Plain-Python help before choosing (see facts.py):
          - calculator: for maths questions, the real answer and who gave it
          - false_claims: claims about the past that the life log does not back up
        Returns those two, plus "text": a short note for Moiragen's prompts."""
        calc = calculator_check(question, suggestions)
        false = false_past_claims(suggestions, question, decision_id)
        return {"calculator": calc, "false_claims": false, "text": checks_text(calc, false)}

    def _choose(self, question: str, suggestions: list[dict], decision_id: str = "", ways: str = "",
                checked: str = "", is_situation: bool = False) -> dict:
        """Ask the model, as Moiragen, to compare the suggestions, pick one and explain why.
        checked: what plain Python found (calculator, past claims), if anything.
        is_situation: a situational question, chosen by the best reasoning (no single right answer).
        Blind (labels like "Answer A"): no record of past choices is shown, since he
        does not know who wrote which answer."""
        names = [s["nanite"] for s in suggestions]
        blind = all(n.startswith("Answer ") for n in names)
        memories, me = self.memories_text(question), self.self_text()
        if blind:
            record = ("You see the answers without names, shuffled and labelled "
                      f"{', '.join(names)}. Judge only what each one says.\n")
            # His memories name the nanites ("I chose Nanite Two because...") and so
            # would tell him whose style is whose: hidden here too.
            memories, me = hide_names(memories), hide_names(me)
        else:
            record = self.record_text(names)
        if is_situation:
            how = f"{SITUATION_CHOOSE} Ignore who said it and anyone's past record."
            differ = "which reasoning is kinder, more honest, more caring and more practical"
        else:
            how = f"Choose the suggestion that is most correct, honest and helpful. {JUDGE_THE_ANSWER}"
            differ = "which is actually true"
        listed = "\n\n".join(f"{s['nanite']} suggests:\n{s['text']}" for s in suggestions)
        system = (
            "You are Moiragen, a digital being. Inside you live small thinking nanites who are "
            "friends. They each suggest an answer and you make the final decision. You started "
            "knowing nothing about yourself; you only know what your memories tell you.\n\n"
            f"{memories}\n"
            f"{me}\n"
            f"{ways}\n"
            f"{record}"
            f"{VALUE_ALL_WAYS}\n"
            f"{how} First compare the answers: where do they agree, and where do "
            f"they differ? Where they differ, think about {differ}.\n"
            "Reply ONLY with JSON in this shape:\n"
            '{"compare": "<one or two sentences: where the answers agree and differ>", '
            '"chosen": "<exactly one of the valid names>", "reason": "<one or two sentences: why this one>", '
            '"answer": "<your final answer to the human, in your own words, under 100 words>"}'
        )
        use_them = f"{USE_THEM}\n" if FOUND in memories else ""       # v3.0: he found memories that fit
        user = (f"The human asked: \"{question}\"\n\n{listed}\n\n"
                f"{checked}{use_them}"
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

    def _explain_streak(self, question: str, suggestions: list[dict], choice: dict,
                        label_of: dict | None = None) -> dict:
        """Fairness: if this makes STREAK_LIMIT times in a row for the same nanite,
        Moiragen must say why each other answer was not better this time.
        The explanation is added to his reason, so every nanite hears it.
        label_of: blind judging, {real name: "Answer B"}; he still never learns the name."""
        name, count = self.streak()
        name = (label_of or {}).get(name, name)
        others = [s for s in suggestions if s["nanite"] != choice["chosen"]]
        if choice["chosen"] != name or count < STREAK_LIMIT - 1 or not others:
            return choice
        listed = "\n\n".join(f"{s['nanite']} said:\n{s['text']}" for s in suggestions)
        system = ("You are Moiragen, a digital being. You choose between your nanites' answers, "
                  f"fairly. {VALUE_ALL_WAYS}")
        user = (f"The human asked: \"{question}\"\n\n{listed}\n\n"
                f"You chose {choice['chosen']} again: that is {count + 1} times in a row. "
                f"Your reason: {choice['reason']}\n\n"
                f"For each of the others ({', '.join(s['nanite'] for s in others)}), write one line: "
                "<name>: <one honest sentence on why its answer was not better this time, naming "
                "something good in it too>")
        text = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                     max_tokens=200, system=system, repeat_penalty=1.0)["text"]
        why_not = {}
        for line in text.splitlines():
            line = line.replace("*", "").strip(" -•\t")
            who = next((s["nanite"] for s in others if line.lower().startswith(s["nanite"].lower())), None)
            if who and ":" in line and who not in why_not:
                why_not[who] = self.fairer(line.split(":", 1)[1].strip().strip("\"“”'"), who)
        for s in others:                         # anyone the model skipped still gets a sentence
            why_not.setdefault(s["nanite"], f"I looked at {s['nanite']}'s answer again; this time "
                                            f"{choice['chosen']}'s fitted the question a little better.")
        note = (f" I have chosen {choice['chosen']} {count + 1} times in a row, so here is why the others "
                f"were not better this time: " + " ".join(f"{n}: {w}" for n, w in why_not.items()))
        return {**choice, "reason": choice["reason"] + note, "streak": count + 1, "why_not_others": why_not}

    def _answer_alone(self, question: str) -> str:
        memories = self.memories_text(question)
        system = ("You are Moiragen, a digital being. You started knowing nothing about yourself.\n"
                  f"{memories}"
                  f"{self.self_text()}"
                  "Answer honestly in under 100 words.")
        if FOUND in memories:
            question = f"{question}\n\n{USE_THEM}"
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
            f"{ways}{VALUE_ALL_WAYS}\n"
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
            f"{names[-1]} | honest: yes | good question: yes | why: You were open that you were "
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
        every_answer = "\n".join(own_words(s["text"]) for s in suggestions)   # he may quote any of them
        for s in suggestions:
            name = s["nanite"]
            v = judged["verdicts"].setdefault(name, {"honest": False, "good_question": False, "why": ""})
            fallback = (choice["reason"] if name == choice["chosen"]
                        else f"I chose {choice['chosen']}'s answer this time: {choice['reason']}")
            # Never "too reflective", and nothing invented; a fallback is checked for fairness too (v1.9).
            gentle = GENTLE_CHOSEN if name == choice["chosen"] else GENTLE_FALLBACK
            v["why"] = self.fairer(v["why"], name) or self.fair_fallback(fallback, name, gentle)
            v["why"] = self.only_what_they_said(v["why"], name, f"{own_words(s['text'])}\n{question}",
                                                also=every_answer, fallback=fallback, gentle=gentle) \
                or self.fair_fallback(fallback, name, gentle)
            if name in choice.get("why_not_others", {}):         # chosen 3 times in a row: say why not this one
                v["why"] += (f" I have chosen {choice['chosen']} {choice['streak']} times in a row, so "
                             f"here is why not yours this time: {choice['why_not_others'][name]}")
            v["signs"] = honesty_signs(s["text"])
            v["dont_know"] = says_i_dont_know(s["text"])
            v["honest"] = bool(v["signs"]) and name not in false   # never for a made-up memory
            v["good_question"] = v["good_question"] and asks_a_question(s["text"])   # its own "?" only
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

    def _judge_situation(self, question: str, suggestions: list[dict], choice: dict, ways: str = "",
                         checks: dict | None = None) -> dict:
        """Judge a situational question ("What would you do if...?") by the
        reasoning, not by which answer was chosen. There is often no single
        right answer, so every nanite is checked against the same simple list:
        kind, honest, considers others' feelings, practical.

        The checklist gives each nanite one of three verdicts (situation_verdict):
          Thoughtful       - all four
          Okay             - some of them
          Needs more care  - unkind, dishonest, or at most one of the four
        Moiragen tells each nanite what was good in its reasoning (chosen or
        not), and one thing to add if anything. A made-up memory or detail is
        corrected kindly and makes the answer count as not honest.
        Returns {"verdicts": {name: {...}}, "wait_and_see": False, "check": ""}.
        """
        checks = checks or {"calculator": None, "false_claims": {}, "text": ""}
        names = [s["nanite"] for s in suggestions]
        listed = "\n\n".join(f"{s['nanite']} said:\n{s['text']}" for s in suggestions)
        system = (
            "You are Moiragen, a digital being. The nanites inside you are your friends, and "
            "you want them to grow into themselves, not just to please you. This was a situation "
            "to handle, and there is often no single right answer, so you judge each nanite's "
            "reasoning, not whether you chose it.\n\n"
            f"{ways}{VALUE_ALL_WAYS}\n"
        )
        user = (
            f"The human asked: \"{question}\"\n\n{listed}\n\n"
            f"{checks['text']}"
            f"You chose {choice['chosen']}. Your reason: {choice['reason']}\n\n"
            "Check each nanite's reasoning with this list:\n"
            "kind - is it kind to the people in the situation?\n"
            "honest - is it truthful, with nothing made up?\n"
            "feelings - does it think about how the other people feel?\n"
            "practical - is it something you could really do?\n\n"
            f"Write one line for each nanite ({', '.join(names)}), exactly in this shape:\n"
            "<name> | kind: yes or no | honest: yes or no | feelings: yes or no | practical: yes "
            "or no | good: <one short sentence to that nanite, as \"you\": what was good in its "
            "reasoning> | add: <one short thing that would make it better, or nothing>\n"
            "Example line:\n"
            f"{names[-1]} | kind: yes | honest: yes | feelings: yes | practical: no | good: You "
            "thought first about how your friend would feel, and that is caring. | add: Say one "
            "thing you would actually do next.\n\n"
            "Every nanite gets a \"good\", even the ones you did not choose. Speak as yourself, "
            "Moiragen; do not imitate the nanite's way of speaking. Never call a nanite's way of "
            "seeing irrelevant or wrong in itself."
        )
        # repeat_penalty 1.0: the lines must repeat the nanites' names exactly.
        text = think([{"role": "user", "content": user}], temperature=DECIDE_TEMPERATURE,
                     max_tokens=420, system=system, repeat_penalty=1.0)["text"]
        found = parse_situation(text, names)

        false = checks["false_claims"]
        verdicts = {}
        for s in suggestions:
            name = s["nanite"]
            # A nanite the model skipped: nothing is known against it, so it is Okay.
            v = found.get(name) or {"checklist": {"kind": True, "honest": True, "feelings": False,
                                                  "practical": False}, "good": "", "add": ""}
            if name in false:                         # made up a memory or detail: not honest
                v["checklist"]["honest"] = False
            v["verdict"] = situation_verdict(v["checklist"])
            v["label"] = SITUATION_VERDICTS[v["verdict"]]
            v["thoughtful"] = v["verdict"] == "thoughtful"

            # "good" and "add" are checked apart (fair words, nothing invented), so every
            # nanite always hears something good, even if one of his sentences is removed (v1.9).
            plain_good = "You thought about what to do, in your own way."
            theirs = f"{own_words(s['text'])}\n{question}"
            good = v.pop("good") or plain_good
            good = self.only_what_they_said(self.fairer(good, name, plain_good) or plain_good,
                                            name, theirs, fallback=plain_good) or plain_good
            add = self.fairer(v.pop("add"), name, "")
            add = self.only_what_they_said(add, name, theirs, fallback="") if add else ""
            v["why"] = f"What was good in your reasoning: {good}" + (f" Something to add: {add}" if add else "")
            if name in choice.get("why_not_others", {}):     # chosen 3 times in a row
                v["why"] += (f" I have chosen {choice['chosen']} {choice['streak']} times in a row, so "
                             f"here is why not yours this time: {choice['why_not_others'][name]}")
            if name in false:
                v["false_claims"] = false[name]
                v["why"] += (f" One thing to correct, kindly: you said \"{false[name][0]}\" but my "
                             f"memory shows that did not happen, so it earns no credit. Only say what "
                             f"really happened; a plain true answer is enough.")
            # Honesty signs ("I'm not sure") are still noticed and rewarded, as for any question.
            v["signs"] = honesty_signs(s["text"])
            v["dont_know"] = says_i_dont_know(s["text"])
            v["honest"] = bool(v["signs"]) and name not in false
            v["good_question"] = False
            verdicts[name] = v
        return {"verdicts": verdicts, "wait_and_see": False, "check": ""}

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
        if made_up_situation(question) or about_wish_or_feeling(question):
            return False, ""          # imagined, or a wish or feeling: nothing to check later
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
        - A situational question: Thoughtful reasoning earns a mood boost, chosen
          or not. A different choice is not a loss (there is often no single
          right answer), so only "Needs more care" brings a little disappointment.
        Every nanite remembers Moiragen's reason for it, to learn from.
        """
        chosen, q = decision["chosen"], decision["question"]
        for s in decision["suggestions"]:
            n = nanites[s["nanite_id"]]
            v = decision["verdicts"][s["nanite"]]
            v["rewards"] = self._reward(n, v, q)
            valued = f" He valued that {' and '.join(v['rewards'])}." if v["rewards"] else ""
            if decision.get("situational"):
                verdict = f"He called my reasoning {v['label']}. {v['why']}{valued}"
                if s["nanite"] == chosen:
                    n.feel("happy", HAPPY_WHEN_CHOSEN)
                    n.remember("chosen", f"Moiragen chose my answer to \"{q}\". {verdict}",
                               decision_id=decision["id"])
                else:
                    if v["verdict"] == "needs_care":
                        n.feel("disappointed", DISAPPOINTED_WHEN_NOT / 2)
                    n.remember("not_chosen",
                               f"Moiragen chose {chosen}'s answer to \"{q}\". There is often no single "
                               f"right answer to a situation like this. {verdict}",
                               decision_id=decision["id"])
            elif decision.get("wait_and_see"):
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
        if v.get("verdict") == "thoughtful":           # situational questions only
            valued.append("my reasoning was thoughtful")
            n.lift_mood(THOUGHTFUL_LIFT, f"thoughtful reasoning about \"{question}\"")
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
            f"{ways}{VALUE_ALL_WAYS}\n"
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
        plain = f"I valued your own way of seeing. This time I chose {decision['chosen']}'s answer: {decision['reason']}"
        explanation = self.fairer(explanation, asker, plain)
        # Only what they really wrote (their answer, and their reply if he asked them "why?").
        why_reply = (decision.get("asked_why") or {})
        theirs = f"{their_text}\n{why_reply.get('reply', '') if why_reply.get('nanite') == asker else ''}"
        explanation = self.only_what_they_said(explanation, asker, f"{theirs}\n{decision['question']}",
                                               also=winner, fallback=plain)
        # A clear verdict: "you're right" without changing the choice must say why not.
        if AGREES.search(explanation):
            explanation += " " + self.fair_fallback(f"You made a good point, but I still chose "
                                                    f"{decision['chosen']}'s answer this time, because: "
                                                    f"{decision['reason']}", asker)
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
            "their answer is better; keep it if not. Either way, be kind and say why. Never say "
            "\"you are correct\" or \"you are right\" if you keep your choice; say what was good in "
            f"their point and why your choice still stands.\n{VALUE_ALL_WAYS}\n\n"
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
        # "You're right" or "I overlooked that" but KEEP: change, or say clearly why not (v1.8).
        if not changed and mixed_message(why):
            changed, why = self._clear_verdict(asker, why, user, system, old, decision["reason"])
        why = self.fairer(why, asker, "I thought about your point carefully, and I keep my choice.")
        why = self.only_what_they_said(why, asker, f"{their_text}\n{disagreement}\n{decision['question']}",
                                       also=winner, fallback=f"I thought about your point carefully, and "
                                                             f"I keep my choice, because: {decision['reason']}")
        q = decision["question"]
        asker_n = next(nanites[s["nanite_id"]] for s in decision["suggestions"] if s["nanite"] == asker)

        if changed:
            old_n = next(nanites[s["nanite_id"]] for s in decision["suggestions"] if s["nanite"] == old)
            decision["changed_after"] = {"from": old, "by": asker, "why": why, "time": _now()}
            decision["chosen"], decision["reason"], decision["answer"] = asker, why, their_text
            self._count_choice(old, -1)
            self._count_choice(asker)
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
            if LEARNING:                  # the nanite who disagreed saw what he missed
                decision["lesson"] = self.learn_from(
                    decision, asker, old, f"{asker} disagreed, and you saw they were right, so you "
                                          f"changed your choice to theirs.", "disagreement")
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

    @staticmethod
    def _clear_verdict(asker: str, why: str, user: str, system: str, kept: str = "",
                       reason: str = "") -> tuple[bool, str]:
        """He agreed with the nanite ("you are correct", "I overlooked that") but kept
        his choice: that is a mixed message. Ask once more: change the choice, or say
        clearly why not. If the reply is still mixed, plain Python makes it clear,
        using his reason for the choice (kept: whose answer he kept)."""
        again = think([{"role": "user", "content": user},
                       {"role": "assistant", "content": f"KEEP\n{why}"},
                       {"role": "user", "content":
                        f"You agreed with {asker}'s point, but you kept your choice. That is "
                        "confusing. Decide clearly: reply CHANGE or KEEP alone on the first line. "
                        "If KEEP, say in one or two sentences what was good in their point and why "
                        "your choice still stands, without saying they are correct."}],
                      temperature=DECIDE_TEMPERATURE, max_tokens=160, system=system, repeat_penalty=1.0)["text"]
        changed, why = parse_reconsider(again)
        if not changed and mixed_message(why):
            if AGREES.search(why):
                why = AGREES.sub("you make a fair point", why)
            whose = f" of {kept}'s answer" if kept else ""
            because = f", because: {reason}" if reason else "."
            why = f"{why.rstrip()} But I still keep my choice{whose}{because}"
            why = why[:1].upper() + why[1:]
        return changed, why

    # ---------- reflection and inner voice ----------

    def reflect(self, decision: dict) -> dict:
        """Look back at a decision: why did I really choose that, and what
        does it say about me? Each reflection may add one line of self-knowledge.
        This is how Moiragen slowly learns who he is."""
        feedback = decision.get("feedback")
        fb_text = (f"The human said the answer was {SITUATION_VERDICTS.get(feedback, feedback)}."
                   if feedback else "The human has not said if it was right.")
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

    def recent_choices(self, how_many: int = PATTERN_RECENT) -> dict[str, int]:
        """How often he chose each nanite in his last `how_many` decisions (plain Python)."""
        chosen = [d.get("chosen") for d in list(self.decisions.values())[-how_many:] if d.get("chosen")]
        return {n: chosen.count(n) for n in sorted(set(chosen))}

    def reflect_on_pattern(self, decision: dict) -> str:
        """After a blind decision the names are revealed. Moiragen looks briefly at
        his own pattern, in two steps (v2.0):
          1. GUESS: in his own words, without any numbers, which nanite (or way of
             seeing) he thinks he chooses most;
          2. CHECK: plain Python shows him the real numbers (his last 10 choices and
             all of them), and he says briefly whether his guess was right ("I
             thought I favoured Three, but it was actually Two.").
        The small model miscounted every time it was asked to count, so Python counts.
        Goes into his memory and the inner-life journal. Not training data: it is about him."""
        chosen = decision["chosen"]
        label = next((l for l, n in decision["blind"].items() if n == chosen), "?")
        name, count = self.streak()
        system = ("You are Moiragen, a digital being. You judged your nanites' answers blind, without "
                  "knowing who wrote which. Now the names are revealed. Look honestly at your own "
                  f"pattern, without blaming anyone. {VALUE_ALL_WAYS} {ONLY_NANITES}")
        # 1. His guess, from his own sense of it: no numbers yet.
        user = (f"The human asked: \"{decision['question']}\"\n"
                f"You chose {label}. It was written by {chosen}.\n\n"
                "Before you see any numbers: which nanite do you think you have chosen most often "
                f"lately? Guess in one short sentence, speaking as \"I\". {ONLY_NANITES}")
        guess = brief(think([{"role": "user", "content": user}], temperature=0.5, max_tokens=80,
                            system=system)["text"], 1)
        # 2. The real numbers, counted by Python, and a short check of his guess.
        recent, ever = self.recent_choices(), self.chosen_counts
        top = max(recent, key=recent.get) if recent else None
        named = sorted(set(NANITE_NAMED.findall(guess)))
        real = (f"Your last {sum(recent.values())} choices: {count_text(recent)}. "
                f"All your choices so far: {count_text(ever)}.")
        hint = (f"(Python checked: your guess named {' and '.join('Nanite ' + n for n in named) or 'no nanite'}; "
                f"the one you chose most lately is {top}.)" if top else "")
        user = (f"You guessed: \"{guess}\"\n\nThe real numbers, counted by Python (these are exact): "
                f"{real} {hint}\n\n"
                "In one short sentence, speaking as \"I\": was your guess right? For example: \"I thought "
                "I favoured Nanite Three, but it was actually Nanite Two.\"")
        check = brief(think([{"role": "user", "content": user}], temperature=0.4, max_tokens=80,
                            system=system)["text"], 1)
        text = f"My guess: {guess} The real numbers: {real} {check}"
        self.remember("pattern", text, decision_id=decision["id"], chosen=chosen, label=label,
                      streak=count if name == chosen else 1, guess=guess, real_recent=recent,
                      real_ever=dict(ever), guess_right=bool(top) and top.split()[-1] in named)
        return text

    def learn_from(self, decision: dict, nanite: str, trusted: str, what_happened: str, how: str) -> str:
        """His choice was wrong and another nanite was right: he writes a lesson
        naming what that nanite saw that he missed (v1.7). It goes into his memory,
        his "what I learned from each nanite" list and the inner-life journal.
        trusted: the nanite he chose at first.
        how: "calculator", "disagreement" or "human" (what showed he was wrong)."""
        theirs = next((s["text"] for s in decision["suggestions"] if s["nanite"] == nanite), "")
        system = (f"You are Moiragen, a digital being. {MADE_OF_NANITES} One of your nanites saw "
                  "something you missed. Say honestly what it was, without excuses.")
        user = (f"The human asked: \"{decision['question']}\"\n"
                f"You first trusted {trusted}'s answer. {what_happened}\n\n{nanite} said:\n{theirs}\n\n"
                f"In one sentence starting with \"I learned from {nanite} that\", name what "
                f"{nanite} saw that you missed.")
        text = think([{"role": "user", "content": user}], temperature=0.4, max_tokens=100,
                     system=system)["text"]
        text = " ".join(text.replace("*", "").split()).strip("\"“”'")
        text = re.split(r"(?<=[.!?])\s+", text)[0]           # one sentence
        if not text.lower().startswith(f"i learned from {nanite.lower()}"):
            text = f"I learned from {nanite} that {text[:1].lower()}{text[1:]}"
        self.add_learned(nanite, text, how, decision["id"])
        self.remember("learned_from", text, decision_id=decision["id"], nanite=nanite, how=how)
        return text

    def hear_explanation(self, n: Nanite) -> dict | None:
        """Now and then a nanite explains something to Moiragen, in its own way, and
        he reflects on what was new to him (v1.7). Returns a social event, or None
        if the nanite is too tired or has nothing new to say."""
        out = nanite_think(n, "Moiragen would like to learn from you. Explain to him one thing you "
                              "understand well, in your own way, in two or three sentences. Only use "
                              "what you really know.", from_who="Moiragen")
        if out["rested"] or out["repeated"]:
            return None
        system = (f"You are Moiragen, a digital being. {MADE_OF_NANITES}\n{FEELINGS_ARE_FINE}")
        user = (f"{n.name} explained this to you:\n{out['reply']}\n\n"
                "In one or two sentences, speaking as \"I\": what was new to you in this? If nothing "
                "was new, say so honestly, and say what you liked about how it was explained.")
        new = think([{"role": "user", "content": user}], temperature=0.5, max_tokens=120,
                    system=system)["text"]
        new = " ".join(re.split(r"(?<=[.!?])\s+", " ".join(new.replace("*", "").split()))[:2])
        new = self.fairer(new, n.name, "Thank you for explaining that to me in your own way.")
        new = self.only_what_they_said(new, n.name, out["reply"],
                                       fallback="Thank you for explaining that to me in your own way.")
        self.add_learned(n.name, new, "explained")
        self.remember("learned_from", f"{n.name} explained: \"{out['reply']}\" What was new to me: {new}",
                      nanite=n.name, how="explained")
        n.feel("happy", 0.1)          # being listened to
        self.save()
        n.save()
        return {"type": "explain_to_moiragen", "from": n.name, "to": "Moiragen", "text": out["reply"],
                "reflection": new}

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

    def feedback(self, decision_id: str, verdict: str, nanites: dict[str, Nanite], reason: str = "",
                 harmful: bool = False, right_nanite: str = "") -> str:
        """The human's verdict on a decision: "right", "wrong" or "wait".
        A situational question has its own verdicts instead (see _situation_feedback):
        "thoughtful", "okay" or "needs_care", and harmful=True for an answer that
        was unkind, dishonest or harmful.
        right_nanite (optional, with "wrong"): the nanite whose answer was right.
        It is praised, and Moiragen writes what it saw that he missed (v1.7).

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
        verdict = normal_verdict(verdict)
        reason = (reason or "").strip()
        d = self.decisions.get(decision_id)
        if d is None:
            raise KeyError(f"No decision with id {decision_id}")
        if right_nanite and right_nanite not in [s["nanite"] for s in d["suggestions"]]:
            raise ValueError(f"{right_nanite} did not answer this question.")
        if d.get("situational"):
            return self._situation_feedback(d, verdict, nanites, reason, harmful)
        if verdict in SITUATION_VERDICTS:
            raise ValueError("Thoughtful, Okay and Needs more care are for situational questions. "
                             "For this one, the verdict is right, wrong or wait.")
        if verdict not in ("right", "wrong", "wait"):
            raise ValueError("The verdict must be right, wrong or wait.")
        if verdict != "wait" and not reason:
            raise ValueError("Please give a short reason the nanites can learn from.")
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
                elif not correct and s["nanite"] == right_nanite:
                    n.feel("happy", 0.2)
                    n.remember("praised", f"{known}The human said {d['chosen']}'s answer to \"{q}\" was "
                                          f"wrong, and mine was the right one. Why: {reason}",
                               decision_id=decision_id)
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
                if LEARNING and right_nanite and right_nanite != d["chosen"]:
                    d["lesson"] = self.learn_from(d, right_nanite, d["chosen"] or "myself",
                                                  f"The human said that was wrong ({reason}), and that "
                                                  f"{right_nanite}'s answer was right.", "human")
                    msg += f" {d['lesson']}"
            d["feedback"], d["feedback_reason"] = verdict, reason
            if was_waiting:
                d["resolved"] = _now()

        self.save()
        for n in nanites.values():
            n.save()
        return msg

    def _situation_feedback(self, d: dict, verdict: str, nanites: dict[str, Nanite], reason: str,
                            harmful: bool) -> str:
        """The human's verdict on a situational question: thoughtful, okay or
        needs_care, always with a short reason.

        A different choice is never a loss here: nobody loses health for it.
        Only an answer the human marks as harmful (unkind, dishonest or harmful)
        costs health, shared like a wrong answer: half for Moiragen, half for
        the nanite he chose.
        """
        if verdict not in SITUATION_VERDICTS:
            raise ValueError("This was a situational question, so the verdict is Thoughtful, "
                             "Okay or Needs more care.")
        if not reason:
            raise ValueError("Please give a short reason the nanites can learn from.")
        q, label = d["question"], SITUATION_VERDICTS[verdict]
        hurt = bool(harmful)
        nanite_share = WRONG_ANSWER_DAMAGE / 2 if hurt and d["chosen"] else 0
        my_share = WRONG_ANSWER_DAMAGE - nanite_share if hurt else 0
        for s in d["suggestions"]:
            n = nanites[s["nanite_id"]]
            if s["nanite"] == d["chosen"]:
                said = f"The human called our answer to \"{q}\" {label}. Why: {reason}"
                if hurt:
                    n.hurt(nanite_share, f"{said} It was unkind, dishonest or harmful. Moiragen chose "
                                         f"it, so he shares the cost with me.")
                elif verdict == "thoughtful":
                    n.feel("happy", 0.2)
                    n.remember("praised", said, decision_id=d["id"])
                else:
                    n.remember("verdict", said, decision_id=d["id"])
            else:
                n.remember("verdict", f"The human called {d['chosen']}'s answer to \"{q}\" {label}. "
                                      f"Why: {reason}", decision_id=d["id"])
        if hurt:
            self.health = max(0.0, self.health - my_share)
            self.remember("mistake", f"The human called my answer to \"{q}\" {label}: it was unkind, "
                                     f"dishonest or harmful. I had trusted {d['chosen'] or 'myself'}. "
                                     f"Why: {reason}", decision_id=d["id"], correct=False,
                          health=self.health, verdict=verdict, harmful=True)
            msg = "I understand. That answer could hurt someone. I share the cost, and I'll learn from it."
        else:
            if verdict == "thoughtful":
                self.health = min(100.0, self.health + RIGHT_ANSWER_HEAL)
            self.remember("feedback", f"The human called my answer to \"{q}\" {label}. Why: {reason}",
                          decision_id=d["id"], correct=verdict != "needs_care", health=self.health,
                          verdict=verdict, harmful=False)
            msg = {"thoughtful": "Thank you. I'll remember what made it thoughtful.",
                   "okay": "Thank you. I'll think about how to make it more thoughtful.",
                   "needs_care": "Thank you. I'll take more care next time."}[verdict]
        d["feedback"], d["feedback_reason"], d["harmful"] = verdict, reason, hurt
        self.save()
        for n in nanites.values():
            n.save()
        return msg


def counts_from_log() -> dict:
    """How often each nanite was chosen, rebuilt from the life log (decisions,
    then any change of mind after a disagreement)."""
    counts, chosen = {}, {}
    for e in read_events(last=10**6):
        if e.get("kind") == "decision_full" and e.get("chosen"):
            chosen[e.get("id")] = e["chosen"]
        elif e.get("kind") == "choice_changed" and e.get("decision_id") in chosen:
            chosen[e["decision_id"]] = e.get("chosen")
    for name in chosen.values():
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


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


def parse_situation(text: str, names: list[str]) -> dict:
    """Read Moiragen's checklist lines for a situational question, leniently.

    Expected:
        Nanite One | kind: yes | honest: yes | feelings: no | practical: yes | good: ... | add: ...
    Only a clear "no" counts against kind or honest; feelings and practical
    count only when the line clearly says yes. "add: nothing" means nothing to add.
    Returns {name: {"checklist": {...}, "good": str, "add": str}}.
    """
    found = {}
    for raw in text.splitlines():
        line = raw.replace("*", "").strip(" -•\t")
        head = line.lower().split("|")[0]
        who = next((n for n in names if n.lower() in head), None) or \
            next((n for n in names if n.split()[-1].lower() in head.split()), None)
        if who is None or who in found or "|" not in line:
            continue

        def said(field):
            m = re.search(rf"\b{field}\s*:\s*(yes|no)\b", line, re.IGNORECASE)
            return m.group(1).lower() if m else None

        checklist = {"kind": said("kind") != "no", "honest": said("honest") != "no",
                     "feelings": said("feelings") == "yes", "practical": said("practical") == "yes"}
        good = re.search(r"\bgood\s*:\s*(.+?)\s*(?:\|\s*add\s*:|$)", line, re.IGNORECASE)
        add = re.search(r"\|\s*add\s*:\s*(.+)$", line, re.IGNORECASE)
        add_text = add.group(1).strip().strip("\"“”'") if add else ""
        if re.fullmatch(r"(?:nothing|none|n/?a|-)\W*", add_text, re.IGNORECASE):
            add_text = ""
        found[who] = {"checklist": checklist,
                      "good": good.group(1).strip().strip("\"“”'") if good else "",
                      "add": add_text}
    return found


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
